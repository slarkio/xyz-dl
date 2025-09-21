"""HTTP Mock工具

提供HTTP请求Mock功能，支持离线测试和异常场景模拟
"""

import os
from pathlib import Path
from typing import Dict, Optional, Union, Any
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlparse

import aiohttp
import pytest

from .test_data_manager import TestDataManager, DEFAULT_TEST_URLS


class MockResponse:
    """模拟HTTP响应对象"""

    def __init__(self, html_content: str, status: int = 200, reason: str = "OK"):
        self.status = status
        self.reason = reason
        self._html_content = html_content
        self._headers = {}

    async def text(self) -> str:
        """返回响应文本内容"""
        return self._html_content

    async def json(self) -> Dict[str, Any]:
        """返回JSON响应（如果适用）"""
        import json

        return json.loads(self._html_content)

    @property
    def headers(self) -> Dict[str, str]:
        """返回响应头"""
        return self._headers

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockHTTPSession:
    """模拟HTTP会话对象"""

    def __init__(self, data_manager: TestDataManager = None):
        """初始化Mock HTTP会话

        Args:
            data_manager: 测试数据管理器实例
        """
        self.data_manager = data_manager or TestDataManager()
        self._url_to_file = {}
        self._should_fail = {}  # URL -> 异常类型映射

        # 初始化URL到文件的映射
        self._setup_url_mapping()

    def _setup_url_mapping(self):
        """设置URL到文件的映射"""
        for i, url in enumerate(DEFAULT_TEST_URLS):
            # 从URL提取episode ID
            try:
                episode_id = url.split("/episode/")[-1].split("?")[0][:12]
                filename = f"episode_{episode_id}.html"
            except Exception:
                filename = f"episode_test_{i}.html"

            self._url_to_file[url] = filename

    def set_failure(self, url: str, exception: Exception):
        """设置特定URL应该失败

        Args:
            url: 要设置失败的URL
            exception: 要抛出的异常
        """
        self._should_fail[url] = exception

    def clear_failures(self):
        """清除所有失败设置"""
        self._should_fail.clear()

    def get_sync(self, url: str, timeout: int = None, **kwargs) -> MockResponse:
        """同步版本的GET请求，用于MockClientSession"""
        # 检查是否应该抛出异常
        if url in self._should_fail:
            raise self._should_fail[url]

        # 查找对应的fixture文件
        filename = self._url_to_file.get(url)
        if filename is None:
            # 未知URL，返回404
            return MockResponse("Page not found", status=404, reason="Not Found")

        try:
            # 同步加载HTML内容 - 需要使用同步版本
            html_content = self.data_manager.load_html_sync(filename)
            return MockResponse(html_content)
        except FileNotFoundError:
            # fixture文件不存在，返回404
            return MockResponse("Fixture not found", status=404, reason="Not Found")

    async def get(self, url: str, timeout: int = None, **kwargs) -> MockResponse:
        """模拟HTTP GET请求

        Args:
            url: 请求URL
            timeout: 超时时间（忽略）
            **kwargs: 其他参数（忽略）

        Returns:
            MockResponse实例

        Raises:
            配置的异常或默认的ClientError
        """
        # 检查是否应该抛出异常
        if url in self._should_fail:
            raise self._should_fail[url]

        # 查找对应的fixture文件
        filename = self._url_to_file.get(url)
        if filename is None:
            # 未知URL，返回404
            return MockResponse("Page not found", status=404, reason="Not Found")

        try:
            # 加载HTML内容
            html_content = await self.data_manager.load_html(filename)
            return MockResponse(html_content)
        except FileNotFoundError:
            # fixture文件不存在，返回404
            return MockResponse("Fixture not found", status=404, reason="Not Found")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class HTTPMocker:
    """HTTP Mock管理器"""

    def __init__(self, data_manager: TestDataManager = None):
        self.data_manager = data_manager or TestDataManager()
        self.original_client_session = None
        self.mock_session = None

    def start_mock(self):
        """开始Mock HTTP请求"""
        self.mock_session = MockHTTPSession(self.data_manager)

        # 保存原始的ClientSession
        self.original_client_session = aiohttp.ClientSession

        # 替换aiohttp.ClientSession
        aiohttp.ClientSession = MockClientSession
        MockClientSession._mock_session = self.mock_session

    def stop_mock(self):
        """停止Mock HTTP请求"""
        if self.original_client_session:
            aiohttp.ClientSession = self.original_client_session
            self.original_client_session = None

        if hasattr(MockClientSession, "_mock_session"):
            delattr(MockClientSession, "_mock_session")

        self.mock_session = None

    def set_failure(self, url: str, exception: Exception):
        """设置特定URL的失败"""
        if self.mock_session:
            self.mock_session.set_failure(url, exception)

    def clear_failures(self):
        """清除所有失败设置"""
        if self.mock_session:
            self.mock_session.clear_failures()


class MockClientSession:
    """模拟的ClientSession类"""

    _mock_session: Optional[MockHTTPSession] = None

    def __init__(self, *args, **kwargs):
        # 忽略所有参数
        pass

    def get(self, url: str, **kwargs):
        """模拟GET请求"""
        if self._mock_session is None:
            raise RuntimeError("Mock session not initialized")

        # 调用同步版本的get方法
        return self._mock_session.get_sync(url, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# pytest fixtures


@pytest.fixture
async def test_data_manager():
    """测试数据管理器fixture"""
    manager = TestDataManager()

    # 如果测试数据不存在，先获取
    fixtures = manager.list_fixtures()
    if not fixtures:
        print("正在获取测试数据...")
        await manager.setup_test_data(DEFAULT_TEST_URLS)

    yield manager


@pytest.fixture
async def http_mocker(test_data_manager):
    """HTTP Mock管理器fixture"""
    mocker = HTTPMocker(test_data_manager)
    mocker.start_mock()

    yield mocker

    mocker.stop_mock()


@pytest.fixture
async def mock_http_session(test_data_manager):
    """Mock HTTP会话fixture"""
    return MockHTTPSession(test_data_manager)


# 便捷函数


async def setup_mock_environment() -> HTTPMocker:
    """设置Mock环境

    Returns:
        配置好的HTTPMocker实例
    """
    # 创建测试数据管理器并确保数据存在
    data_manager = TestDataManager()
    fixtures = data_manager.list_fixtures()

    if not fixtures:
        print("正在获取测试数据...")
        await data_manager.setup_test_data(DEFAULT_TEST_URLS)

    # 创建并启动HTTP Mock
    mocker = HTTPMocker(data_manager)
    mocker.start_mock()

    return mocker


def create_network_error(message: str = "Network error") -> aiohttp.ClientError:
    """创建网络错误异常"""
    return aiohttp.ClientConnectionError(message)


def create_timeout_error(message: str = "Request timeout") -> aiohttp.ClientError:
    """创建超时错误异常"""
    return aiohttp.ServerTimeoutError(message)


def create_http_error(status: int, message: str = None) -> aiohttp.ClientError:
    """创建HTTP错误异常"""
    if message is None:
        message = f"HTTP {status} error"

    # 创建模拟的request_info对象
    from yarl import URL
    from aiohttp.client_reqrep import RequestInfo

    try:
        # 创建基本的RequestInfo对象
        url = URL("https://example.com")
        request_info = RequestInfo(
            url=url,
            method="GET",
            headers={},
            real_url=url
        )

        # 模拟不同的HTTP错误
        if status == 404:
            return aiohttp.ClientResponseError(request_info, (), status=status, message=message)
        elif status >= 500:
            return aiohttp.ClientResponseError(request_info, (), status=status, message=message)
        else:
            return aiohttp.ClientError(message)
    except Exception:
        # 如果RequestInfo创建失败，使用简单的ClientError
        return aiohttp.ClientError(f"HTTP {status}: {message}")
