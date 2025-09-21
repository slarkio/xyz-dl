"""流式下载器实现

提供大文件的流式下载功能，支持内存使用优化和速度限制
"""

import asyncio
import time
import psutil
from pathlib import Path
from typing import Callable, Optional, Any
from dataclasses import dataclass

import aiofiles
import aiohttp

from ..config import Config


@dataclass
class DownloadResult:
    """下载结果"""

    success: bool
    total_bytes: int = 0
    downloaded_bytes: int = 0
    streaming_used: bool = False
    peak_memory_mb: float = 0.0
    elapsed_time: float = 0.0
    average_speed_mbps: float = 0.0
    error_message: str = ""


class StreamingDownloader:
    """流式下载器

    Features:
    - 大文件流式下载（减少内存使用）
    - 下载速度限制
    - 内存使用监控
    - 进度回调支持
    """

    def __init__(
        self,
        config: Config,
        memory_threshold_mb: int = 10,
        speed_limit_mbps: Optional[float] = None,
    ):
        """初始化流式下载器

        Args:
            config: 应用配置
            memory_threshold_mb: 流式下载内存阈值(MB)
            speed_limit_mbps: 下载速度限制(Mbps)
        """
        self.config = config
        self.memory_threshold_mb = memory_threshold_mb
        self.speed_limit_mbps = speed_limit_mbps

        # 内存监控
        self._process = psutil.Process()
        self._peak_memory_mb = 0.0

    async def download_file(
        self,
        response: aiohttp.ClientResponse,
        file_path: Path,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> DownloadResult:
        """下载文件

        Args:
            response: HTTP响应对象
            file_path: 目标文件路径
            progress_callback: 进度回调函数 (downloaded, total, speed)

        Returns:
            下载结果
        """
        start_time = time.time()
        self._peak_memory_mb = 0.0

        try:
            # 获取文件大小
            content_length = response.headers.get("content-length")
            total_bytes = int(content_length) if content_length else 0

            # 决定是否使用流式下载
            use_streaming = self._should_use_streaming(total_bytes)

            if use_streaming:
                result = await self._stream_download(
                    response, file_path, total_bytes, progress_callback
                )
            else:
                result = await self._regular_download(
                    response, file_path, total_bytes, progress_callback
                )

            # 计算性能指标
            elapsed_time = time.time() - start_time
            average_speed_mbps = (
                (result.downloaded_bytes / (1024 * 1024)) / elapsed_time
                if elapsed_time > 0
                else 0
            )

            result.elapsed_time = elapsed_time
            result.average_speed_mbps = average_speed_mbps
            result.peak_memory_mb = self._peak_memory_mb
            result.streaming_used = use_streaming

            return result

        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=str(e),
                elapsed_time=time.time() - start_time,
                peak_memory_mb=self._peak_memory_mb,
            )

    def _should_use_streaming(self, file_size: int) -> bool:
        """判断是否应该使用流式下载

        Args:
            file_size: 文件大小（字节）

        Returns:
            True表示使用流式下载
        """
        if file_size <= 0:
            return False

        size_mb = file_size / (1024 * 1024)
        return size_mb > self.memory_threshold_mb

    async def _regular_download(
        self,
        response: aiohttp.ClientResponse,
        file_path: Path,
        total_bytes: int,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> DownloadResult:
        """常规下载（一次性读取）"""
        start_time = time.time()

        try:
            # 一次性读取所有内容
            content = await response.content.read()
            self._update_memory_stats()

            # 写入文件
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)

            downloaded_bytes = len(content)

            # 调用进度回调
            if progress_callback:
                elapsed = time.time() - start_time
                speed = downloaded_bytes / elapsed if elapsed > 0 else 0
                progress_callback(
                    downloaded_bytes, total_bytes or downloaded_bytes, speed
                )

            return DownloadResult(
                success=True,
                total_bytes=total_bytes or downloaded_bytes,
                downloaded_bytes=downloaded_bytes,
            )

        except Exception as e:
            return DownloadResult(success=False, error_message=str(e))

    async def _stream_download(
        self,
        response: aiohttp.ClientResponse,
        file_path: Path,
        total_bytes: int,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> DownloadResult:
        """流式下载"""
        downloaded_bytes = 0
        start_time = time.time()
        last_callback_time = start_time

        try:
            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in response.content.iter_chunked(
                    self.config.chunk_size
                ):
                    if not chunk:
                        break

                    # 写入块
                    await f.write(chunk)
                    downloaded_bytes += len(chunk)

                    # 更新内存统计
                    self._update_memory_stats()

                    # 速度限制
                    if self.speed_limit_mbps:
                        await self._apply_speed_limit(
                            downloaded_bytes, start_time, self.speed_limit_mbps
                        )

                    # 进度回调（限制频率）
                    current_time = time.time()
                    if progress_callback and (current_time - last_callback_time) >= 0.1:
                        elapsed = current_time - start_time
                        speed = downloaded_bytes / elapsed if elapsed > 0 else 0
                        progress_callback(downloaded_bytes, total_bytes, speed)
                        last_callback_time = current_time

            return DownloadResult(
                success=True, total_bytes=total_bytes, downloaded_bytes=downloaded_bytes
            )

        except Exception as e:
            return DownloadResult(
                success=False, downloaded_bytes=downloaded_bytes, error_message=str(e)
            )

    async def _apply_speed_limit(
        self, downloaded_bytes: int, start_time: float, limit_mbps: float
    ) -> None:
        """应用下载速度限制

        Args:
            downloaded_bytes: 已下载字节数
            start_time: 开始时间
            limit_mbps: 速度限制(MB/s)
        """
        elapsed_time = time.time() - start_time
        if elapsed_time <= 0:
            return

        # 计算当前速度
        current_speed_mbps = (downloaded_bytes / (1024 * 1024)) / elapsed_time

        # 如果超过限制，计算需要等待的时间
        if current_speed_mbps > limit_mbps:
            # 计算理想的下载时间
            ideal_time = (downloaded_bytes / (1024 * 1024)) / limit_mbps
            wait_time = ideal_time - elapsed_time

            if wait_time > 0:
                await asyncio.sleep(wait_time)

    def _update_memory_stats(self) -> None:
        """更新内存使用统计"""
        try:
            # 获取当前内存使用
            memory_info = self._process.memory_info()
            current_memory_mb = memory_info.rss / (1024 * 1024)

            # 更新峰值
            if current_memory_mb > self._peak_memory_mb:
                self._peak_memory_mb = current_memory_mb

        except Exception:
            # 忽略内存监控错误
            pass
