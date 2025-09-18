"""异步下载器核心模块

实现 XiaoYuZhouDL 主类，支持依赖注入和异步下载
"""

import asyncio
import os
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union, List

import aiofiles
import aiohttp
from rich.progress import (
    BarColumn,
    DownloadColumn,
    FileSizeColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

# 常量定义
MAX_PATH_LENGTH = 260  # Windows路径长度限制
MAX_DECODE_ITERATIONS = 10  # Unicode解码最大迭代次数
DEFAULT_UNKNOWN_PODCAST = "未知播客"
DEFAULT_UNKNOWN_AUTHOR = "未知作者"
DEFAULT_SHOW_NOTES = "暂无节目介绍"
TEMP_DIRS = ["/tmp", "/var/folders"]  # 安全的临时目录前缀

from .config import get_config
from .exceptions import (
    DownloadError,
    FileOperationError,
    NetworkError,
    ParseError,
    PathSecurityError,
    ValidationError,
    wrap_exception,
)
from .filename_sanitizer import create_filename_sanitizer
from .models import (
    Config,
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    EpisodeInfo,
)
from .parsers import CompositeParser, UrlValidator, parse_episode_from_url


class XiaoYuZhouDL:
    """小宇宙播客下载器 - 异步版本

    支持依赖注入、异步下载、进度回调等现代功能
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        parser: Optional[CompositeParser] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        secure_filename: bool = True,
    ):
        """初始化下载器

        Args:
            config: 配置对象，如果为None则使用默认配置
            parser: 解析器对象，如果为None则使用默认解析器
            progress_callback: 进度回调函数
            secure_filename: 是否使用安全的文件名清理器
        """
        self.config = config or get_config()
        self.parser = parser or CompositeParser()
        self.progress_callback = progress_callback

        # HTTP会话配置
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_downloads)

        # 文件覆盖控制标志
        self._overwrite_all = False
        self._skip_all = False

        # Rich进度条配置
        self._progress: Optional[Progress] = None

        # 文件名清理器
        self._filename_sanitizer = create_filename_sanitizer(secure=secure_filename)

    async def __aenter__(self) -> "XiaoYuZhouDL":
        """异步上下文管理器入口"""
        await self._create_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器退出"""
        await self._close_session()

    async def _create_session(self) -> None:
        """创建HTTP会话"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            headers = {"User-Agent": self.config.user_agent}
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)

    async def _close_session(self) -> None:
        """关闭HTTP会话"""
        if self._session:
            await self._session.close()
            self._session = None

    def _create_progress_bar(self) -> Progress:
        """创建rich进度条"""
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            refresh_per_second=4,
        )

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
                raise ValidationError(
                    f"Invalid episode URL or ID: {request.url}. {str(e)}"
                )

            # 解析节目信息
            episode_info, audio_url = await self._parse_episode(str(request.url))

            # 如果是只获取URL模式，直接返回URL信息
            if request.url_only:
                if not audio_url:
                    raise ParseError("Audio URL not found", url=str(request.url))

                # 确保将audio_url保存到episode_info中
                episode_info.audio_url = audio_url
                return DownloadResult(
                    success=True,
                    episode_info=episode_info,
                    audio_path=None,
                    md_path=None,
                    error=None,
                )

            # 生成文件名
            filename = self._generate_filename(episode_info)

            result = DownloadResult(
                success=True,
                episode_info=episode_info,
                audio_path=None,
                md_path=None,
                error=None,
            )

            # 根据模式执行下载 - both模式优先下载md
            if request.mode in ["md", "both"]:
                md_path = await self._generate_markdown(
                    episode_info, filename, request.download_dir
                )
                result.md_path = md_path

            if request.mode in ["audio", "both"]:
                if not audio_url:
                    raise ParseError("Audio URL not found", url=str(request.url))

                audio_path = await self._download_audio(
                    audio_url, filename, request.download_dir
                )
                result.audio_path = audio_path

            return result

        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e),
                episode_info=episode_info if "episode_info" in locals() else None,
                audio_path=None,
                md_path=None,
            )

    async def _parse_episode(self, url: str) -> tuple[EpisodeInfo, Optional[str]]:
        """解析节目信息"""
        try:
            return await parse_episode_from_url(url, self.parser)
        except Exception as e:
            raise ParseError(f"Failed to parse episode: {e}", url=url)

    def _generate_filename(self, episode_info: EpisodeInfo) -> str:
        """生成文件名 - 优化版本"""
        episode_id = episode_info.eid or self._extract_id_from_title(episode_info.title)
        title = episode_info.title
        podcast_title = episode_info.podcast.title or DEFAULT_UNKNOWN_PODCAST

        # 解析标题格式 - 提取公共逻辑
        episode_name, host_name = self._parse_episode_title(title, podcast_title)

        # 构建文件名 - 简化条件判断
        if host_name and episode_name and host_name != DEFAULT_UNKNOWN_PODCAST:
            filename = f"{episode_id}_{host_name} - {episode_name}"
        else:
            filename = f"{episode_id}_{title}"

        return self._sanitize_filename(filename)

    def _parse_episode_title(self, title: str, podcast_title: str) -> tuple[str, str]:
        """解析节目标题，提取节目名和主播名

        Args:
            title: 节目标题
            podcast_title: 播客标题

        Returns:
            (节目名, 主播名) 元组
        """
        if " - " in title:
            parts = title.split(" - ", 1)
            episode_name = parts[0].strip()
            host_name = parts[1].strip() if len(parts) > 1 else podcast_title
        else:
            episode_name = title
            host_name = podcast_title

        return episode_name, host_name

    def _extract_id_from_title(self, title: str) -> str:
        """从标题中提取ID（备用方案）"""
        # 简单的时间戳作为ID
        return str(int(datetime.now().timestamp()))

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符

        使用安全的文件名清理器，提供多层防护：
        - Unicode规范化
        - 控制字符移除
        - 平台特定字符处理
        - Windows保留名称处理
        - 安全截断
        """
        max_len = self.config.max_filename_length
        return self._filename_sanitizer.sanitize(filename, max_len)

    def _decode_all_encodings(self, path: str) -> str:
        """递归解码所有可能的编码格式，防止编码攻击 - 优化版本

        Args:
            path: 待解码的路径字符串

        Returns:
            完全解码后的路径字符串
        """
        prev_path = ""
        current_path = path

        # 定义特殊编码攻击模式 - 使用常量
        attack_patterns = {
            "%c0%af": "/",  # 空字节攻击
            "%c1%9c": "\\",  # 反斜杠变体
        }

        for _ in range(MAX_DECODE_ITERATIONS):
            if prev_path == current_path:
                break
            prev_path = current_path

            # URL解码
            current_path = urllib.parse.unquote(current_path)

            # Unicode转义解码 - 简化异常处理
            current_path = self._safe_unicode_decode(current_path)

            # 批量处理特殊编码模式
            for pattern, replacement in attack_patterns.items():
                current_path = current_path.replace(pattern, replacement)

        return current_path

    def _safe_unicode_decode(self, text: str) -> str:
        """安全的Unicode解码，忽略解码错误"""
        try:
            import codecs
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return codecs.decode(text, "unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return text

    def _validate_download_path(self, download_dir: str) -> Path:
        """验证下载路径安全性，防止路径遍历攻击

        Args:
            download_dir: 用户提供的下载目录路径

        Returns:
            安全的绝对路径

        Raises:
            PathSecurityError: 检测到路径遍历攻击或不安全路径
        """
        try:
            # 递归解码所有可能的编码格式
            decoded_path = self._decode_all_encodings(download_dir)

            # 创建Path对象并解析为绝对路径
            path = Path(decoded_path).resolve()

            # 检查路径长度限制
            if len(str(path)) > MAX_PATH_LENGTH:
                raise PathSecurityError(
                    f"Path too long: exceeds {MAX_PATH_LENGTH} characters limit",
                    path=str(path),
                    attack_type="path_length_limit",
                )

            # 检查是否包含危险的路径遍历模式
            self._check_path_traversal_attacks(decoded_path)

            # 检查是否为符号链接（Unix系统）
            if path.is_symlink():
                # 解析符号链接的真实路径
                real_path = path.readlink()
                if self._is_dangerous_system_path(real_path):
                    raise PathSecurityError(
                        "Symlink points to dangerous system directory",
                        path=str(path),
                        attack_type="symlink_attack",
                    )

            # 检查是否指向危险的系统目录
            if self._is_dangerous_system_path(path):
                raise PathSecurityError(
                    "Access to system directories not allowed",
                    path=str(path),
                    attack_type="system_directory_access",
                )

            # 检查是否在安全的临时目录中
            is_temp_safe = self._is_safe_temp_path(path)

            # 确保路径在用户可写区域内（基本安全检查）
            user_safe_areas = [
                Path.home(),  # 用户主目录
                Path.cwd(),  # 当前工作目录
            ]

            # 检查路径是否在安全区域内或其子目录中
            is_safe = is_temp_safe  # 临时目录总是安全的
            for safe_area in user_safe_areas:
                try:
                    safe_area_resolved = safe_area.resolve()
                    if str(path).startswith(str(safe_area_resolved)):
                        is_safe = True
                        break
                except (OSError, RuntimeError):
                    continue

            # 如果不在安全区域，但是是相对路径转换后的绝对路径，需要额外检查
            if not is_safe and not Path(download_dir).is_absolute():
                # 检查解析后的绝对路径是否仍在当前工作目录下
                current_dir = Path.cwd().resolve()
                if str(path).startswith(str(current_dir)):
                    is_safe = True
                else:
                    # 相对路径解析到了当前目录之外，仍然不安全
                    is_safe = False

            if not is_safe:
                raise PathSecurityError(
                    "Path outside of allowed safe areas",
                    path=str(path),
                    attack_type="unsafe_area_access",
                )

            return path

        except PathSecurityError:
            # 重新抛出安全异常
            raise
        except (OSError, ValueError, RuntimeError) as e:
            raise PathSecurityError(
                f"Invalid path format: {e}",
                path=download_dir,
                attack_type="invalid_path",
            )

    def _check_path_traversal_attacks(self, decoded_path: str) -> None:
        """检查路径遍历攻击模式"""
        # 危险的路径遍历模式
        dangerous_patterns = [
            "../",
            "..\\",
            "/..",
            "\\..",
            "%2e%2e",  # URL编码的..
            "%2f",  # URL编码的/
            "%5c",  # URL编码的\
        ]

        for pattern in dangerous_patterns:
            if pattern.lower() in decoded_path.lower():
                raise PathSecurityError(
                    f"Path traversal attack detected: contains '{pattern}'",
                    path=decoded_path,
                    attack_type="path_traversal",
                )

    def _is_safe_temp_path(self, path: Path) -> bool:
        """检查路径是否在安全的临时目录中"""
        # 安全的临时目录路径
        temp_paths = [
            *TEMP_DIRS,
            os.environ.get("TEMP", ""),
            os.environ.get("TMPDIR", ""),
        ]

        return any(
            temp_path and str(path).startswith(temp_path)
            for temp_path in temp_paths
            if temp_path
        )

    def _is_dangerous_system_path(self, path: Path) -> bool:
        """检查路径是否指向危险的系统目录

        Args:
            path: 要检查的路径

        Returns:
            True表示危险路径，False表示安全路径
        """
        path_str = str(path).lower().replace("\\", "/")

        # Unix系统危险目录
        unix_dangerous = [
            "/etc",
            "/bin",
            "/sbin",
            "/usr/bin",
            "/usr/sbin",
            "/var/log",
            "/root",
            "/boot",
            "/sys",
            "/proc",
        ]

        # Windows系统危险目录
        windows_dangerous = [
            "c:/windows",
            "c:/program files",
            "c:/program files (x86)",
            "c:/system32",
            "c:/syswow64",
            "windows/system32",  # 相对路径形式
            "/c/windows",  # Unix式Windows路径
        ]

        dangerous_paths = unix_dangerous + windows_dangerous

        for dangerous in dangerous_paths:
            if path_str.startswith(dangerous):
                return True

        return False

    def _ask_file_overwrite_confirmation(
        self, file_path: Path, file_type: str = "文件"
    ) -> bool:
        """询问用户是否覆盖已存在的文件

        Args:
            file_path: 文件路径
            file_type: 文件类型描述

        Returns:
            True表示覆盖，False表示跳过
        """
        print(f"\n⚠️  {file_type} 已存在: {file_path.name}")

        while True:
            choice = (
                input("是否覆盖? (y)覆盖 / (n)跳过 / (a)全部覆盖 / (s)全部跳过: ")
                .strip()
                .lower()
            )

            if choice in ["y", "yes", "覆盖"]:
                return True
            elif choice in ["n", "no", "跳过"]:
                return False
            elif choice in ["a", "all", "全部覆盖"]:
                # 设置全局覆盖标志
                self._overwrite_all = True
                return True
            elif choice in ["s", "skip", "全部跳过"]:
                # 设置全局跳过标志
                self._skip_all = True
                return False
            else:
                print("请输入有效选择: y/n/a/s")

    def _create_safe_filename(
        self, title: str, author: str, extension: str = ".md"
    ) -> str:
        """创建安全的文件名 - 优化版本

        Args:
            title: 节目标题
            author: 作者/主播名
            extension: 文件扩展名

        Returns:
            清理后的安全文件名
        """
        # 构建基础文件名：作者 - 标题
        if author and author != DEFAULT_UNKNOWN_AUTHOR:
            base_name = f"{author} - {title}"
        else:
            base_name = title

        # 清理文件名并添加扩展名
        safe_name = self._sanitize_filename(base_name)
        return safe_name + extension

    def _check_file_exists_and_handle(self, file_path: Path, file_type: str) -> bool:
        """检查文件是否存在并处理用户选择

        Args:
            file_path: 文件路径
            file_type: 文件类型描述

        Returns:
            True表示继续处理，False表示跳过
        """
        if not file_path.exists():
            return True

        if self._skip_all:
            print(f"⏭️  跳过已存在的{file_type}: {file_path.name}")
            return False
        elif not self._overwrite_all:
            should_overwrite = self._ask_file_overwrite_confirmation(
                file_path, file_type
            )
            if not should_overwrite:
                print(f"⏭️  跳过{file_type}: {file_path.name}")
                return False

        return True

    def _get_audio_extension(
        self, audio_url: str, content_type: Optional[str] = None
    ) -> str:
        """根据URL和内容类型确定音频文件扩展名"""
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

    @wrap_exception
    async def _download_audio(
        self, audio_url: str, filename: str, download_dir: str
    ) -> str:
        """下载音频文件"""
        # 验证下载路径安全性
        download_path = self._validate_download_path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        # 先发送HEAD请求获取content-type以确定正确的文件扩展名
        content_type = None
        try:
            if self._session is not None:
                async with self._session.head(audio_url) as response:
                    content_type = response.headers.get("content-type")
        except:
            pass  # 如果HEAD请求失败，继续使用URL判断

        # 确定正确的文件扩展名
        extension = self._get_audio_extension(audio_url, content_type)
        file_path = download_path / f"{filename}{extension}"

        # 检查文件是否已存在 - 使用统一的检查逻辑
        if not self._check_file_exists_and_handle(file_path, "音频文件"):
            return str(file_path)

        async with self._semaphore:  # 限制并发下载数
            try:
                if self._session is not None:
                    async with self._session.get(audio_url) as response:
                        if response.status != 200:
                            raise NetworkError(
                                f"HTTP {response.status}: {response.reason}",
                                url=audio_url,
                                status_code=response.status,
                            )

                        total_size = int(response.headers.get("content-length", 0))
                        downloaded = 0

                        # 使用rich进度条
                        with self._create_progress_bar() as progress:
                            task = progress.add_task(
                                f"🎵 下载音频: {file_path.name}", total=total_size
                            )

                            async with aiofiles.open(file_path, "wb") as f:
                                async for chunk in response.content.iter_chunked(
                                    self.config.chunk_size
                                ):
                                    await f.write(chunk)
                                    downloaded += len(chunk)
                                    progress.update(task, completed=downloaded)

                                    # 保持原有的进度回调兼容性
                                    if self.progress_callback:
                                        progress_info = DownloadProgress(
                                            filename=file_path.name,
                                            downloaded=downloaded,
                                            total=total_size,
                                        )
                                        self.progress_callback(progress_info)

                        print(f"✅ 音频文件已保存: {file_path.name}")
                        return str(file_path)
                else:
                    raise NetworkError("Session not initialized", url=audio_url)

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
        # 验证下载路径安全性
        download_path = self._validate_download_path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        md_file_path = download_path / f"{filename}.md"

        # 检查文件是否已存在 - 使用统一的检查逻辑
        if not self._check_file_exists_and_handle(md_file_path, "Markdown文件"):
            return str(md_file_path)

        # 构建Markdown内容
        md_content = self._build_markdown_content(episode_info)

        try:
            async with aiofiles.open(md_file_path, "w", encoding="utf-8") as f:
                await f.write(md_content)

            print(f"✅ Markdown文件已保存: {md_file_path.name}")
            return str(md_file_path)

        except IOError as e:
            raise FileOperationError(
                f"MD file write failed: {e}",
                file_path=str(md_file_path),
                operation="write",
            )

    def _build_markdown_content(self, episode_info: EpisodeInfo) -> str:
        """构建Markdown文件内容 - 优化版本"""
        from datetime import datetime

        # 处理show notes - 使用常量
        show_notes = episode_info.shownotes or DEFAULT_SHOW_NOTES

        # 简单HTML清理 - 只有在不是默认值时才处理
        if show_notes != DEFAULT_SHOW_NOTES:
            show_notes = self._clean_html_content(show_notes)

        # 构建YAML元数据
        yaml_metadata = self._build_yaml_metadata(episode_info)

        # 构建完整的Markdown内容
        return f"""{yaml_metadata}

# {episode_info.title}

## Show Notes

{show_notes}
"""

    def _clean_html_content(self, content: str) -> str:
        """清理HTML内容，转换为纯文本"""
        # HTML标签清理模式
        html_patterns = [
            (r"<p[^>]*>", "\n"),
            (r"</p>", "\n"),
            (r"<br[^>]*/?>", "\n"),
            (r"<[^>]+>", ""),
        ]

        cleaned = content
        for pattern, replacement in html_patterns:
            cleaned = re.sub(pattern, replacement, cleaned)

        return cleaned.strip()

    def _build_yaml_metadata(self, episode_info: EpisodeInfo) -> str:
        """构建YAML元数据"""
        from datetime import datetime

        return f"""---
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

    # 同步接口 - 向后兼容
    def download_sync(self, request: Union[DownloadRequest, str]) -> DownloadResult:
        """同步下载接口 - 向后兼容"""
        return asyncio.run(self.download(request))

    # 批量下载
    async def download_batch(
        self, requests: List[Union[DownloadRequest, str]]
    ) -> List[DownloadResult]:
        """批量下载"""
        tasks = [self.download(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Filter out exceptions and return only DownloadResult objects
        return [r for r in results if isinstance(r, DownloadResult)]

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
