"""缓存管理器实现

提供基于LRU算法的内存缓存，支持ETag验证和内存限制
"""

import asyncio
import time
from collections import OrderedDict
from typing import Dict, Optional, Any
from dataclasses import dataclass

from ..config import Config


@dataclass
class CacheEntry:
    """缓存条目"""

    content: bytes
    headers: Dict[str, str]
    timestamp: float
    access_count: int = 0

    @property
    def size_bytes(self) -> int:
        """计算条目大小（字节）"""
        content_size = len(self.content)
        headers_size = sum(len(k) + len(v) for k, v in self.headers.items())
        return content_size + headers_size

    def is_expired(self, ttl_seconds: int) -> bool:
        """检查是否过期"""
        if ttl_seconds <= 0:
            return False
        return time.time() - self.timestamp > ttl_seconds


class CacheManager:
    """内存缓存管理器

    Features:
    - LRU淘汰算法
    - ETag验证支持
    - 内存大小限制
    - TTL过期机制
    - 缓存统计
    """

    def __init__(
        self,
        config: Config,
        max_entries: int = 100,
        max_memory_mb: int = 50,
        ttl_seconds: int = 300,  # 5分钟默认TTL
    ):
        """初始化缓存管理器

        Args:
            config: 应用配置
            max_entries: 最大缓存条目数
            max_memory_mb: 最大内存使用(MB)
            ttl_seconds: 缓存TTL(秒)
        """
        self.config = config
        self.max_entries = max_entries
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.ttl_seconds = ttl_seconds

        # 使用OrderedDict实现LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        # 统计信息
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "current_memory": 0}

    async def get(self, url: str) -> Optional[CacheEntry]:
        """获取缓存条目

        Args:
            url: 请求URL

        Returns:
            缓存条目或None
        """
        async with self._lock:
            entry = self._cache.get(url)

            if entry is None:
                self._stats["misses"] += 1
                return None

            # 检查是否过期
            if entry.is_expired(self.ttl_seconds):
                del self._cache[url]
                self._stats["misses"] += 1
                self._update_memory_stats()
                return None

            # 更新访问计数和位置（LRU）
            entry.access_count += 1
            self._cache.move_to_end(url)
            self._stats["hits"] += 1

            return entry

    async def set(self, url: str, content: bytes, headers: Dict[str, str]) -> None:
        """设置缓存条目

        Args:
            url: 请求URL
            content: 响应内容
            headers: 响应头
        """
        async with self._lock:
            entry = CacheEntry(
                content=content, headers=headers.copy(), timestamp=time.time()
            )

            # 检查单个条目是否超过内存限制
            if entry.size_bytes > self.max_memory_bytes:
                return  # 跳过太大的条目

            # 如果URL已存在，先删除旧条目
            if url in self._cache:
                del self._cache[url]

            # 添加新条目
            self._cache[url] = entry

            # 检查并执行LRU淘汰
            await self._evict_if_needed()

            self._update_memory_stats()

    async def is_etag_valid(self, url: str, etag: str) -> bool:
        """验证ETag是否匹配

        Args:
            url: 请求URL
            etag: ETag值

        Returns:
            True表示匹配，False表示不匹配
        """
        entry = await self.get(url)
        if entry is None:
            return False

        cached_etag = entry.headers.get("etag")
        return cached_etag == etag if cached_etag else False

    async def clear(self) -> None:
        """清空所有缓存"""
        async with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0, "current_memory": 0}

    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        async with self._lock:
            return {
                **self._stats,
                "entries": len(self._cache),
                "hit_rate": (
                    self._stats["hits"] / (self._stats["hits"] + self._stats["misses"])
                    if (self._stats["hits"] + self._stats["misses"]) > 0
                    else 0
                ),
            }

    async def _evict_if_needed(self) -> None:
        """执行LRU淘汰"""
        # 按条目数量淘汰
        while len(self._cache) > self.max_entries:
            oldest_url = next(iter(self._cache))
            del self._cache[oldest_url]
            self._stats["evictions"] += 1

        # 按内存大小淘汰
        current_memory = sum(entry.size_bytes for entry in self._cache.values())
        while current_memory > self.max_memory_bytes and self._cache:
            oldest_url = next(iter(self._cache))
            oldest_entry = self._cache[oldest_url]
            current_memory -= oldest_entry.size_bytes
            del self._cache[oldest_url]
            self._stats["evictions"] += 1

    def _update_memory_stats(self) -> None:
        """更新内存统计"""
        self._stats["current_memory"] = sum(
            entry.size_bytes for entry in self._cache.values()
        )
