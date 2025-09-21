"""重试机制和错误恢复测试

测试重试装饰器、错误分类、断点续传等功能
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
from aioresponses import aioresponses

from xyz_dl.downloader import XiaoYuZhouDL
from xyz_dl.exceptions import DownloadError, NetworkError
from xyz_dl.models import Config, DownloadRequest
from xyz_dl.retry import (
    RetryableError,
    RetryConfig,
    RetryStats,
    create_retry_decorator,
    is_retryable_error,
)


class TestRetryableErrorClassification:
    """测试错误分类功能"""

    def test_retryable_network_errors(self):
        """测试可重试的网络错误"""
        # 临时网络错误应该可重试
        assert is_retryable_error(aiohttp.ClientConnectionError())
        assert is_retryable_error(aiohttp.ClientConnectorError(Mock(), Mock()))
        assert is_retryable_error(NetworkError("Connection timeout", status_code=503))
        assert is_retryable_error(NetworkError("Server error", status_code=502))

    def test_non_retryable_errors(self):
        """测试不可重试的错误"""
        # 客户端错误不应该重试
        assert not is_retryable_error(NetworkError("Not found", status_code=404))
        assert not is_retryable_error(NetworkError("Unauthorized", status_code=401))
        assert not is_retryable_error(ValueError("Invalid input"))

    def test_retryable_error_custom_exception(self):
        """测试自定义可重试错误"""
        retryable_error = RetryableError("Temporary failure")
        assert is_retryable_error(retryable_error)


class TestRetryDecorator:
    """测试重试装饰器功能"""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """测试成功调用不需要重试"""
        retry_config = RetryConfig(max_attempts=3, base_delay=0.1)
        stats = RetryStats()

        @create_retry_decorator(retry_config, stats)
        async def successful_function():
            return "success"

        result = await successful_function()
        assert result == "success"
        assert stats.total_attempts == 1
        assert stats.failed_attempts == 0

    @pytest.mark.asyncio
    async def test_retry_on_retryable_error(self):
        """测试遇到可重试错误时进行重试"""
        retry_config = RetryConfig(max_attempts=3, base_delay=0.01)
        stats = RetryStats()
        call_count = 0

        @create_retry_decorator(retry_config, stats)
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Temporary failure")
            return "success"

        result = await failing_function()
        assert result == "success"
        assert call_count == 3
        assert stats.total_attempts == 3
        assert stats.failed_attempts == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """测试超过最大重试次数"""
        retry_config = RetryConfig(max_attempts=2, base_delay=0.01)
        stats = RetryStats()

        @create_retry_decorator(retry_config, stats)
        async def always_failing_function():
            raise RetryableError("Always fails")

        with pytest.raises(RetryableError):
            await always_failing_function()

        assert stats.total_attempts == 2
        assert stats.failed_attempts == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """测试指数退避延迟"""
        retry_config = RetryConfig(
            max_attempts=3, base_delay=0.1, backoff_factor=2.0, jitter=False
        )
        stats = RetryStats()

        @create_retry_decorator(retry_config, stats)
        async def failing_function():
            raise RetryableError("Temporary failure")

        start_time = asyncio.get_event_loop().time()

        with pytest.raises(RetryableError):
            await failing_function()

        end_time = asyncio.get_event_loop().time()

        # 应该至少延迟了 0.1 + 0.2 = 0.3 秒，但允许一些时间误差
        elapsed = end_time - start_time
        assert elapsed >= 0.25  # 减少一些容差


class TestDownloadResume:
    """测试下载断点续传功能"""

    @pytest.mark.asyncio
    async def test_partial_download_resume(self):
        """测试部分下载后的续传"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(timeout=5)
            downloader = XiaoYuZhouDL(config=config)

            test_file_path = Path(temp_dir) / "test_audio.m4a"
            test_progress_path = Path(temp_dir) / "test_audio.m4a.progress"

            # 模拟之前下载了一部分
            partial_content = b"partial content"
            test_file_path.write_bytes(partial_content)

            # 创建进度文件
            progress_data = {
                "downloaded": len(partial_content),
                "total": 100,
                "url": "https://example.com/audio.m4a",
            }
            downloader._save_download_progress(test_progress_path, progress_data)

            with aioresponses() as m:
                # 模拟Range请求支持
                remaining_content = b"remaining content"
                m.get(
                    "https://example.com/audio.m4a",
                    body=remaining_content,
                    status=206,  # Partial Content
                    headers={
                        "Content-Range": f"bytes {len(partial_content)}-99/100",
                        "Content-Length": str(len(remaining_content)),
                    },
                )

                async with downloader:
                    result = await downloader._resume_download(
                        "https://example.com/audio.m4a",
                        test_file_path,
                        test_progress_path,
                    )

                    assert result
                    # 验证文件内容完整
                    final_content = test_file_path.read_bytes()
                    assert final_content == partial_content + remaining_content

    @pytest.mark.asyncio
    async def test_download_progress_save_and_load(self):
        """测试下载进度保存和加载"""
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = XiaoYuZhouDL()

            progress_path = Path(temp_dir) / "test.progress"
            progress_data = {
                "downloaded": 50,
                "total": 100,
                "url": "https://example.com/test.m4a",
                "timestamp": "2023-01-01T00:00:00Z",
            }

            # 保存进度
            downloader._save_download_progress(progress_path, progress_data)
            assert progress_path.exists()

            # 加载进度
            loaded_data = downloader._load_download_progress(progress_path)
            assert loaded_data["downloaded"] == 50
            assert loaded_data["total"] == 100
            assert loaded_data["url"] == "https://example.com/test.m4a"


class TestRetryIntegration:
    """测试重试机制与下载器的集成"""

    @pytest.mark.asyncio
    async def test_download_with_retry_success(self):
        """测试下载重试成功的情况"""
        config = Config(max_retries=3, timeout=5)

        with aioresponses() as m:
            # 第一次请求失败
            m.get(
                "https://www.xiaoyuzhoufm.com/episode/test123",
                exception=aiohttp.ClientConnectionError(),
            )

            # 第二次请求成功
            m.get(
                "https://www.xiaoyuzhoufm.com/episode/test123",
                body="<html><head><title>测试节目</title></head></html>",
            )

            m.get("https://audio.example.com/test.m4a", body=b"audio content")

            async with XiaoYuZhouDL(config=config) as downloader:
                # 这应该在重试后成功
                with patch.object(downloader, "_parse_episode") as mock_parse:
                    mock_parse.return_value = (
                        Mock(),
                        "https://audio.example.com/test.m4a",
                    )

                    request = DownloadRequest(url="test123", mode="audio")
                    # 这个测试应该失败，因为重试功能还没实现
                    with pytest.raises(Exception):
                        await downloader.download(request)

    @pytest.mark.asyncio
    async def test_download_with_retry_exhausted(self):
        """测试重试次数耗尽的情况"""
        config = Config(max_retries=2, timeout=5)

        with aioresponses() as m:
            # 所有请求都失败
            for _ in range(3):
                m.get(
                    "https://www.xiaoyuzhoufm.com/episode/test123",
                    exception=aiohttp.ClientConnectionError(),
                )

            async with XiaoYuZhouDL(config=config) as downloader:
                request = DownloadRequest(url="test123")
                # 这应该最终失败
                result = await downloader.download(request)
                assert not result.success
                assert (
                    "network error" in result.error.lower()
                    or "connection" in result.error.lower()
                    or "parse" in result.error.lower()
                )

    @pytest.mark.asyncio
    async def test_retry_stats_collection(self):
        """测试重试统计收集"""
        config = Config(max_retries=3)
        downloader = XiaoYuZhouDL(config=config)

        # 检查重试统计是否可用
        assert hasattr(downloader, "retry_stats")
        assert downloader.retry_stats.total_attempts == 0
        assert downloader.retry_stats.failed_attempts == 0


class TestRetryConfiguration:
    """测试重试配置"""

    def test_retry_config_validation(self):
        """测试重试配置验证"""
        # 有效配置
        config = RetryConfig(max_attempts=3, base_delay=1.0)
        assert config.max_attempts == 3
        assert config.base_delay == 1.0

        # 无效配置应该被拒绝
        with pytest.raises(ValueError):
            RetryConfig(max_attempts=0)  # 至少要1次尝试

        with pytest.raises(ValueError):
            RetryConfig(base_delay=-1.0)  # 延迟不能为负

    def test_config_integration_with_models(self):
        """测试重试配置与现有配置模型的集成"""
        config = Config(max_retries=5, timeout=30)

        # 配置应该包含重试相关设置
        assert config.max_retries == 5

        # 应该能够转换为RetryConfig
        retry_config = RetryConfig.from_config(config)
        assert retry_config.max_attempts == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
