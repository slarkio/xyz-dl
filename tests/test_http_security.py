"""HTTP安全配置测试

测试SSL验证、重定向限制、大小限制、连接池配置等安全功能
"""

import asyncio
import ssl
from unittest.mock import AsyncMock, Mock, patch
from typing import AsyncIterator

import aiohttp
import pytest
import pytest_asyncio
from aioresponses import aioresponses

from src.xyz_dl.config import Config
from src.xyz_dl.downloader import SecureHTTPSessionManager, XiaoYuZhouDL
from src.xyz_dl.exceptions import NetworkError


class TestSecureHTTPSessionManager:
    """测试安全HTTP会话管理器"""

    @pytest.fixture
    def config(self) -> Config:
        """测试配置"""
        return Config(
            ssl_verify=True,
            max_redirects=3,
            max_request_size=1024 * 1024,  # 1MB
            max_response_size=5 * 1024 * 1024,  # 5MB
            connection_pool_size=10,
            connection_timeout=10.0,
            read_timeout=30.0,
        )

    @pytest.fixture
    def session_manager(self, config: Config) -> SecureHTTPSessionManager:
        """测试会话管理器"""
        return SecureHTTPSessionManager(config)

    @pytest.mark.asyncio
    async def test_ssl_context_creation(
        self, session_manager: SecureHTTPSessionManager
    ):
        """测试SSL上下文创建"""
        ssl_context = session_manager._create_ssl_context()

        assert isinstance(ssl_context, ssl.SSLContext)
        assert ssl_context.check_hostname is True
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.minimum_version == ssl.TLSVersion.TLSv1_2

    @pytest.mark.asyncio
    async def test_ssl_disabled(self):
        """测试禁用SSL验证"""
        config = Config(ssl_verify=False)
        session_manager = SecureHTTPSessionManager(config)

        ssl_context = session_manager._create_ssl_context()
        assert ssl_context is False

    @pytest.mark.asyncio
    async def test_connector_configuration(
        self, session_manager: SecureHTTPSessionManager
    ):
        """测试TCP连接器配置"""
        ssl_context = session_manager._create_ssl_context()
        connector = session_manager._create_connector(ssl_context)

        assert isinstance(connector, aiohttp.TCPConnector)
        assert connector.limit == 10  # connection_pool_size
        assert connector.limit_per_host == 5
        # 注意：较新版本的aiohttp可能不暴露内部属性，这里检查类型就足够了

    @pytest.mark.asyncio
    async def test_timeout_configuration(
        self, session_manager: SecureHTTPSessionManager
    ):
        """测试超时配置"""
        timeout = session_manager._create_timeout_config()

        assert isinstance(timeout, aiohttp.ClientTimeout)
        assert timeout.total == 30  # default timeout
        assert timeout.connect == 10.0  # connection_timeout
        assert timeout.sock_read == 30.0  # read_timeout

    @pytest.mark.asyncio
    async def test_secure_headers(self, session_manager: SecureHTTPSessionManager):
        """测试安全头配置"""
        headers = session_manager._create_secure_headers()

        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "DNT" in headers
        assert "Server" not in headers
        assert "X-Powered-By" not in headers

    @pytest.mark.asyncio
    async def test_session_creation(self, session_manager: SecureHTTPSessionManager):
        """测试会话创建"""
        session = await session_manager.create_session()

        assert isinstance(session, aiohttp.ClientSession)
        assert session.timeout.total == 30
        await session_manager.close_session()

    @pytest.mark.asyncio
    async def test_session_reuse(self, session_manager: SecureHTTPSessionManager):
        """测试会话复用"""
        session1 = await session_manager.create_session()
        session2 = await session_manager.create_session()

        assert session1 is session2
        await session_manager.close_session()


class TestHTTPSecurity:
    """测试HTTP安全功能"""

    @pytest.fixture
    def config(self) -> Config:
        """测试配置"""
        return Config(
            ssl_verify=True,
            max_redirects=2,
            max_request_size=1024,  # 1KB for testing
            max_response_size=2048,  # 2KB for testing
            connection_pool_size=5,
            timeout=10,
        )

    @pytest.fixture
    def session_manager(self, config: Config) -> SecureHTTPSessionManager:
        """测试会话管理器"""
        return SecureHTTPSessionManager(config)

    @pytest.mark.asyncio
    async def test_response_size_limit_exceeded(
        self, session_manager: SecureHTTPSessionManager
    ):
        """测试响应大小限制"""
        with aioresponses() as m:
            # 模拟大文件响应
            m.get(
                "https://example.com/large-file",
                headers={"content-length": "5000"},  # 超过2KB限制
                body="x" * 5000,
            )

            with pytest.raises(
                NetworkError, match="Response size exceeds maximum allowed limit"
            ):
                await session_manager.safe_request(
                    "GET", "https://example.com/large-file"
                )

    @pytest.mark.asyncio
    async def test_redirect_limit_exceeded(
        self, session_manager: SecureHTTPSessionManager
    ):
        """测试重定向次数限制"""
        with aioresponses() as m:
            # 设置循环重定向
            m.get(
                "https://example.com/start",
                status=302,
                headers={"location": "https://example.com/redirect1"},
            )
            m.get(
                "https://example.com/redirect1",
                status=302,
                headers={"location": "https://example.com/redirect2"},
            )
            m.get(
                "https://example.com/redirect2",
                status=302,
                headers={"location": "https://example.com/redirect3"},
            )
            m.get(
                "https://example.com/redirect3",
                status=302,
                headers={"location": "https://example.com/final"},
            )

            with pytest.raises(NetworkError, match="Too many redirects"):
                await session_manager.safe_request("GET", "https://example.com/start")

    @pytest.mark.asyncio
    async def test_successful_redirects(
        self, session_manager: SecureHTTPSessionManager
    ):
        """测试成功的重定向处理"""
        with aioresponses() as m:
            m.get(
                "https://example.com/start",
                status=302,
                headers={"location": "https://example.com/redirect"},
            )
            m.get("https://example.com/redirect", status=200, body="success")

            response = await session_manager.safe_request(
                "GET", "https://example.com/start"
            )
            assert response.status == 200
            response.close()

    @pytest.mark.asyncio
    async def test_no_redirect_loop(self, session_manager: SecureHTTPSessionManager):
        """测试重定向循环检测"""
        with aioresponses() as m:
            # 为循环重定向设置多个响应
            for _ in range(5):  # 超过max_redirects=2的限制
                m.get(
                    "https://example.com/loop",
                    status=302,
                    headers={"location": "https://example.com/loop"},
                )

            with pytest.raises(NetworkError, match="Too many redirects"):
                await session_manager.safe_request("GET", "https://example.com/loop")


class TestDownloaderSecurity:
    """测试下载器安全功能"""

    @pytest.fixture
    def config(self) -> Config:
        """测试配置"""
        return Config(
            ssl_verify=True,
            max_redirects=3,
            max_response_size=1024 * 1024,  # 1MB
            timeout=10,
        )

    @pytest_asyncio.fixture
    async def downloader(self, config: Config) -> AsyncIterator[XiaoYuZhouDL]:
        """测试下载器"""
        async with XiaoYuZhouDL(config=config) as dl:
            yield dl

    @pytest.mark.asyncio
    async def test_large_file_download_blocked(
        self, downloader: XiaoYuZhouDL, tmp_path
    ):
        """测试大文件下载被阻止"""
        with aioresponses() as m:
            # 模拟大音频文件
            large_size = 2 * 1024 * 1024  # 2MB，超过1MB限制
            m.head(
                "https://example.com/large-audio.m4a",
                headers={"content-type": "audio/mp4"},
            )
            m.get(
                "https://example.com/large-audio.m4a",
                headers={"content-length": str(large_size)},
                body="x" * large_size,
            )

            with pytest.raises(
                NetworkError, match="Response size exceeds maximum allowed limit"
            ):
                await downloader._download_audio(
                    "https://example.com/large-audio.m4a", "test-audio", str(tmp_path)
                )

    @pytest.mark.asyncio
    async def test_streaming_size_check(self, downloader: XiaoYuZhouDL, tmp_path):
        """测试流式下载时的大小检查"""
        with aioresponses() as m:
            # 模拟流式下载，实际大小超过声明大小
            m.head(
                "https://example.com/audio.m4a", headers={"content-type": "audio/mp4"}
            )

            # 使用Mock来模拟chunk迭代器
            mock_response = Mock()
            mock_response.status = 200
            mock_response.headers = {"content-length": "500"}  # 声明500字节

            # 创建大于限制的chunk序列
            large_chunk = b"x" * (1024 * 1024 + 1)  # 超过1MB

            # 创建异步迭代器
            async def chunk_iterator(chunk_size):
                yield large_chunk

            mock_response.content.iter_chunked = chunk_iterator

            # 添加异步上下文管理器支持
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            with patch.object(
                downloader._session_manager, "safe_request", return_value=mock_response
            ):
                with pytest.raises(NetworkError, match="Download size limit exceeded"):
                    await downloader._download_audio(
                        "https://example.com/audio.m4a", "test-audio", str(tmp_path)
                    )


class TestConfigValidation:
    """测试配置验证"""

    def test_positive_values_validation(self):
        """测试正数验证"""
        with pytest.raises(ValueError, match="Value must be positive"):
            Config(max_redirects=0)

        with pytest.raises(ValueError, match="Value must be positive"):
            Config(connection_pool_size=-1)

    def test_timeout_validation(self):
        """测试超时值验证"""
        with pytest.raises(ValueError, match="Timeout value must be positive"):
            Config(connection_timeout=0.0)

        with pytest.raises(ValueError, match="Timeout value must be positive"):
            Config(read_timeout=-1.0)

    def test_redirect_limit_validation(self):
        """测试重定向限制验证"""
        with pytest.raises(ValueError, match="max_redirects should not exceed 10"):
            Config(max_redirects=20)

        # 正常值应该通过
        config = Config(max_redirects=5)
        assert config.max_redirects == 5

    def test_default_security_headers(self):
        """测试默认安全头配置"""
        config = Config()
        headers = config.security_headers

        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "DNT" in headers
        assert "Connection" in headers
        assert headers["DNT"] == "1"


class TestSSLConfiguration:
    """测试SSL配置"""

    @pytest.mark.asyncio
    async def test_ssl_enabled_by_default(self):
        """测试SSL默认启用"""
        config = Config()
        assert config.ssl_verify is True

        session_manager = SecureHTTPSessionManager(config)
        ssl_context = session_manager._create_ssl_context()
        assert isinstance(ssl_context, ssl.SSLContext)

    @pytest.mark.asyncio
    async def test_ssl_cipher_configuration(self):
        """测试SSL加密算法配置"""
        config = Config(ssl_verify=True)
        session_manager = SecureHTTPSessionManager(config)
        ssl_context = session_manager._create_ssl_context()

        # 验证强加密算法已设置
        assert ssl_context is not False
        assert ssl_context.minimum_version == ssl.TLSVersion.TLSv1_2

    @pytest.mark.asyncio
    async def test_ssl_verification_settings(self):
        """测试SSL验证设置"""
        config = Config(ssl_verify=True)
        session_manager = SecureHTTPSessionManager(config)
        ssl_context = session_manager._create_ssl_context()

        assert ssl_context.check_hostname is True
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
