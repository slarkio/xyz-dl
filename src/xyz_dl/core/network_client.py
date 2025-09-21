"""网络客户端模块

负责HTTP请求的安全管理，包括SSL验证、重定向控制、大小限制等。
从原有的SecureHTTPSessionManager重构而来，专注于网络通信安全。
"""

import ssl
import ipaddress
import urllib.parse
from typing import Any, Dict, Optional, Union

import aiohttp

from ..config import Config
from ..exceptions import NetworkError


def _sanitize_url_for_logging(url: str) -> str:
    """清理URL中的敏感信息用于日志记录

    Args:
        url: 原始URL

    Returns:
        清理后的URL，隐藏查询参数和敏感信息
    """
    try:
        parsed = urllib.parse.urlparse(url)
        sanitized = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"
        return sanitized
    except Exception:
        return "[URL]"


class HTTPClient:
    """安全HTTP客户端

    负责创建和管理安全的HTTP会话，包括:
    - SSL验证和安全配置
    - 重定向限制和验证
    - 响应大小限制
    - 连接池管理
    - SSRF防护
    """

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

    def __init__(self, config: Config):
        """初始化HTTP客户端

        Args:
            config: 配置对象
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "HTTPClient":
        """异步上下文管理器入口"""
        await self._create_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器退出"""
        await self.close()

    async def _create_session(self) -> None:
        """创建HTTP会话"""
        if self._session is not None:
            return

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
            auto_decompress=True,
            raise_for_status=False,
        )

    def _create_ssl_context(self) -> Union[ssl.SSLContext, bool]:
        """创建SSL上下文配置

        Returns:
            ssl.SSLContext: 安全的SSL上下文（当ssl_verify=True时）
            False: 禁用SSL验证（仅用于测试环境，生产环境不推荐）
        """
        if not self.config.ssl_verify:
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
            "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
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
            total=self.config.timeout,
            connect=self.config.connection_timeout,
            sock_read=self.config.read_timeout,
            sock_connect=self.config.connection_timeout,
        )

    def _create_secure_headers(self) -> Dict[str, str]:
        """创建安全的HTTP头"""
        headers = {"User-Agent": self.config.user_agent, **self.config.security_headers}

        # 移除可能暴露信息的头
        headers.pop("Server", None)
        headers.pop("X-Powered-By", None)

        return headers

    async def close(self) -> None:
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

            # 检查主机名是否存在
            if not parsed.hostname:
                return False

            # 检查是否指向内部IP地址（防止SSRF）
            if self._is_private_ip(parsed.hostname):
                return False

            # 检查主机名是否在白名单中
            if self.config.allowed_redirect_hosts:
                if parsed.hostname not in self.config.allowed_redirect_hosts:
                    # 允许同域重定向（但仍需要原始域名也不是私有IP）
                    if (
                        parsed.hostname != original_parsed.hostname
                        or self._is_private_ip(original_parsed.hostname)
                    ):
                        return False

            return True

        except Exception:
            return False

    def _is_private_ip(self, hostname: Optional[str]) -> bool:
        """检查主机名是否为私有IP地址

        Args:
            hostname: 主机名或IP地址

        Returns:
            True 表示是私有IP，False 表示公网IP
        """
        if not hostname:
            return True

        try:
            ip = ipaddress.ip_address(hostname)

            # 检查是否为私有地址
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True

            # 检查是否在私有网段内
            for private_range in self.PRIVATE_IP_RANGES:
                if ip in ipaddress.ip_network(private_range):
                    return True

            return False

        except ValueError:
            # 不是IP地址，认为是域名，返回False
            return False

    async def safe_request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """执行安全的HTTP请求，包含大小限制和重定向控制

        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 其他请求参数

        Returns:
            HTTP响应对象

        Raises:
            NetworkError: 当请求失败或不安全时
        """
        if self._session is None:
            await self._create_session()

        # 设置重定向限制
        if "allow_redirects" not in kwargs:
            kwargs["allow_redirects"] = False  # 手动处理重定向

        # 添加默认headers
        if "headers" in kwargs:
            kwargs["headers"] = dict(kwargs["headers"])
        else:
            kwargs["headers"] = {}

        # 执行请求并检查响应大小
        response = await self._session.request(method, url, **kwargs)

        # 检查响应大小
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.config.max_response_size:
            response.close()
            raise NetworkError(
                "Response size exceeds maximum allowed limit",
                url=_sanitize_url_for_logging(url),
            )

        # 手动处理重定向
        response = await self._handle_redirects(response, url, kwargs)

        return response

    async def _handle_redirects(
        self,
        response: aiohttp.ClientResponse,
        original_url: str,
        request_kwargs: Dict[str, Any],
    ) -> aiohttp.ClientResponse:
        """处理重定向逻辑

        Args:
            response: 初始响应
            original_url: 原始URL
            request_kwargs: 请求参数

        Returns:
            最终响应对象
        """
        redirect_count = 0
        current_url = original_url

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
                        f"Unsafe redirect detected: {_sanitize_url_for_logging(redirect_url)}",
                        url=current_url,
                    )

                # 关闭当前响应并请求新的URL
                response.close()
                redirect_count += 1
                current_url = redirect_url

                # 递归请求重定向URL
                response = await self._session.request(
                    "GET", redirect_url, **request_kwargs
                )

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
                url=_sanitize_url_for_logging(original_url),
            )

        return response
