"""异步下载器核心模块

实现 XiaoYuZhouDL 主类，支持依赖注入和异步下载
"""

import asyncio
import ipaddress
import os
import re
import ssl
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import aiofiles
import aiohttp
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
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
TEMP_DIRS = [
    "/tmp",
    "/var/folders",
    "/private/var/folders",
    "/private/tmp",
]  # 安全的临时目录前缀

# HTTP安全常量
HTTP_RESPONSE_SIZE_LIMIT = 500 * 1024 * 1024  # 500MB
HTTP_CHUNK_SIZE_DEFAULT = 8192
HTTP_TIMEOUT_DEFAULT = 30
HTTP_REDIRECT_LIMIT = 3

# 安全的内部IP范围 (RFC 1918)
PRIVATE_IP_RANGES = [
    "127.0.0.0/8",  # 本地回环
    "10.0.0.0/8",  # 私有网络 A类
    "172.16.0.0/12",  # 私有网络 B类
    "192.168.0.0/16",  # 私有网络 C类
    "169.254.0.0/16",  # 链路本地
    "224.0.0.0/4",  # 多播
    "240.0.0.0/4",  # 实验性
]

from .async_adapter import smart_run
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


def _sanitize_url_for_logging(url: str) -> str:
    """清理URL中的敏感信息用于日志记录

    Args:
        url: 原始URL

    Returns:
        清理后的URL，隐藏查询参数和敏感信息
    """
    try:
        parsed = urllib.parse.urlparse(url)
        # 保留基本信息，隐藏查询参数
        sanitized = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"
        return sanitized
    except Exception:
        # 如果解析失败，返回一个通用标识
        return "[URL]"


def _sanitize_error_message(message: str, url: Optional[str] = None) -> str:
    """清理错误消息中的敏感信息

    Args:
        message: 原始错误消息
        url: 相关的URL（可选）

    Returns:
        清理后的错误消息
    """
    # 替换可能的敏感信息模式
    sensitive_patterns = [
        (r"token=[^&\s]+", "token=***"),
        (r"key=[^&\s]+", "key=***"),
        (r"password=[^&\s]+", "password=***"),
        (r"auth=[^&\s]+", "auth=***"),
        (r"api_key=[^&\s]+", "api_key=***"),
    ]

    sanitized = message
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # 如果提供了URL，替换为清理后的版本
    if url:
        sanitized_url = _sanitize_url_for_logging(url)
        sanitized = sanitized.replace(url, sanitized_url)

    return sanitized


class SecureHTTPSessionManager:
    """安全HTTP会话管理器

    负责创建和配置安全的HTTP会话，包括SSL验证、重定向限制、
    大小限制、连接池配置等安全功能
    """

    def __init__(self, config: Config):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def create_session(self) -> aiohttp.ClientSession:
        """创建安全配置的HTTP会话"""
        if self._session is not None:
            return self._session

        # 配置SSL上下文
        ssl_context = self._create_ssl_context()

        # 配置连接器
        connector = self._create_connector(ssl_context)

        # 配置超时
        timeout = self._create_timeout_config()

        # 配置安全头
        headers = self._create_secure_headers()

        # 创建会话
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
            auto_decompress=True,  # 自动解压缩
            raise_for_status=False,  # 手动处理状态码
        )

        return self._session

    def _create_ssl_context(self) -> Union[ssl.SSLContext, bool]:
        """创建SSL上下文配置

        Returns:
            ssl.SSLContext: 安全的SSL上下文（当ssl_verify=True时）
            False: 禁用SSL验证（仅用于测试环境，生产环境不推荐）
        """
        if not self.config.ssl_verify:
            # 警告：生产环境不应禁用SSL验证
            import warnings

            warnings.warn(
                "SSL verification is disabled. This is not recommended for production use.",
                UserWarning,
                stacklevel=2,
            )
            return False

        # 创建安全的SSL上下文
        ssl_context = ssl.create_default_context()

        # 强制使用强加密算法
        ssl_context.set_ciphers(
            "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:" "!aNULL:!MD5:!DSS"
        )

        # 设置最低TLS版本
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        # 启用证书验证
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED

        return ssl_context

    def _create_connector(
        self, ssl_context: Union[ssl.SSLContext, bool]
    ) -> aiohttp.TCPConnector:
        """创建TCP连接器"""
        return aiohttp.TCPConnector(
            ssl=ssl_context,
            limit=self.config.connection_pool_size,
            limit_per_host=self.config.connections_per_host,
            ttl_dns_cache=self.config.dns_cache_ttl,
            use_dns_cache=True,
            enable_cleanup_closed=True,
        )

    def _create_timeout_config(self) -> aiohttp.ClientTimeout:
        """创建超时配置"""
        return aiohttp.ClientTimeout(
            total=self.config.timeout,  # 总超时时间
            connect=self.config.connection_timeout,  # 连接超时
            sock_read=self.config.read_timeout,  # 读取超时
            sock_connect=self.config.connection_timeout,  # Socket连接超时
        )

    def _create_secure_headers(self) -> Dict[str, str]:
        """创建安全的HTTP头"""
        headers = {"User-Agent": self.config.user_agent, **self.config.security_headers}

        # 移除可能暴露信息的头
        headers.pop("Server", None)
        headers.pop("X-Powered-By", None)

        return headers

    async def close_session(self) -> None:
        """关闭HTTP会话"""
        if self._session:
            await self._session.close()
            self._session = None

    def _validate_redirect_url(self, url: str, original_url: str) -> bool:
        """验证重定向URL的安全性，防止SSRF攻击

        Args:
            url: 重定向目标URL
            original_url: 原始URL

        Returns:
            True 表示安全，False 表示不安全
        """
        try:
            parsed = urllib.parse.urlparse(url)
            original_parsed = urllib.parse.urlparse(original_url)

            # 检查协议是否安全
            if parsed.scheme not in ["http", "https"]:
                return False

            # 检查主机名是否存在 - 防止None hostname绕过
            if not parsed.hostname:
                return False

            # 检查是否指向内部IP地址（防止SSRF） - 优先检查
            if self._is_private_ip(parsed.hostname):
                return False

            # 检查主机名是否在白名单中
            if self.config.allowed_redirect_hosts:
                # 白名单模式：只允许白名单中的主机
                if parsed.hostname not in self.config.allowed_redirect_hosts:
                    # 允许同域重定向（但仍需要原始域名也不是私有IP）
                    if (parsed.hostname != original_parsed.hostname or
                        self._is_private_ip(original_parsed.hostname)):
                        return False

            return True

        except Exception:
            # 解析失败，认为不安全
            return False

    def _is_private_ip(self, hostname: Optional[str]) -> bool:
        """检查主机名是否为私有IP地址

        Args:
            hostname: 主机名或IP地址

        Returns:
            True 表示是私有IP，False 表示公网IP
        """
        if not hostname:
            return True  # 空主机名认为不安全

        try:
            ip = ipaddress.ip_address(hostname)

            # 检查是否为私有地址
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True

            # 检查是否在私有网段内
            for private_range in PRIVATE_IP_RANGES:
                if ip in ipaddress.ip_network(private_range):
                    return True

            return False

        except ValueError:
            # 不是IP地址，认为是域名，返回False
            return False

    async def safe_request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """执行安全的HTTP请求，包含大小限制和重定向控制"""
        session = await self.create_session()

        # 设置重定向限制
        if "allow_redirects" not in kwargs:
            kwargs["allow_redirects"] = False  # 手动处理重定向

        # 添加Content-Length限制到请求头
        if "headers" in kwargs:
            kwargs["headers"] = dict(kwargs["headers"])
        else:
            kwargs["headers"] = {}

        # 执行请求并检查响应大小
        response = await session.request(method, url, **kwargs)

        # 检查响应大小
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.config.max_response_size:
            response.close()
            raise NetworkError(
                "Response size exceeds maximum allowed limit",
                url=_sanitize_url_for_logging(url),
            )

        # 手动处理重定向，限制重定向次数和验证目标URL安全性
        redirect_count = 0
        original_url = url
        current_url = url

        try:
            while (
                response.status in (301, 302, 303, 307, 308)
                and redirect_count < self.config.max_redirects
            ):
                redirect_url = response.headers.get("location")
                if not redirect_url:
                    break

                # 处理相对URL
                redirect_url = urllib.parse.urljoin(current_url, redirect_url)

                # 验证重定向URL的安全性
                if not self._validate_redirect_url(redirect_url, original_url):
                    raise NetworkError(
                        "Unsafe redirect detected: "
                        f"{_sanitize_url_for_logging(redirect_url)}",
                        url=current_url,
                    )

                # 关闭当前响应并请求新的URL
                response.close()
                redirect_count += 1
                current_url = redirect_url

                # 递归请求重定向URL
                response = await session.request(method, redirect_url, **kwargs)

                # 再次检查响应大小
                content_length = response.headers.get("content-length")
                if (
                    content_length
                    and int(content_length) > self.config.max_response_size
                ):
                    raise NetworkError(
                        "Redirected response size exceeds maximum allowed limit",
                        url=_sanitize_url_for_logging(redirect_url),
                    )

        except Exception:
            # 在异常情况下确保响应被关闭
            if response and not response.closed:
                response.close()
            raise

        # 如果超过重定向次数限制
        if (
            response.status in (301, 302, 303, 307, 308)
            and redirect_count >= self.config.max_redirects
        ):
            response.close()
            raise NetworkError(
                "Too many redirects: exceeded maximum allowed limit",
                url=_sanitize_url_for_logging(url),
            )

        return response


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

        # HTTP会话管理器
        self._session_manager = SecureHTTPSessionManager(self.config)
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
            self._session = await self._session_manager.create_session()

    async def _close_session(self) -> None:
        """关闭HTTP会话"""
        await self._session_manager.close_session()
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

        except (
            ValidationError,
            NetworkError,
            ParseError,
            DownloadError,
            FileOperationError,
            PathSecurityError,
        ) as e:
            # 处理已知的应用异常，保留异常类型和上下文
            return DownloadResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                episode_info=episode_info if "episode_info" in locals() else None,
                audio_path=None,
                md_path=None,
            )
        except Exception as e:
            # 处理未知异常，记录完整错误信息用于调试
            import traceback
            error_details = f"Unexpected error ({type(e).__name__}): {e}"

            # 只在调试模式下包含堆栈跟踪
            if self.config.debug_mode and hasattr(e, '__traceback__'):
                error_details += f"\nTraceback: {traceback.format_exc()}"

            return DownloadResult(
                success=False,
                error=error_details,
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
        import sys

        # 非交互模式或无TTY环境，使用默认行为
        if self.config.non_interactive or not sys.stdin.isatty():
            return self.config.default_overwrite_behavior

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

    def _ensure_safe_filename(self, filename: str) -> str:
        """确保文件名绝对安全，防止路径遍历攻击

        Args:
            filename: 待验证的文件名

        Returns:
            安全的文件名

        Raises:
            PathSecurityError: 检测到不安全的文件名
        """
        # 先检查原始filename是否包含路径分隔符 - 防止路径遍历
        dangerous_patterns = ["..", "/", "\\"]
        for pattern in dangerous_patterns:
            if pattern in filename:
                raise PathSecurityError(
                    f"Dangerous pattern '{pattern}' found in filename",
                    path=filename,
                    attack_type="path_traversal"
                )

        # 检查是否为绝对路径（Windows和Unix）
        if (filename.startswith('/') or
            (len(filename) >= 3 and filename[1:3] == ':\\')):
            raise PathSecurityError(
                f"Absolute path not allowed in filename",
                path=filename,
                attack_type="path_traversal"
            )

        # 使用Path.name确保只有文件名部分，去除任何路径成分
        try:
            safe_filename = Path(filename).name
        except (OSError, ValueError) as e:
            raise PathSecurityError(
                f"Invalid filename: {filename}",
                path=filename,
                attack_type="invalid_filename"
            ) from e

        # 检查文件名中是否包含其他危险字符
        other_dangerous_chars = [":", "*", "?", "<", ">", "|"]
        for char in other_dangerous_chars:
            if char in safe_filename:
                raise PathSecurityError(
                    f"Dangerous character '{char}' found in filename",
                    path=filename,
                    attack_type="path_traversal"
                )

        # 检查是否为空或只包含点号和空格
        if not safe_filename or safe_filename.strip() == "" or safe_filename in [".", ".."]:
            raise PathSecurityError(
                "Empty or invalid filename",
                path=filename,
                attack_type="invalid_filename"
            )

        # 限制文件名长度，保留扩展名
        if len(safe_filename) > 255:
            # 尝试保留扩展名
            path_obj = Path(safe_filename)
            extension = path_obj.suffix
            name_without_ext = path_obj.stem

            if extension:
                # 计算可用于名称的长度
                available_length = 255 - len(extension)
                if available_length > 0:
                    safe_filename = name_without_ext[:available_length] + extension
                else:
                    # 扩展名太长，只截断整个文件名
                    safe_filename = safe_filename[:255]
            else:
                safe_filename = safe_filename[:255]

        return safe_filename

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

    async def _detect_audio_content_type(self, audio_url: str) -> Optional[str]:
        """检测音频文件的内容类型

        Args:
            audio_url: 音频文件URL

        Returns:
            内容类型字符串，如果检测失败返回None
        """
        try:
            async with await self._session_manager.safe_request(
                "HEAD", audio_url
            ) as response:
                if response.status == 200:
                    return response.headers.get("content-type")
        except Exception:
            # 如果HEAD请求失败，返回None然后使用URL判断
            pass
        return None

    async def _prepare_download_file_path(
        self, audio_url: str, filename: str, download_dir: str
    ) -> tuple[Path, str]:
        """准备下载文件路径

        Args:
            audio_url: 音频URL
            filename: 文件名（不包含扩展名）
            download_dir: 下载目录

        Returns:
            (download_path, full_file_path): 下载目录和完整文件路径
        """
        # 验证下载路径安全性
        download_path = self._validate_download_path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        # 检测文件类型并确定扩展名
        content_type = await self._detect_audio_content_type(audio_url)
        extension = self._get_audio_extension(audio_url, content_type)

        # 确保文件名安全，防止路径遍历攻击
        safe_filename = self._ensure_safe_filename(f"{filename}{extension}")
        file_path = download_path / safe_filename

        # 最终验证路径在下载目录内
        resolved_file_path = file_path.resolve()
        resolved_download_path = download_path.resolve()

        if not str(resolved_file_path).startswith(str(resolved_download_path)):
            raise PathSecurityError(
                "File path escapes download directory",
                path=str(resolved_file_path),
                attack_type="path_traversal"
            )

        return download_path, str(file_path)

    async def _validate_download_response(
        self, response: aiohttp.ClientResponse, audio_url: str
    ) -> int:
        """验证下载响应的有效性

        Args:
            response: HTTP响应对象
            audio_url: 音频URL

        Returns:
            文件总大小（字节）

        Raises:
            NetworkError: 当响应状态码不正确或文件过大时
        """
        if response.status != 200:
            raise NetworkError(
                f"HTTP {response.status}: Download failed",
                url=_sanitize_url_for_logging(audio_url),
                status_code=response.status,
            )

        total_size = int(response.headers.get("content-length", 0))

        # 检查文件大小限制
        if total_size > self.config.max_response_size:
            raise NetworkError(
                "File size exceeds maximum allowed limit",
                url=_sanitize_url_for_logging(audio_url),
            )

        return total_size

    async def _download_audio_stream(
        self,
        response: aiohttp.ClientResponse,
        file_path: str,
        total_size: int,
        audio_url: str,
    ) -> None:
        """流式下载音频数据

        Args:
            response: HTTP响应对象
            file_path: 目标文件路径
            total_size: 文件总大小
            audio_url: 音频URL

        Raises:
            NetworkError: 当下载大小超过限制时
            FileOperationError: 当文件写入失败时
        """
        downloaded = 0
        file_path_obj = Path(file_path)

        # 使用rich进度条
        with self._create_progress_bar() as progress:
            task = progress.add_task(
                f"🎵 下载音频: {file_path_obj.name}", total=total_size
            )

            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in response.content.iter_chunked(
                    self.config.chunk_size
                ):
                    # 流式下载时检查累积大小
                    if downloaded + len(chunk) > self.config.max_response_size:
                        raise NetworkError(
                            "Download size limit exceeded during streaming",
                            url=_sanitize_url_for_logging(audio_url),
                        )

                    await f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(task, completed=downloaded)

                    # 保持原有的进度回调兼容性
                    if self.progress_callback:
                        progress_info = DownloadProgress(
                            filename=file_path_obj.name,
                            downloaded=downloaded,
                            total=total_size,
                        )
                        self.progress_callback(progress_info)

    @wrap_exception
    async def _download_audio(
        self, audio_url: str, filename: str, download_dir: str
    ) -> str:
        """下载音频文件主方法

        Args:
            audio_url: 音频文件URL
            filename: 文件名（不包含扩展名）
            download_dir: 下载目录

        Returns:
            下载后的文件路径
        """
        # 准备下载文件路径
        download_path, file_path = await self._prepare_download_file_path(
            audio_url, filename, download_dir
        )

        # 检查文件是否已存在
        file_path_obj = Path(file_path)
        if not self._check_file_exists_and_handle(file_path_obj, "音频文件"):
            return file_path

        # 限制并发下载数
        async with self._semaphore:
            response = None
            try:
                response = await self._session_manager.safe_request("GET", audio_url)
                async with response:
                    # 验证响应和获取文件大小
                    total_size = await self._validate_download_response(
                        response, audio_url
                    )

                    # 流式下载数据
                    await self._download_audio_stream(
                        response, file_path, total_size, audio_url
                    )

                print(f"✅ 音频文件已保存: {file_path_obj.name}")
                return file_path

            except aiohttp.ClientError as e:
                sanitized_message = _sanitize_error_message(str(e), audio_url)
                raise DownloadError(
                    f"Download failed: {sanitized_message}",
                    url=_sanitize_url_for_logging(audio_url),
                    file_path=file_path,
                )
            except IOError as e:
                raise FileOperationError(
                    f"File write failed: {_sanitize_error_message(str(e))}",
                    file_path=file_path,
                    operation="write",
                )
            except Exception:
                # 在任何未预期异常情况下确保响应被关闭
                if response and not response.closed:
                    response.close()
                raise

    @wrap_exception
    async def _generate_markdown(
        self, episode_info: EpisodeInfo, filename: str, download_dir: str
    ) -> str:
        """生成Markdown文件"""
        # 验证下载路径安全性
        download_path = self._validate_download_path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        # 确保文件名安全
        safe_filename = self._ensure_safe_filename(f"{filename}.md")
        md_file_path = download_path / safe_filename

        # 最终验证路径在下载目录内
        resolved_file_path = md_file_path.resolve()
        resolved_download_path = download_path.resolve()

        if not str(resolved_file_path).startswith(str(resolved_download_path)):
            raise PathSecurityError(
                "File path escapes download directory",
                path=str(resolved_file_path),
                attack_type="path_traversal"
            )

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

        # 处理show notes - 使用安全的HTML清理
        show_notes = episode_info.shownotes or DEFAULT_SHOW_NOTES

        # 安全HTML清理并转换为Markdown
        if show_notes != DEFAULT_SHOW_NOTES:
            from .security import sanitize_show_notes
            show_notes = sanitize_show_notes(show_notes)

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

    # 同步接口 - 向后兼容，使用智能适配器
    def download_sync(self, request: Union[DownloadRequest, str]) -> DownloadResult:
        """同步下载接口 - 向后兼容

        使用智能适配器自动处理事件循环嵌套问题
        支持在 Jupyter Notebook 和其他环境中使用
        """
        return smart_run(self.download(request))

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
    """同步版本的便捷下载函数

    使用智能适配器自动处理事件循环嵌套问题
    支持在任何环境中调用，包括 Jupyter Notebook
    """
    return smart_run(
        download_episode(url, download_dir, mode, config, progress_callback)
    )
