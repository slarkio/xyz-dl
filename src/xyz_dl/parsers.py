"""页面解析器模块

采用策略模式和协议接口设计，支持多种解析策略
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from urllib.parse import unquote

import aiohttp
from bs4 import BeautifulSoup

from .models import EpisodeInfo, PodcastInfo
from .exceptions import ParseError, NetworkError, wrap_exception


class ParserProtocol(ABC):
    """解析器协议接口"""

    @abstractmethod
    async def parse_episode_info(self, html_content: str, url: str) -> EpisodeInfo:
        """解析节目信息"""
        pass

    @abstractmethod
    async def extract_audio_url(self, html_content: str, url: str) -> Optional[str]:
        """提取音频URL"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """解析器名称"""
        pass


class JsonScriptParser(ParserProtocol):
    """从页面 JavaScript 中解析 JSON 数据的解析器"""

    @property
    def name(self) -> str:
        return "json_script"

    @wrap_exception
    async def parse_episode_info(self, html_content: str, url: str) -> EpisodeInfo:
        """从页面脚本中解析节目信息"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 首先尝试从JSON-LD script提取数据
        json_ld_script = soup.find("script", {"name": "schema:podcast-show", "type": "application/ld+json"})
        if json_ld_script and json_ld_script.string:
            try:
                json_data = json.loads(json_ld_script.string)
                episode_info = self._build_episode_info_from_json_ld(json_data, url)
                
                # 尝试从meta标签中提取封面图片
                try:
                    cover_image = self._extract_cover_image(soup)
                    if cover_image:
                        episode_info = episode_info.model_copy(update={"cover_image": cover_image})
                except Exception as e:
                    print(f"Failed to extract cover image: {e}")
                
                # 尝试从HTML中获取完整的Show Notes
                try:
                    html_show_notes = self.extract_show_notes_from_html(html_content)
                    if html_show_notes and len(html_show_notes) > len(episode_info.shownotes):
                        # 如果HTML中的Show Notes更完整，则使用它
                        episode_info = episode_info.model_copy(update={"shownotes": html_show_notes})
                except Exception as e:
                    print(f"Failed to extract show notes from HTML: {e}")
                
                return episode_info
            except Exception as e:
                print(f"Failed to parse JSON-LD: {e}")

        # 回退到原来的window.__INITIAL_STATE__方法
        script_tags = soup.find_all("script")
        for script in script_tags:
            if not script.string:
                continue

            if "window.__INITIAL_STATE__" in script.string:
                try:
                    json_data = self._extract_json_from_script(script.string)
                    episode_data = self._find_episode_data(json_data)

                    if episode_data:
                        episode_info = self._build_episode_info(episode_data, url)
                        
                        # 尝试从HTML中获取完整的Show Notes
                        try:
                            html_show_notes = self.extract_show_notes_from_html(html_content)
                            if html_show_notes and len(html_show_notes) > len(episode_info.shownotes):
                                # 如果HTML中的Show Notes更完整，则使用它
                                episode_info = episode_info.model_copy(update={"shownotes": html_show_notes})
                        except Exception as e:
                            print(f"Failed to extract show notes from HTML: {e}")
                        
                        return episode_info
                except Exception as e:
                    continue  # 尝试下一个脚本

        raise ParseError(
            "Failed to extract episode data from JSON scripts",
            url=url,
            parser_type=self.name,
        )

    @wrap_exception
    async def extract_audio_url(self, html_content: str, url: str) -> Optional[str]:
        """从页面中提取音频URL"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 首先尝试从JSON-LD script提取音频URL
        json_ld_script = soup.find("script", {"name": "schema:podcast-show", "type": "application/ld+json"})
        if json_ld_script and json_ld_script.string:
            try:
                json_data = json.loads(json_ld_script.string)
                # JSON-LD中音频URL在associatedMedia.contentUrl
                associated_media = json_data.get("associatedMedia", {})
                if isinstance(associated_media, dict):
                    content_url = associated_media.get("contentUrl")
                    if content_url:
                        return content_url
            except Exception as e:
                print(f"Failed to extract audio URL from JSON-LD: {e}")

        # 尝试从 audio 标签获取
        audio_tag = soup.find("audio")
        if audio_tag and audio_tag.get("src"):
            return audio_tag.get("src")

        # 从 JSON 数据中提取
        script_tags = soup.find_all("script")
        for script in script_tags:
            if not script.string or "window.__INITIAL_STATE__" not in script.string:
                continue

            try:
                json_data = self._extract_json_from_script(script.string)
                episode_data = self._find_episode_data(json_data)

                if episode_data:
                    # 尝试多种可能的音频URL字段
                    audio_fields = [
                        "audioUrl",
                        "audio_url",
                        "mediaUrl",
                        "media_url",
                        "enclosureUrl",
                    ]
                    for field in audio_fields:
                        if field in episode_data and episode_data[field]:
                            return episode_data[field]
            except Exception:
                continue

        return None

    def _extract_json_from_script(self, script_content: str) -> Dict[str, Any]:
        """从脚本内容中提取JSON数据"""
        json_start = script_content.find("{")
        json_end = script_content.rfind("}") + 1

        if json_start == -1 or json_end <= json_start:
            raise ParseError("Invalid JSON boundaries in script")

        json_str = script_content[json_start:json_end]
        return json.loads(json_str)

    def _find_episode_data(self, json_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """在JSON数据中查找节目数据"""
        # 尝试多种可能的路径
        possible_paths = [
            ["episodeInfo", "episode"],
            ["episode"],
            ["data", "episode"],
            ["pageProps", "episode"],
        ]

        for path in possible_paths:
            current = json_data
            try:
                for key in path:
                    current = current[key]
                return current
            except (KeyError, TypeError):
                continue

        return None

    def _build_episode_info(
        self, episode_data: Dict[str, Any], url: str
    ) -> EpisodeInfo:
        """构建节目信息模型"""
        # 提取播客信息
        podcast_data = episode_data.get("podcast", {})
        podcast_info = PodcastInfo(
            title=podcast_data.get("title", "未知播客"),
            author=podcast_data.get("author", "未知作者"),
        )

        # 构建节目信息
        return EpisodeInfo(
            title=episode_data.get("title", "未知标题"),
            podcast=podcast_info,
            duration=episode_data.get("duration", 0),
            pub_date=episode_data.get("pubDate", ""),
            eid=episode_data.get("eid", ""),
            shownotes=episode_data.get("shownotes", ""),
        )

    def extract_show_notes_from_html(self, html_content: str) -> str:
        """从HTML中提取完整的Show Notes内容
        
        Args:
            html_content: HTML页面内容
            
        Returns:
            格式化后的Show Notes内容
        """
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 查找Show Notes容器
        show_notes_section = soup.find("section", {"aria-label": "节目show notes"})
        if not show_notes_section:
            return ""
        
        # 查找sn-content div中的article
        sn_content = show_notes_section.find("div", class_="sn-content")
        if not sn_content:
            return ""
        
        article = sn_content.find("article")
        if not article:
            return ""
        
        # 提取并格式化内容
        return self._format_show_notes_content(article)
    
    def _format_show_notes_content(self, article) -> str:
        """格式化Show Notes内容为Markdown
        
        Args:
            article: BeautifulSoup article元素
            
        Returns:
            Markdown格式的Show Notes内容
        """
        markdown_parts = []
        
        for element in article.find_all(['p', 'figure', 'h1', 'h2', 'h3']):
            if element.name == 'p':
                # 处理段落
                text_content = self._extract_paragraph_content(element)
                if text_content.strip():
                    markdown_parts.append(text_content)
            
            elif element.name == 'figure':
                # 处理图片
                img = element.find('img')
                if img and img.get('src'):
                    img_url = img.get('src')
                    alt_text = img.get('alt', '图片')
                    markdown_parts.append(f"![{alt_text}]({img_url})")
            
            elif element.name.startswith('h'):
                # 处理标题
                level = int(element.name[1])
                text = element.get_text().strip()
                if text:
                    markdown_parts.append(f"{'#' * level} {text}")
        
        return '\n\n'.join(markdown_parts)
    
    def _extract_paragraph_content(self, paragraph) -> str:
        """提取段落内容，保留链接和格式
        
        Args:
            paragraph: BeautifulSoup段落元素
            
        Returns:
            格式化的段落文本
        """
        content_parts = []
        
        for element in paragraph.children:
            if hasattr(element, 'name'):
                if element.name == 'span':
                    # 普通文本
                    text = element.get_text().strip()
                    if text:
                        content_parts.append(text)
                
                elif element.name == 'a':
                    # 链接处理
                    link_text = element.get_text().strip()
                    link_url = element.get('href') or element.get('data-url', '')
                    
                    if element.get('class') and 'timestamp' in element.get('class'):
                        # 时间戳链接
                        content_parts.append(f"**{link_text}**")
                    elif link_url and link_text:
                        # 普通链接
                        content_parts.append(f"[{link_text}]({link_url})")
                    elif link_text:
                        # 无URL的链接，保留文本
                        content_parts.append(link_text)
            else:
                # 纯文本节点
                text = str(element).strip()
                if text:
                    content_parts.append(text)
        
        return ''.join(content_parts)

    def _extract_cover_image(self, soup: BeautifulSoup) -> str:
        """从meta标签中提取封面图片URL"""
        # 尝试从og:image提取
        og_image = soup.find("meta", {"property": "og:image"})
        if og_image and og_image.get("content"):
            return og_image.get("content")
        
        # 尝试从twitter:image提取
        twitter_image = soup.find("meta", {"property": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            return twitter_image.get("content")
        
        return ""

    def _build_episode_info_from_json_ld(self, json_data: Dict[str, Any], url: str) -> EpisodeInfo:
        """从JSON-LD数据构建节目信息模型"""
        # 提取播客信息
        podcast_series = json_data.get("partOfSeries", {})
        podcast_url = podcast_series.get("url", "")
        
        # 从播客URL中提取podcast_id
        podcast_id = ""
        if podcast_url:
            try:
                podcast_id = podcast_url.split("/podcast/")[-1].split("?")[0]
            except:
                pass
        
        podcast_info = PodcastInfo(
            title=podcast_series.get("name", "未知播客"),
            author="未知作者",  # JSON-LD中没有作者信息，使用默认值
            podcast_id=podcast_id,
            podcast_url=podcast_url,
        )

        # 解析时长（从PT73M格式转换为毫秒）
        duration = 0
        time_required = json_data.get("timeRequired", "")
        if time_required:
            # PT73M -> 73分钟 -> 73 * 60 * 1000毫秒
            import re
            minutes_match = re.search(r'PT(\d+)M', time_required)
            if minutes_match:
                minutes = int(minutes_match.group(1))
                duration = minutes * 60 * 1000

        # 提取节目ID
        episode_id = ""
        try:
            episode_id = url.split("/episode/")[-1].split("?")[0]
        except:
            pass

        # 提取音频URL
        audio_url = ""
        associated_media = json_data.get("associatedMedia", {})
        if isinstance(associated_media, dict):
            audio_url = associated_media.get("contentUrl", "")

        # 构建节目信息
        return EpisodeInfo(
            title=json_data.get("name", "未知标题"),
            podcast=podcast_info,
            duration=duration,
            pub_date=json_data.get("datePublished", ""),
            eid=episode_id,
            shownotes=json_data.get("description", ""),
            episode_url=json_data.get("url", url),
            audio_url=audio_url,
            published_datetime=json_data.get("datePublished", ""),
        )


class HtmlFallbackParser(ParserProtocol):
    """HTML 回退解析器 - 当 JSON 解析失败时使用"""

    @property
    def name(self) -> str:
        return "html_fallback"

    @wrap_exception
    async def parse_episode_info(self, html_content: str, url: str) -> EpisodeInfo:
        """从HTML元素解析节目信息"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 提取标题
        title = self._extract_title(soup)

        # 提取播客信息
        podcast_info = self._extract_podcast_info(soup)

        # 提取描述
        description = self._extract_description(soup)

        return EpisodeInfo(
            title=title,
            podcast=podcast_info,
            shownotes=description,
            duration=0,  # HTML中无法获取
            pub_date="",  # HTML中无法获取
            eid=self._extract_episode_id(url),
        )

    @wrap_exception
    async def extract_audio_url(self, html_content: str, url: str) -> Optional[str]:
        """从HTML中提取音频URL"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 查找 audio 标签
        audio_tag = soup.find("audio")
        if audio_tag and audio_tag.get("src"):
            return audio_tag.get("src")

        return None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取标题"""
        # 从 title 标签提取
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text().strip()
            # 移除网站标识
            if "|" in title:
                title = title.split("|")[0].strip()
            return title

        # 从 h1 标签提取
        h1_tag = soup.find("h1")
        if h1_tag:
            return h1_tag.get_text().strip()

        return "未知标题"

    def _extract_podcast_info(self, soup: BeautifulSoup) -> PodcastInfo:
        """提取播客信息"""
        # 尝试从面包屑导航中提取播客名称
        podcast_title = "未知播客"
        breadcrumb = soup.find(
            "a", href=lambda x: x and "/podcast/" in x if x else False
        )
        if breadcrumb:
            podcast_title = breadcrumb.get_text().strip()

        return PodcastInfo(title=podcast_title, author="未知作者")

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """提取节目描述"""
        # 从 meta description 提取
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc:
            return meta_desc.get("content", "").strip()

        # 从 og:description 提取
        og_desc = soup.find("meta", {"property": "og:description"})
        if og_desc:
            return og_desc.get("content", "").strip()

        return "暂无节目介绍"

    def _extract_episode_id(self, url: str) -> str:
        """从URL中提取节目ID"""
        try:
            return url.split("/episode/")[-1].split("?")[0]
        except:
            return ""


class CompositeParser:
    """组合解析器 - 使用多种解析策略"""

    def __init__(self, parsers: Optional[List[ParserProtocol]] = None):
        if parsers is None:
            self.parsers = [
                JsonScriptParser(),
                HtmlFallbackParser(),
            ]
        else:
            self.parsers = parsers

    async def parse_episode_info(self, html_content: str, url: str) -> EpisodeInfo:
        """使用多个解析器尝试解析"""
        last_error = None

        for parser in self.parsers:
            try:
                result = await parser.parse_episode_info(html_content, url)
                print(f"Successfully parsed using {parser.name}")
                return result
            except Exception as e:
                print(f"Parser {parser.name} failed: {e}")
                last_error = e
                continue

        # 所有解析器都失败
        raise ParseError(
            f"All parsers failed. Last error: {last_error}",
            url=url,
            parser_type="composite",
        )

    async def extract_audio_url(self, html_content: str, url: str) -> Optional[str]:
        """使用多个解析器尝试提取音频URL"""
        for parser in self.parsers:
            try:
                audio_url = await parser.extract_audio_url(html_content, url)
                if audio_url:
                    print(f"Audio URL extracted using {parser.name}")
                    return audio_url
            except Exception as e:
                print(f"Parser {parser.name} failed to extract audio URL: {e}")
                continue

        return None


class UrlValidator:
    """URL验证器"""

    @staticmethod
    def validate_xiaoyuzhou_url(url: str) -> bool:
        """验证是否为有效的小宇宙播客URL"""
        return url.startswith("https://www.xiaoyuzhoufm.com/episode/")

    @staticmethod
    def extract_episode_id(url: str) -> str:
        """从URL中提取节目ID"""
        if not UrlValidator.validate_xiaoyuzhou_url(url):
            raise ParseError(f"Invalid Xiaoyuzhou URL: {url}")

        try:
            episode_id = url.split("/episode/")[-1].split("?")[0]
            return unquote(episode_id)  # URL解码
        except Exception as e:
            raise ParseError(
                f"Failed to extract episode ID from URL: {url}",
                context={"error": str(e)},
            )


# 便捷函数
def create_default_parser() -> CompositeParser:
    """创建默认的组合解析器"""
    return CompositeParser()


async def parse_episode_from_url(
    url: str, parser: Optional[CompositeParser] = None
) -> tuple[EpisodeInfo, Optional[str]]:
    """从URL解析节目信息和音频URL"""
    if parser is None:
        parser = create_default_parser()

    # 验证URL
    if not UrlValidator.validate_xiaoyuzhou_url(url):
        raise ParseError(f"Invalid Xiaoyuzhou URL: {url}")

    # 获取页面内容
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    raise NetworkError(
                        f"HTTP {response.status}: {response.reason}",
                        url=url,
                        status_code=response.status,
                    )
                html_content = await response.text()
        except aiohttp.ClientError as e:
            raise NetworkError(f"Network error: {e}", url=url)

    # 解析节目信息和音频URL
    episode_info = await parser.parse_episode_info(html_content, url)
    audio_url = await parser.extract_audio_url(html_content, url)

    return episode_info, audio_url
