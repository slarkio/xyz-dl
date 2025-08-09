"""异步下载器核心模块

实现 XiaoYuZhouDL 主类，支持依赖注入和异步下载
"""

import re
import asyncio
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Union, Dict, Any
import aiohttp

from .models import (
    DownloadRequest,
    DownloadResult,
    DownloadProgress,
    EpisodeInfo,
    Config,
)
from .parsers import CompositeParser, parse_episode_from_url, UrlValidator
from .config import get_config
from .exceptions import (
    DownloadError,
    FileOperationError,
    ValidationError,
    NetworkError,
    ParseError,
    wrap_exception,
)


class XiaoYuZhouDL:
    """小宇宙播客下载器 - 异步版本

    支持依赖注入、异步下载、进度回调等现代功能
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        parser: Optional[CompositeParser] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ):
        """初始化下载器

        Args:
            config: 配置对象，如果为None则使用默认配置
            parser: 解析器对象，如果为None则使用默认解析器
            progress_callback: 进度回调函数
        """
        self.config = config or get_config()
        self.parser = parser or CompositeParser()
        self.progress_callback = progress_callback

        # HTTP会话配置
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_downloads)

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self._close_session()

    async def _create_session(self):
        """创建HTTP会话"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            headers = {"User-Agent": self.config.user_agent}
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)

    async def _close_session(self):
        """关闭HTTP会话"""
        if self._session:
            await self._session.close()
            self._session = None

    async def download(self, request: Union[DownloadRequest, str]) -> DownloadResult:
        """主下载方法

        Args:
            request: 下载请求对象或URL字符串

        Returns:
            下载结果对象
        """
        # 标准化请求对象
        if isinstance(request, str):
            request = DownloadRequest(url=request)

        try:
            await self._create_session()

            # 标准化 URL（支持 episode ID 输入）
            try:
                normalized_url = UrlValidator.normalize_to_url(str(request.url))
                # 更新请求对象的 URL 为标准化后的 URL
                request.url = normalized_url
            except Exception as e:
                raise ValidationError(f"Invalid episode URL or ID: {request.url}. {str(e)}")

            # 解析节目信息
            episode_info, audio_url = await self._parse_episode(str(request.url))

            # 生成文件名
            filename = self._generate_filename(episode_info)

            result = DownloadResult(success=True, episode_info=episode_info)

            # 根据模式执行下载
            if request.mode in ["audio", "both"]:
                if not audio_url:
                    raise ParseError("Audio URL not found", url=str(request.url))

                audio_path = await self._download_audio(
                    audio_url, filename, request.download_dir
                )
                result.audio_path = audio_path

            if request.mode in ["md", "both"]:
                md_path = await self._generate_markdown(
                    episode_info, filename, request.download_dir
                )
                result.md_path = md_path

            return result

        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e),
                episode_info=episode_info if "episode_info" in locals() else None,
            )

    async def _parse_episode(self, url: str) -> tuple[EpisodeInfo, Optional[str]]:
        """解析节目信息"""
        try:
            return await parse_episode_from_url(url, self.parser)
        except Exception as e:
            raise ParseError(f"Failed to parse episode: {e}", url=url)

    def _generate_filename(self, episode_info: EpisodeInfo) -> str:
        """生成文件名"""
        # 构建文件名: episode_id + 主播名 + 节目名
        episode_id = episode_info.eid or self._extract_id_from_title(episode_info.title)

        title = episode_info.title
        podcast_title = episode_info.podcast.title

        # 解析标题格式
        if " - " in title:
            parts = title.split(" - ", 1)
            episode_name = parts[0].strip()
            host_name = parts[1].strip() if len(parts) > 1 else podcast_title
        else:
            episode_name = title
            host_name = podcast_title

        # 构建文件名
        if host_name and episode_name and host_name != "未知播客":
            filename = f"{episode_id}_{host_name} - {episode_name}"
        else:
            filename = f"{episode_id}_{title}"

        return self._sanitize_filename(filename)

    def _extract_id_from_title(self, title: str) -> str:
        """从标题中提取ID（备用方案）"""
        # 简单的时间戳作为ID
        return str(int(datetime.now().timestamp()))

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # 移除或替换非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, "", filename)

        # 移除多余空格
        filename = " ".join(filename.split())

        # 限制长度
        max_len = self.config.max_filename_length
        if len(filename) > max_len:
            filename = filename[:max_len]

        return filename.strip()

    def _create_safe_filename(self, title: str, author: str, extension: str = ".md") -> str:
        """创建安全的文件名
        
        Args:
            title: 节目标题
            author: 作者/主播名
            extension: 文件扩展名
            
        Returns:
            清理后的安全文件名
        """
        # 构建基础文件名：作者 - 标题
        if author and author != "未知作者":
            base_name = f"{author} - {title}"
        else:
            base_name = title
        
        # 清理文件名
        safe_name = self._sanitize_filename(base_name)
        
        # 添加扩展名
        return safe_name + extension

    @wrap_exception
    async def _download_audio(
        self, audio_url: str, filename: str, download_dir: str
    ) -> str:
        """下载音频文件"""
        download_path = Path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        file_path = download_path / f"{filename}.mp3"

        # 检查文件是否已存在
        if file_path.exists():
            print(f"File already exists: {file_path}")
            # 在实际应用中可以添加覆盖确认逻辑

        async with self._semaphore:  # 限制并发下载数
            try:
                async with self._session.get(audio_url) as response:
                    if response.status != 200:
                        raise NetworkError(
                            f"HTTP {response.status}: {response.reason}",
                            url=audio_url,
                            status_code=response.status,
                        )

                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    # 初始化进度
                    progress = DownloadProgress(filename=filename, total=total_size)

                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(
                            self.config.chunk_size
                        ):
                            await f.write(chunk)
                            downloaded += len(chunk)

                            # 更新进度
                            progress.downloaded = downloaded

                            if self.progress_callback:
                                self.progress_callback(progress)

                    return str(file_path)

            except aiohttp.ClientError as e:
                raise DownloadError(
                    f"Download failed: {e}", url=audio_url, file_path=str(file_path)
                )
            except IOError as e:
                raise FileOperationError(
                    f"File write failed: {e}",
                    file_path=str(file_path),
                    operation="write",
                )

    @wrap_exception
    async def _generate_markdown(
        self, episode_info: EpisodeInfo, filename: str, download_dir: str
    ) -> str:
        """生成Markdown文件"""
        download_path = Path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        md_file_path = download_path / f"{filename}.md"

        # 构建Markdown内容
        md_content = self._build_markdown_content(episode_info)

        try:
            async with aiofiles.open(md_file_path, "w", encoding="utf-8") as f:
                await f.write(md_content)

            return str(md_file_path)

        except IOError as e:
            raise FileOperationError(
                f"MD file write failed: {e}",
                file_path=str(md_file_path),
                operation="write",
            )

    def _build_markdown_content(self, episode_info: EpisodeInfo) -> str:
        """构建Markdown文件内容"""
        from datetime import datetime
        
        # 处理show notes
        show_notes = episode_info.shownotes or "暂无节目介绍"

        # 简单HTML清理
        if show_notes != "暂无节目介绍":
            show_notes = re.sub(r"<p[^>]*>", "\n", show_notes)
            show_notes = re.sub(r"</p>", "\n", show_notes)
            show_notes = re.sub(r"<br[^>]*/?>", "\n", show_notes)
            show_notes = re.sub(r"<[^>]+>", "", show_notes)
            show_notes = show_notes.strip()

        # 构建YAML元数据
        yaml_metadata = f"""---
title: "{episode_info.title}"
episode_id: "{episode_info.eid}"
url: "{episode_info.episode_url or ''}"
podcast_name: "{episode_info.podcast.title}"
podcast_id: "{episode_info.podcast.podcast_id}"
podcast_url: "{episode_info.podcast.podcast_url}"
published_at: "{episode_info.published_datetime or episode_info.pub_date}"
published_date: "{episode_info.formatted_pub_date}"
published_datetime: "{episode_info.formatted_datetime}"
duration_ms: {episode_info.duration}
duration_minutes: {episode_info.duration_minutes}
duration_text: "{episode_info.duration_text}"
audio_url: "{episode_info.audio_url}"
downloaded_by: "xyz-dl"
downloaded_at: "{datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}"
---"""

        # 构建Markdown内容
        md_content = f"""{yaml_metadata}

# {episode_info.title}

## Show Notes

{show_notes}
"""

        return md_content

    # 同步接口 - 向后兼容
    def download_sync(self, request: Union[DownloadRequest, str]) -> DownloadResult:
        """同步下载接口 - 向后兼容"""
        return asyncio.run(self.download(request))

    # 批量下载
    async def download_batch(
        self, requests: list[Union[DownloadRequest, str]]
    ) -> list[DownloadResult]:
        """批量下载"""
        tasks = [self.download(req) for req in requests]
        return await asyncio.gather(*tasks, return_exceptions=True)

    # 便捷方法
    async def download_audio_only(
        self, url: str, download_dir: str = "."
    ) -> DownloadResult:
        """仅下载音频"""
        request = DownloadRequest(url=url, download_dir=download_dir, mode="audio")
        return await self.download(request)

    async def download_markdown_only(
        self, url: str, download_dir: str = "."
    ) -> DownloadResult:
        """仅下载Markdown"""
        request = DownloadRequest(url=url, download_dir=download_dir, mode="md")
        return await self.download(request)

    async def download_both(self, url: str, download_dir: str = ".") -> DownloadResult:
        """下载音频和Markdown"""
        request = DownloadRequest(url=url, download_dir=download_dir, mode="both")
        return await self.download(request)


# 便捷函数
async def download_episode(
    url: str,
    download_dir: str = ".",
    mode: str = "both",
    config: Optional[Config] = None,
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
) -> DownloadResult:
    """便捷的下载函数"""
    request = DownloadRequest(url=url, download_dir=download_dir, mode=mode)

    async with XiaoYuZhouDL(
        config=config, progress_callback=progress_callback
    ) as downloader:
        return await downloader.download(request)


def download_episode_sync(
    url: str,
    download_dir: str = ".",
    mode: str = "both",
    config: Optional[Config] = None,
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
) -> DownloadResult:
    """同步版本的便捷下载函数"""
    return asyncio.run(
        download_episode(url, download_dir, mode, config, progress_callback)
    )
