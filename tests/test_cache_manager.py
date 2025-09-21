"""缓存管理器测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock

from src.xyz_dl.cache.cache_manager import CacheManager, CacheEntry
from src.xyz_dl.config import Config


@pytest.fixture
def cache_manager():
    """创建缓存管理器实例"""
    config = Config()
    return CacheManager(config=config)


@pytest.mark.asyncio
async def test_cache_manager_get_miss():
    """测试缓存未命中"""
    cache_manager = CacheManager(Config())
    result = await cache_manager.get("http://example.com/test")
    assert result is None


@pytest.mark.asyncio
async def test_cache_manager_set_and_get():
    """测试缓存设置和获取"""
    cache_manager = CacheManager(Config())

    # 设置缓存
    content = b"test content"
    headers = {"content-type": "text/html", "etag": "test-etag"}
    await cache_manager.set("http://example.com/test", content, headers)

    # 获取缓存
    result = await cache_manager.get("http://example.com/test")
    assert result is not None
    assert result.content == content
    assert result.headers["etag"] == "test-etag"


@pytest.mark.asyncio
async def test_cache_manager_etag_validation():
    """测试ETag验证功能"""
    cache_manager = CacheManager(Config())

    # 设置缓存
    content = b"test content"
    headers = {"etag": "test-etag"}
    await cache_manager.set("http://example.com/test", content, headers)

    # 验证ETag匹配
    is_valid = await cache_manager.is_etag_valid("http://example.com/test", "test-etag")
    assert is_valid is True

    # 验证ETag不匹配
    is_valid = await cache_manager.is_etag_valid("http://example.com/test", "different-etag")
    assert is_valid is False


@pytest.mark.asyncio
async def test_cache_manager_lru_eviction():
    """测试LRU缓存淘汰机制"""
    config = Config()
    cache_manager = CacheManager(config=config, max_entries=2)

    # 添加第一个缓存项
    await cache_manager.set("url1", b"content1", {"etag": "etag1"})

    # 添加第二个缓存项
    await cache_manager.set("url2", b"content2", {"etag": "etag2"})

    # 添加第三个缓存项（应该淘汰第一个）
    await cache_manager.set("url3", b"content3", {"etag": "etag3"})

    # 验证第一个已被淘汰
    result1 = await cache_manager.get("url1")
    assert result1 is None

    # 验证第二和第三个仍存在
    result2 = await cache_manager.get("url2")
    result3 = await cache_manager.get("url3")
    assert result2 is not None
    assert result3 is not None


@pytest.mark.asyncio
async def test_cache_manager_memory_limit():
    """测试内存限制功能"""
    config = Config()
    cache_manager = CacheManager(config=config, max_memory_mb=1)  # 1MB限制

    # 尝试添加超大内容（2MB）
    large_content = b"x" * (2 * 1024 * 1024)
    await cache_manager.set("large", large_content, {})

    # 应该没有被缓存
    result = await cache_manager.get("large")
    assert result is None


@pytest.mark.asyncio
async def test_cache_entry_expiration():
    """测试缓存项过期功能"""
    import time

    config = Config()
    cache_manager = CacheManager(config=config, ttl_seconds=1)  # 1秒过期

    # 设置缓存
    await cache_manager.set("url", b"content", {})

    # 立即获取应该成功
    result = await cache_manager.get("url")
    assert result is not None

    # 等待过期
    await asyncio.sleep(1.1)

    # 再次获取应该失败
    result = await cache_manager.get("url")
    assert result is None


@pytest.mark.asyncio
async def test_cache_clear():
    """测试缓存清空功能"""
    cache_manager = CacheManager(Config())

    # 添加一些缓存项
    await cache_manager.set("url1", b"content1", {})
    await cache_manager.set("url2", b"content2", {})

    # 清空缓存
    await cache_manager.clear()

    # 验证缓存已清空
    result1 = await cache_manager.get("url1")
    result2 = await cache_manager.get("url2")
    assert result1 is None
    assert result2 is None


@pytest.mark.asyncio
async def test_cache_statistics():
    """测试缓存统计功能"""
    cache_manager = CacheManager(Config())

    # 初始统计
    stats = await cache_manager.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["entries"] == 0

    # 缓存未命中
    await cache_manager.get("nonexistent")
    stats = await cache_manager.get_stats()
    assert stats["misses"] == 1

    # 添加缓存并命中
    await cache_manager.set("url", b"content", {})
    await cache_manager.get("url")

    stats = await cache_manager.get_stats()
    assert stats["hits"] == 1
    assert stats["entries"] == 1