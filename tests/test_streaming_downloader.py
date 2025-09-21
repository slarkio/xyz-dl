"""流式下载器测试"""

import asyncio
import tempfile
import pytest
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

from src.xyz_dl.performance.streaming_downloader import StreamingDownloader
from src.xyz_dl.config import Config


@pytest.fixture
def streaming_downloader():
    """创建流式下载器实例"""
    config = Config()
    return StreamingDownloader(config=config)


@pytest.fixture
def temp_file():
    """创建临时文件"""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    # 清理
    if temp_path.exists():
        temp_path.unlink()


@pytest.mark.asyncio
async def test_streaming_downloader_small_file(streaming_downloader, temp_file):
    """测试小文件下载（不使用流式）"""
    mock_response = AsyncMock()
    mock_response.headers = {"content-length": "1024"}  # 1KB
    mock_response.content.read = AsyncMock(return_value=b"x" * 1024)

    with patch('aiofiles.open') as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await streaming_downloader.download_file(
            mock_response, temp_file, progress_callback=None
        )

        assert result.success is True
        assert result.total_bytes == 1024
        assert result.streaming_used is False


@pytest.mark.asyncio
async def test_streaming_downloader_large_file(streaming_downloader, temp_file):
    """测试大文件下载（使用流式）"""
    large_size = 15 * 1024 * 1024  # 15MB
    mock_response = AsyncMock()
    mock_response.headers = {"content-length": str(large_size)}

    # 模拟分块读取
    chunk_size = streaming_downloader.config.chunk_size
    chunks = [b"x" * chunk_size for _ in range(large_size // chunk_size)]
    chunks.append(b"x" * (large_size % chunk_size))  # 最后一块

    # 创建异步迭代器
    async def mock_iter_chunked(size):
        for chunk in chunks:
            yield chunk

    mock_response.content.iter_chunked = mock_iter_chunked

    with patch('aiofiles.open') as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await streaming_downloader.download_file(
            mock_response, temp_file, progress_callback=None
        )

        assert result.success is True
        assert result.total_bytes == large_size
        assert result.streaming_used is True


@pytest.mark.asyncio
async def test_streaming_downloader_with_progress_callback(streaming_downloader, temp_file):
    """测试带进度回调的下载"""
    mock_response = AsyncMock()
    mock_response.headers = {"content-length": "1024"}

    # 使用常规下载而非流式下载，确保简单性
    mock_response.content.read = AsyncMock(return_value=b"x" * 1024)

    progress_calls = []

    def progress_callback(downloaded, total, speed):
        progress_calls.append((downloaded, total, speed))

    with patch('aiofiles.open') as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await streaming_downloader.download_file(
            mock_response, temp_file, progress_callback=progress_callback
        )

        assert result.success is True
        assert len(progress_calls) > 0  # 确保进度回调被调用
        assert progress_calls[-1][0] == 1024  # 最后一次回调显示完整下载


@pytest.mark.asyncio
async def test_streaming_downloader_memory_monitoring(streaming_downloader, temp_file):
    """测试内存监控功能"""
    mock_response = AsyncMock()
    mock_response.headers = {"content-length": "1048576"}  # 1MB

    chunks = [b"x" * 1024 for _ in range(1024)]

    async def mock_iter_chunked(size):
        for chunk in chunks:
            yield chunk

    mock_response.content.iter_chunked = mock_iter_chunked

    with patch('aiofiles.open') as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await streaming_downloader.download_file(
            mock_response, temp_file, progress_callback=None
        )

        assert result.success is True
        assert hasattr(result, 'peak_memory_mb')
        assert result.peak_memory_mb > 0


@pytest.mark.asyncio
async def test_streaming_downloader_speed_limit(temp_file):
    """测试下载速度限制"""
    config = Config()
    # 设置速度限制为 1MB/s
    streaming_downloader = StreamingDownloader(
        config=config,
        speed_limit_mbps=1.0
    )

    # 验证速度限制配置
    assert streaming_downloader.speed_limit_mbps == 1.0

    # 测试速度限制方法
    import time
    start_time = time.time()

    # 模拟已下载 2MB，应该触发速度限制
    await streaming_downloader._apply_speed_limit(
        downloaded_bytes=2 * 1024 * 1024,
        start_time=start_time,
        limit_mbps=1.0
    )

    elapsed_time = time.time() - start_time
    # 应该至少等待接近2秒
    assert elapsed_time >= 1.8


@pytest.mark.asyncio
async def test_streaming_downloader_memory_threshold():
    """测试内存阈值检查"""
    config = Config()
    streaming_downloader = StreamingDownloader(
        config=config,
        memory_threshold_mb=10  # 10MB阈值
    )

    # 测试是否应该使用流式下载
    assert streaming_downloader._should_use_streaming(15 * 1024 * 1024) is True  # 15MB
    assert streaming_downloader._should_use_streaming(5 * 1024 * 1024) is False   # 5MB


@pytest.mark.asyncio
async def test_streaming_downloader_error_handling(streaming_downloader, temp_file):
    """测试错误处理"""
    mock_response = AsyncMock()
    mock_response.headers = {"content-length": "1024"}

    # 模拟读取错误 - 使用常规下载
    mock_response.content.read = AsyncMock(side_effect=Exception("Network error"))

    with patch('aiofiles.open') as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await streaming_downloader.download_file(
            mock_response, temp_file, progress_callback=None
        )

        assert result.success is False
        assert "Network error" in result.error_message


@pytest.mark.asyncio
async def test_streaming_downloader_file_write_error(streaming_downloader, temp_file):
    """测试文件写入错误处理"""
    mock_response = AsyncMock()
    mock_response.headers = {"content-length": "1024"}
    mock_response.content.read = AsyncMock(return_value=b"x" * 1024)

    with patch('aiofiles.open') as mock_open:
        # 模拟文件写入错误
        mock_file = AsyncMock()
        mock_file.write = AsyncMock(side_effect=IOError("Disk full"))
        mock_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_open.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await streaming_downloader.download_file(
            mock_response, temp_file, progress_callback=None
        )

        assert result.success is False
        assert "Disk full" in result.error_message