"""配置缓存实现

提供配置对象的缓存机制，避免重复验证和加载
"""

import asyncio
import time
import hashlib
from typing import Dict, Any, Optional
from collections import OrderedDict

from ..config import Config, ConfigManager, config_manager


class ConfigCache:
    """配置缓存管理器

    Features:
    - 配置对象缓存
    - 配置验证结果缓存
    - TTL过期机制
    - 内存使用限制
    - 性能监控
    """

    def __init__(
        self,
        ttl_seconds: int = 300,  # 5分钟TTL
        max_cache_size: int = 10,
        max_validation_cache_size: int = 100,
    ):
        """初始化配置缓存

        Args:
            ttl_seconds: 缓存TTL（秒）
            max_cache_size: 最大缓存大小
            max_validation_cache_size: 最大验证缓存大小
        """
        self._ttl_seconds = ttl_seconds
        self._max_cache_size = max_cache_size
        self._max_validation_cache_size = max_validation_cache_size

        # 主配置缓存
        self._cache: Optional[Config] = None
        self._cache_timestamp: float = 0

        # 验证结果缓存 {config_hash: (is_valid, timestamp)}
        self._validation_cache: OrderedDict[str, tuple[bool, float]] = OrderedDict()

        # 统计信息
        self._cache_stats = {"hits": 0, "misses": 0, "invalidations": 0, "errors": 0}

        self._validation_stats = {"cached_validations": 0, "new_validations": 0}

        # 性能监控
        self._access_times = []
        self._lock = asyncio.Lock()

    async def get_cached_config(self) -> Config:
        """获取缓存的配置对象

        Returns:
            配置对象

        Raises:
            Exception: 配置加载失败时
        """
        async with self._lock:
            start_time = time.time()

            try:
                # 检查缓存是否有效
                if self._is_cache_valid():
                    self._cache_stats["hits"] += 1
                    self._record_access_time(start_time)
                    return self._cache

                # 缓存未命中，重新加载
                self._cache_stats["misses"] += 1
                self._cache = config_manager.get_config()
                self._cache_timestamp = time.time()

                self._record_access_time(start_time)
                return self._cache

            except Exception as e:
                self._cache_stats["errors"] += 1
                raise e

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._cache is None:
            return False

        if self._ttl_seconds <= 0:
            return True

        return (time.time() - self._cache_timestamp) < self._ttl_seconds

    async def is_config_valid(self, config: Config) -> bool:
        """检查配置是否有效（带缓存）

        Args:
            config: 配置对象

        Returns:
            True表示配置有效
        """
        async with self._lock:
            # 计算配置哈希
            config_hash = self._calculate_config_hash(config)

            # 检查验证缓存
            if config_hash in self._validation_cache:
                is_valid, timestamp = self._validation_cache[config_hash]

                # 检查缓存是否过期
                if (time.time() - timestamp) < self._ttl_seconds:
                    # 更新LRU位置
                    self._validation_cache.move_to_end(config_hash)
                    self._validation_stats["cached_validations"] += 1
                    return is_valid

                # 缓存过期，删除
                del self._validation_cache[config_hash]

            # 执行实际验证
            is_valid = self._validate_config(config)

            # 缓存验证结果
            self._validation_cache[config_hash] = (is_valid, time.time())
            self._validation_stats["new_validations"] += 1

            # 执行LRU淘汰
            self._evict_validation_cache_if_needed()

            return is_valid

    def _calculate_config_hash(self, config: Config) -> str:
        """计算配置对象的哈希值"""
        # 将配置转换为字符串并计算哈希
        config_str = str(config.model_dump())
        return hashlib.md5(config_str.encode()).hexdigest()

    def _validate_config(self, config: Config) -> bool:
        """验证配置对象"""
        try:
            # 基本验证：检查必要字段
            if config.timeout <= 0:
                return False
            if config.max_retries < 0:
                return False
            if config.chunk_size <= 0:
                return False

            # 检查字符串字段
            if not config.user_agent.strip():
                return False

            # 所有验证通过
            return True

        except Exception:
            return False

    def _evict_validation_cache_if_needed(self) -> None:
        """淘汰验证缓存（LRU）"""
        while len(self._validation_cache) > self._max_validation_cache_size:
            oldest_key = next(iter(self._validation_cache))
            del self._validation_cache[oldest_key]

    async def invalidate_cache(self) -> None:
        """手动失效缓存"""
        async with self._lock:
            self._cache = None
            self._cache_timestamp = 0
            self._validation_cache.clear()
            self._cache_stats["invalidations"] += 1

    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        async with self._lock:
            return self._cache_stats.copy()

    async def get_validation_stats(self) -> Dict[str, Any]:
        """获取验证统计信息"""
        async with self._lock:
            return self._validation_stats.copy()

    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存使用统计"""
        async with self._lock:
            cache_size = 0
            entry_count = 0

            # 计算主缓存大小
            if self._cache is not None:
                cache_size += len(str(self._cache.model_dump()))
                entry_count += 1

            # 计算验证缓存大小
            for key, (is_valid, timestamp) in self._validation_cache.items():
                cache_size += len(key) + 16  # 估算大小
                entry_count += 1

            return {
                "cache_size_bytes": cache_size,
                "entry_count": entry_count,
                "validation_cache_size": len(self._validation_cache),
            }

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        async with self._lock:
            total_accesses = self._cache_stats["hits"] + self._cache_stats["misses"]
            hit_rate = (
                self._cache_stats["hits"] / total_accesses if total_accesses > 0 else 0
            )

            avg_access_time = (
                sum(self._access_times) / len(self._access_times)
                if self._access_times
                else 0
            )

            return {
                "cache_hit_rate": hit_rate,
                "total_accesses": total_accesses,
                "average_access_time_ms": avg_access_time * 1000,
                "validation_cache_efficiency": (
                    self._validation_stats["cached_validations"]
                    / max(
                        self._validation_stats["cached_validations"]
                        + self._validation_stats["new_validations"],
                        1,
                    )
                ),
            }

    async def cleanup(self) -> None:
        """清理缓存"""
        async with self._lock:
            self._cache = None
            self._cache_timestamp = 0
            self._validation_cache.clear()
            self._access_times.clear()

    def _record_access_time(self, start_time: float) -> None:
        """记录访问时间"""
        access_time = time.time() - start_time
        self._access_times.append(access_time)

        # 保持最近100次访问记录
        if len(self._access_times) > 100:
            self._access_times.pop(0)
