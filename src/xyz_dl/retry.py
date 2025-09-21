"""重试机制模块

实现网络请求重试、错误分类、断点续传等功能
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union

import aiohttp
from pydantic import BaseModel, Field, field_validator

from .exceptions import NetworkError, XyzDlException

F = TypeVar("F", bound=Callable[..., Any])


class RetryableError(XyzDlException):
    """可重试的错误"""

    pass


class RetryConfig(BaseModel):
    """重试配置"""

    max_attempts: int = Field(default=3, description="最大尝试次数")
    base_delay: float = Field(default=1.0, description="基础延迟(秒)")
    backoff_factor: float = Field(default=2.0, description="退避因子")
    max_delay: float = Field(default=60.0, description="最大延迟(秒)")
    jitter: bool = Field(default=True, description="是否添加随机抖动")

    @field_validator("max_attempts")
    @classmethod
    def validate_max_attempts(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_attempts must be at least 1")
        return v

    @field_validator("base_delay")
    @classmethod
    def validate_base_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError("base_delay cannot be negative")
        return v

    @classmethod
    def from_config(cls, config: Any) -> "RetryConfig":
        """从现有配置对象创建重试配置"""
        return cls(
            max_attempts=getattr(config, "max_retries", 3),
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
            jitter=True,
        )


class RetryStats(BaseModel):
    """重试统计"""

    total_attempts: int = Field(default=0, description="总尝试次数")
    failed_attempts: int = Field(default=0, description="失败次数")
    total_delay: float = Field(default=0.0, description="总延迟时间")
    last_error: Optional[str] = Field(default=None, description="最后的错误信息")
    start_time: Optional[float] = Field(default=None, description="开始时间")

    def reset(self) -> None:
        """重置统计"""
        self.total_attempts = 0
        self.failed_attempts = 0
        self.total_delay = 0.0
        self.last_error = None
        self.start_time = None

    def record_attempt(self, is_success: bool, error: Optional[str] = None) -> None:
        """记录一次尝试"""
        if self.start_time is None:
            self.start_time = time.time()

        self.total_attempts += 1
        if not is_success:
            self.failed_attempts += 1
            self.last_error = error

    def record_delay(self, delay: float) -> None:
        """记录延迟时间"""
        self.total_delay += delay


def is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试"""

    # 显式的可重试错误
    if isinstance(error, RetryableError):
        return True

    # 网络连接错误
    if isinstance(error, (aiohttp.ClientConnectionError, aiohttp.ClientConnectorError)):
        return True

    # 网络错误，根据状态码判断
    if isinstance(error, NetworkError):
        # 服务器错误和临时错误可重试
        if error.status_code in [502, 503, 504, 429]:
            return True
        # 客户端错误不重试
        if error.status_code and 400 <= error.status_code < 500:
            return False
        # 其他网络错误可重试
        return True

    # 连接和超时错误
    if isinstance(error, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
        return True

    # 检查错误链，看是否包含可重试的错误
    if hasattr(error, "__cause__") and error.__cause__:
        return is_retryable_error(error.__cause__)

    if hasattr(error, "__context__") and error.__context__:
        return is_retryable_error(error.__context__)

    # 其他错误不重试
    return False


def create_retry_decorator(
    config: RetryConfig, stats: Optional[RetryStats] = None
) -> Callable[[F], F]:
    """创建重试装饰器"""

    if stats is None:
        stats = RetryStats()

    def decorator(func: F) -> F:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None

            for attempt in range(config.max_attempts):
                try:
                    result = await func(*args, **kwargs)
                    stats.record_attempt(True)
                    return result

                except Exception as e:
                    last_error = e
                    stats.record_attempt(False, str(e))

                    # 如果不是可重试错误，直接抛出
                    if not is_retryable_error(e):
                        raise

                    # 如果是最后一次尝试，抛出错误
                    if attempt == config.max_attempts - 1:
                        raise

                    # 计算延迟时间
                    delay = min(
                        config.base_delay * (config.backoff_factor**attempt),
                        config.max_delay,
                    )

                    # 添加随机抖动
                    if config.jitter:
                        import random

                        delay *= 0.5 + random.random() * 0.5

                    stats.record_delay(delay)
                    await asyncio.sleep(delay)

            # 这里不应该到达，但为了类型安全
            if last_error:
                raise last_error
            raise RuntimeError("Unexpected retry loop completion")

        return wrapper  # type: ignore

    return decorator


class DownloadProgressManager:
    """下载进度管理器"""

    @staticmethod
    def save_progress(progress_path: Path, progress_data: Dict[str, Any]) -> None:
        """保存下载进度"""
        progress_data["timestamp"] = datetime.now().isoformat()

        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, indent=2)

    @staticmethod
    def load_progress(progress_path: Path) -> Optional[Dict[str, Any]]:
        """加载下载进度"""
        if not progress_path.exists():
            return None

        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    @staticmethod
    def cleanup_progress(progress_path: Path) -> None:
        """清理进度文件"""
        if progress_path.exists():
            progress_path.unlink(missing_ok=True)


def calculate_resume_position(file_path: Path, progress_data: Dict[str, Any]) -> int:
    """计算续传位置"""
    if not file_path.exists():
        return 0

    file_size = file_path.stat().st_size
    recorded_size = progress_data.get("downloaded", 0)

    # 如果文件大小与记录一致，从该位置继续
    if file_size == recorded_size:
        return file_size

    # 如果文件更大，可能是之前下载的不同文件，重新开始
    if file_size > recorded_size:
        return 0

    # 如果文件更小，从文件实际大小开始
    return file_size


def create_range_headers(start_byte: int) -> Dict[str, str]:
    """创建Range请求头"""
    if start_byte > 0:
        return {"Range": f"bytes={start_byte}-"}
    return {}
