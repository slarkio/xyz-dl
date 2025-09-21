"""异步适配器模块

解决事件循环嵌套问题，提供智能的同步/异步包装器
支持在 Jupyter Notebook、IDE、和其他已有事件循环环境中使用
"""

from __future__ import annotations

import asyncio
import functools
import threading
import concurrent.futures
from typing import Any, Awaitable, Callable, Optional, TypeVar, Union
import warnings

T = TypeVar("T")


class EventLoopState:
    """事件循环状态检测器"""

    @staticmethod
    def is_running() -> bool:
        """检测是否在运行中的事件循环内"""
        try:
            loop = asyncio.get_running_loop()
            return loop is not None
        except RuntimeError:
            return False

    @staticmethod
    def get_current_loop() -> Optional[asyncio.AbstractEventLoop]:
        """获取当前事件循环"""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    @staticmethod
    def has_event_loop() -> bool:
        """检查是否有可用的事件循环"""
        try:
            return asyncio.get_event_loop() is not None
        except RuntimeError:
            return False


class AsyncAdapter:
    """智能异步适配器

    根据当前环境自动选择最合适的执行策略：
    - 在已有事件循环中：使用线程池执行
    - 在无事件循环环境中：创建新的事件循环
    - 在 Jupyter/IPython 环境中：使用 nest_asyncio 或线程池
    """

    def __init__(self, use_thread_pool: bool = True):
        """初始化适配器

        Args:
            use_thread_pool: 在事件循环中是否使用线程池（推荐True）
        """
        self.use_thread_pool = use_thread_pool
        self._thread_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None

    def run_sync(self, coro: Awaitable[T]) -> T:
        """智能运行协程，自动适配环境

        Args:
            coro: 要执行的协程

        Returns:
            协程的执行结果

        Raises:
            Exception: 协程执行过程中的异常
        """
        if EventLoopState.is_running():
            # 在已有事件循环中，使用线程池
            return self._run_in_thread_pool(coro)
        else:
            # 没有事件循环，创建新的
            return self._run_with_new_loop(coro)

    def _run_with_new_loop(self, coro: Awaitable[T]) -> T:
        """在新事件循环中运行协程"""
        try:
            return asyncio.run(coro)
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                # 备用方案：使用线程池
                warnings.warn(
                    "Falling back to thread pool execution due to event loop conflict",
                    RuntimeWarning,
                )
                return self._run_in_thread_pool(coro)
            raise

    def _run_in_thread_pool(self, coro: Awaitable[T]) -> T:
        """在线程池中运行协程"""
        if self._thread_pool is None:
            self._thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="xyz-dl-async"
            )

        def run_in_thread():
            """在新线程中创建事件循环并运行协程"""
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()

        future = self._thread_pool.submit(run_in_thread)
        return future.result()

    def __del__(self):
        """清理线程池资源"""
        if self._thread_pool:
            self._thread_pool.shutdown(wait=False)


# 全局适配器实例
_default_adapter = AsyncAdapter()


def smart_run(coro: Awaitable[T]) -> T:
    """智能运行协程的便捷函数

    自动检测环境并选择最合适的执行策略

    Args:
        coro: 要执行的协程

    Returns:
        协程的执行结果
    """
    return _default_adapter.run_sync(coro)


def async_to_sync(func: Callable[..., Awaitable[T]]) -> Callable[..., T]:
    """装饰器：将异步函数转换为智能同步函数

    使用示例:
    ```python
    @async_to_sync
    async def download_episode(url: str) -> DownloadResult:
        # 异步实现
        pass

    # 现在可以在任何环境中同步调用
    result = download_episode("https://...")
    ```
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> T:
        coro = func(*args, **kwargs)
        return smart_run(coro)

    return wrapper


class SyncAsyncBridge:
    """同步/异步桥接器

    为同一功能提供同步和异步两种接口
    """

    def __init__(self, async_func: Callable[..., Awaitable[T]]):
        """初始化桥接器

        Args:
            async_func: 异步实现函数
        """
        self.async_func = async_func
        self.sync_func = async_to_sync(async_func)

    def __call__(self, *args, **kwargs) -> T:
        """同步调用"""
        return self.sync_func(*args, **kwargs)

    async def async_call(self, *args, **kwargs) -> T:
        """异步调用"""
        return await self.async_func(*args, **kwargs)


def create_sync_async_bridge(
    async_func: Callable[..., Awaitable[T]],
) -> SyncAsyncBridge[T]:
    """创建同步/异步桥接器的便捷函数"""
    return SyncAsyncBridge(async_func)


# Jupyter Notebook 特殊支持
def try_enable_jupyter_support() -> bool:
    """尝试启用 Jupyter Notebook 支持

    如果安装了 nest_asyncio，则启用它来支持嵌套事件循环

    Returns:
        True 如果成功启用，False 如果不可用
    """
    try:
        import nest_asyncio

        nest_asyncio.apply()
        return True
    except ImportError:
        return False


def get_execution_context() -> str:
    """获取当前执行环境描述

    用于调试和日志记录

    Returns:
        环境描述字符串
    """
    if EventLoopState.is_running():
        loop = EventLoopState.get_current_loop()
        if loop:
            return f"existing_loop:{type(loop).__name__}"
        return "existing_loop:unknown"

    if EventLoopState.has_event_loop():
        return "available_loop"

    return "no_loop"
