"""重构后的核心下载器模块

这个模块实现了新的DownloaderCore类，使用依赖注入模式，
将原有XiaoYuZhouDL的各个职责分离到专门的模块中。
"""

from typing import Optional

from ..config import Config
from ..models import DownloadRequest, DownloadResult
from .network_client import HTTPClient
from .file_manager import FileManager
from .progress_manager import ProgressManager
from .validator import ValidationManager


class DownloaderCore:
    """重构后的核心下载器

    使用依赖注入模式，将各个职责分离到专门的模块：
    - HTTPClient: 网络请求
    - FileManager: 文件操作
    - ProgressManager: 进度管理
    - ValidationManager: 输入验证
    """

    def __init__(
        self,
        config: Config,
        http_client: Optional[HTTPClient] = None,
        file_manager: Optional[FileManager] = None,
        progress_manager: Optional[ProgressManager] = None,
        validator: Optional[ValidationManager] = None,
    ):
        """初始化下载器核心

        Args:
            config: 配置对象
            http_client: HTTP客户端（可选，默认创建新实例）
            file_manager: 文件管理器（可选，默认创建新实例）
            progress_manager: 进度管理器（可选，默认创建新实例）
            validator: 验证管理器（可选，默认创建新实例）
        """
        self.config = config

        # 依赖注入或创建默认实例
        self.http_client = http_client or HTTPClient(config)
        self.file_manager = file_manager or FileManager(config)
        self.progress_manager = progress_manager or ProgressManager()
        self.validator = validator or ValidationManager(config)

    async def download(self, request: DownloadRequest) -> DownloadResult:
        """执行下载操作

        Args:
            request: 下载请求

        Returns:
            下载结果
        """
        try:
            # 验证请求URL
            await self.validator.validate_url(request.url)

            # 解析episode信息和音频URL
            episode_info, audio_url = await self._parse_episode(request.url)

            # 如果是只获取URL模式，直接返回URL信息
            if request.url_only:
                if not audio_url:
                    return DownloadResult(
                        success=False,
                        error="Audio URL not found",
                        episode_info=episode_info,
                    )

                # 确保将audio_url保存到episode_info中
                episode_info.audio_url = audio_url
                return DownloadResult(
                    success=True,
                    episode_info=episode_info,
                    audio_path=None,
                    md_path=None,
                )

            # 生成文件名
            filename = self._generate_filename(episode_info)

            result = DownloadResult(
                success=True,
                episode_info=episode_info,
                audio_path=None,
                md_path=None,
            )

            # 根据模式执行下载
            if request.mode in ["md", "both"]:
                md_path = await self._generate_markdown(
                    episode_info, filename, request.download_dir
                )
                result.md_path = md_path

            if request.mode in ["audio", "both"]:
                if not audio_url:
                    return DownloadResult(
                        success=False,
                        error="Audio URL not found",
                        episode_info=episode_info,
                    )

                audio_path = await self._download_audio(
                    audio_url, filename, request.download_dir
                )
                result.audio_path = audio_path

            return result

        except Exception as e:
            return DownloadResult(
                success=False,
                error=f"Download failed: {e}",
            )

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.http_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)

    async def _parse_episode(self, url: str) -> tuple:
        """解析episode信息和音频URL

        Args:
            url: episode URL

        Returns:
            (episode_info, audio_url) 元组
        """
        from ..parsers import parse_episode_from_url, CompositeParser

        # 创建解析器（可以考虑依赖注入）
        parser = CompositeParser()

        # 使用修改后的parse_episode_from_url，使用我们的HTTP客户端
        try:
            # 获取页面内容
            response = await self.http_client.safe_request("GET", url)
            async with response:
                if response.status != 200:
                    from ..exceptions import NetworkError
                    raise NetworkError(
                        f"HTTP {response.status}: {response.reason}",
                        url=url,
                        status_code=response.status,
                    )
                html_content = await response.text()

            # 解析节目信息和音频URL
            episode_info = await parser.parse_episode_info(html_content, url)
            audio_url = await parser.extract_audio_url(html_content, url)

            return episode_info, audio_url

        except Exception as e:
            from ..exceptions import ParseError
            raise ParseError(f"Failed to parse episode: {e}", url=url)

    def _generate_filename(self, episode_info) -> str:
        """生成文件名

        Args:
            episode_info: episode信息

        Returns:
            清理后的文件名
        """
        from ..utils import create_filename_generator

        generator = create_filename_generator()
        return generator.generate(episode_info)

    async def _generate_markdown(self, episode_info, filename: str, download_dir: str) -> str:
        """生成Markdown文件

        Args:
            episode_info: episode信息
            filename: 文件名
            download_dir: 下载目录

        Returns:
            生成的文件路径
        """
        # 验证下载路径安全性
        download_path = self.file_manager.validate_download_path(download_dir)
        await self.file_manager.create_directory(download_path)

        # 确保文件名安全
        safe_filename = self.file_manager.ensure_safe_filename(f"{filename}.md")
        md_file_path = download_path / safe_filename

        # 构建Markdown内容
        md_content = self._build_markdown_content(episode_info)

        # 写入文件
        await self.file_manager.write_file(md_file_path, md_content)

        return str(md_file_path)

    def _build_markdown_content(self, episode_info) -> str:
        """构建Markdown文件内容

        Args:
            episode_info: episode信息

        Returns:
            Markdown内容
        """
        from datetime import datetime

        # 处理show notes
        show_notes = episode_info.shownotes or "暂无节目介绍"

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

        # 构建完整的Markdown内容
        return f"""{yaml_metadata}

# {episode_info.title}

## Show Notes

{show_notes}
"""

    async def _download_audio(self, audio_url: str, filename: str, download_dir: str) -> str:
        """下载音频文件

        Args:
            audio_url: 音频URL
            filename: 文件名
            download_dir: 下载目录

        Returns:
            下载的文件路径
        """
        # 验证下载路径安全性
        download_path = self.file_manager.validate_download_path(download_dir)
        await self.file_manager.create_directory(download_path)

        # 检测文件类型并确定扩展名
        content_type = await self._detect_audio_content_type(audio_url)
        extension = self._get_audio_extension(audio_url, content_type)

        # 确保文件名安全
        safe_filename = self.file_manager.ensure_safe_filename(f"{filename}{extension}")
        file_path = download_path / safe_filename

        # 执行下载
        response = await self.http_client.safe_request("GET", audio_url)
        async with response:
            if response.status != 200:
                from ..exceptions import NetworkError
                raise NetworkError(
                    f"HTTP {response.status}: Download failed",
                    url=audio_url,
                    status_code=response.status,
                )

            total_size = int(response.headers.get("content-length", 0))

            # 检查文件大小限制
            if total_size > self.config.max_response_size:
                from ..exceptions import NetworkError
                raise NetworkError(
                    "File size exceeds maximum allowed limit",
                    url=audio_url,
                )

            # 使用进度管理器创建进度条上下文
            with self.progress_manager.create_rich_progress_context(
                f"🎵 下载音频: {file_path.name}", total_size
            ) as progress_ctx:
                downloaded = 0

                # 写入文件
                with open(file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(self.config.chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress_ctx.update(downloaded)

        return str(file_path)

    async def _detect_audio_content_type(self, audio_url: str) -> str:
        """检测音频文件的内容类型

        Args:
            audio_url: 音频文件URL

        Returns:
            内容类型字符串，如果检测失败返回空字符串
        """
        try:
            response = await self.http_client.safe_request("HEAD", audio_url)
            async with response:
                if response.status == 200:
                    return response.headers.get("content-type", "")
        except Exception:
            pass
        return ""

    def _get_audio_extension(self, audio_url: str, content_type: str = "") -> str:
        """根据URL和内容类型确定音频文件扩展名

        Args:
            audio_url: 音频URL
            content_type: 内容类型

        Returns:
            文件扩展名
        """
        # 优先从content-type判断
        if content_type:
            if "mp4" in content_type or "m4a" in content_type:
                return ".m4a"
            elif "mpeg" in content_type or "mp3" in content_type:
                return ".mp3"
            elif "wav" in content_type:
                return ".wav"
            elif "ogg" in content_type:
                return ".ogg"

        # 从URL扩展名判断
        if audio_url.endswith(".m4a"):
            return ".m4a"
        elif audio_url.endswith(".mp3"):
            return ".mp3"
        elif audio_url.endswith(".wav"):
            return ".wav"
        elif audio_url.endswith(".ogg"):
            return ".ogg"

        # 默认使用m4a（小宇宙大多数音频是m4a格式）
        return ".m4a"