"""pytest配置文件"""

import pytest
import asyncio
import os
from pathlib import Path

# 导入测试工具
from .utils.test_data_manager import TestDataManager
from .utils.mock_http import HTTPMocker


@pytest.fixture(scope="session")
def event_loop():
    """为异步测试提供事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_html_content():
    """模拟的HTML内容"""
    return """
    <html>
        <head>
            <title>测试节目 - 测试播客 | 小宇宙</title>
            <meta name="description" content="这是一个测试节目的描述">
        </head>
        <body>
            <audio src="https://example.com/test-audio.mp3"></audio>
            <script>
                window.__INITIAL_STATE__ = {
                    "episodeInfo": {
                        "episode": {
                            "title": "测试节目",
                            "podcast": {
                                "title": "测试播客", 
                                "author": "测试作者"
                            },
                            "duration": 3600000,
                            "pubDate": "2025-01-01T00:00:00Z",
                            "eid": "test123",
                            "shownotes": "这是测试show notes"
                        }
                    }
                };
            </script>
        </body>
    </html>
    """


@pytest.fixture
def sample_episode_data():
    """样本节目数据"""
    return {
        "title": "测试节目",
        "podcast": {
            "title": "测试播客",
            "author": "测试作者"
        },
        "duration": 3600000,  # 1小时
        "pubDate": "2025-01-01T00:00:00Z",
        "eid": "test123",
        "shownotes": "这是测试show notes"
    }


@pytest.fixture(scope="session")
def test_data_manager():
    """测试数据管理器fixture - session级别"""
    return TestDataManager()


@pytest.fixture(scope="function")  
def http_mocker(test_data_manager):
    """HTTP Mock管理器fixture - function级别"""
    mocker = HTTPMocker(test_data_manager)
    mocker.start_mock()
    
    yield mocker
    
    # 清理
    mocker.stop_mock()


@pytest.fixture
def test_download_dir():
    """测试下载目录fixture"""
    test_dir = Path(__file__).parent / "test_data" / "downloads"
    test_dir.mkdir(parents=True, exist_ok=True)
    return str(test_dir)


@pytest.fixture
def sample_urls():
    """样本URL列表"""
    from .utils.test_data_manager import DEFAULT_TEST_URLS
    return DEFAULT_TEST_URLS