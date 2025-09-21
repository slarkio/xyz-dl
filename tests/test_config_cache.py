"""配置缓存测试"""

import asyncio
import pytest
from unittest.mock import patch, Mock

from src.xyz_dl.performance.config_cache import ConfigCache
from src.xyz_dl.config import Config, ConfigManager


@pytest.fixture
def config_cache():
    """创建配置缓存实例"""
    return ConfigCache()


@pytest.mark.asyncio
async def test_config_cache_init(config_cache):
    """测试配置缓存初始化"""
    assert config_cache is not None
    assert config_cache._cache is None  # 初始时应该为空
    assert config_cache._cache_stats is not None


@pytest.mark.asyncio
async def test_config_cache_miss(config_cache):
    """测试配置缓存未命中"""
    # 初次获取配置（应该缓存未命中）
    with patch.object(ConfigManager, 'get_config', return_value=Config()) as mock_get:
        config = await config_cache.get_cached_config()

        assert config is not None
        assert mock_get.called

        # 验证统计
        stats = await config_cache.get_cache_stats()
        assert stats['misses'] == 1
        assert stats['hits'] == 0


@pytest.mark.asyncio
async def test_config_cache_hit(config_cache):
    """测试配置缓存命中"""
    with patch.object(ConfigManager, 'get_config', return_value=Config()) as mock_get:
        # 第一次获取（缓存未命中）
        config1 = await config_cache.get_cached_config()

        # 第二次获取（应该缓存命中）
        config2 = await config_cache.get_cached_config()

        assert config1 is config2  # 应该是同一个对象
        assert mock_get.call_count == 1  # 只调用一次

        # 验证统计
        stats = await config_cache.get_cache_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1


@pytest.mark.asyncio
async def test_config_cache_ttl_expiration(config_cache):
    """测试配置缓存TTL过期"""
    # 设置较短的TTL用于测试
    config_cache._ttl_seconds = 0.1

    with patch.object(ConfigManager, 'get_config', return_value=Config()) as mock_get:
        # 第一次获取
        config1 = await config_cache.get_cached_config()

        # 等待缓存过期
        await asyncio.sleep(0.15)

        # 第二次获取（应该重新加载）
        config2 = await config_cache.get_cached_config()

        assert mock_get.call_count == 2  # 应该调用两次

        # 验证统计
        stats = await config_cache.get_cache_stats()
        assert stats['misses'] == 2  # 两次都是缓存未命中


@pytest.mark.asyncio
async def test_config_cache_validation_caching(config_cache):
    """测试配置验证结果缓存"""
    config = Config()

    # 第一次验证
    is_valid1 = await config_cache.is_config_valid(config)

    # 第二次验证（应该使用缓存结果）
    is_valid2 = await config_cache.is_config_valid(config)

    assert is_valid1 == is_valid2
    assert is_valid1 is True  # 配置应该是有效的

    # 验证缓存统计
    validation_stats = await config_cache.get_validation_stats()
    assert validation_stats['cached_validations'] >= 1


@pytest.mark.asyncio
async def test_config_cache_invalidation(config_cache):
    """测试配置缓存失效"""
    with patch.object(ConfigManager, 'get_config', return_value=Config()) as mock_get:
        # 第一次获取
        config1 = await config_cache.get_cached_config()

        # 手动失效缓存
        await config_cache.invalidate_cache()

        # 第二次获取（应该重新加载）
        config2 = await config_cache.get_cached_config()

        assert mock_get.call_count == 2

        # 验证统计
        stats = await config_cache.get_cache_stats()
        assert stats['invalidations'] == 1


@pytest.mark.asyncio
async def test_config_cache_concurrent_access(config_cache):
    """测试并发访问配置缓存"""
    call_count = 0

    def mock_get_config():
        nonlocal call_count
        call_count += 1
        return Config()

    with patch.object(ConfigManager, 'get_config', side_effect=mock_get_config):
        # 并发获取配置
        tasks = [config_cache.get_cached_config() for _ in range(10)]
        configs = await asyncio.gather(*tasks)

        # 所有配置应该是同一个对象
        for config in configs[1:]:
            assert config is configs[0]

        # 应该只调用一次配置加载
        assert call_count == 1


@pytest.mark.asyncio
async def test_config_cache_error_handling(config_cache):
    """测试配置缓存错误处理"""
    with patch.object(ConfigManager, 'get_config', side_effect=Exception("Config error")):
        # 尝试获取配置（应该抛出异常）
        with pytest.raises(Exception, match="Config error"):
            await config_cache.get_cached_config()

        # 验证统计
        stats = await config_cache.get_cache_stats()
        assert stats['errors'] == 1


@pytest.mark.asyncio
async def test_config_cache_memory_monitoring(config_cache):
    """测试配置缓存内存监控"""
    # 获取一些配置
    await config_cache.get_cached_config()

    # 检查内存使用统计
    memory_stats = await config_cache.get_memory_stats()
    assert 'cache_size_bytes' in memory_stats
    assert 'entry_count' in memory_stats
    assert memory_stats['entry_count'] > 0


@pytest.mark.asyncio
async def test_config_cache_performance_metrics(config_cache):
    """测试配置缓存性能指标"""
    import time

    # 获取配置几次以产生性能数据
    for _ in range(3):
        await config_cache.get_cached_config()

    # 获取性能指标
    performance = await config_cache.get_performance_metrics()

    assert 'average_access_time_ms' in performance
    assert 'cache_hit_rate' in performance
    assert 'total_accesses' in performance
    assert performance['total_accesses'] >= 3


@pytest.mark.asyncio
async def test_config_cache_cleanup(config_cache):
    """测试配置缓存清理"""
    # 获取一些配置
    await config_cache.get_cached_config()

    # 验证缓存中有数据
    stats_before = await config_cache.get_cache_stats()
    assert stats_before['hits'] + stats_before['misses'] > 0

    # 清理缓存
    await config_cache.cleanup()

    # 验证缓存已清理
    memory_stats = await config_cache.get_memory_stats()
    assert memory_stats['entry_count'] == 0


@pytest.mark.asyncio
async def test_config_cache_size_limit(config_cache):
    """测试配置缓存大小限制"""
    # 设置较小的缓存大小限制
    config_cache._max_cache_size = 2

    # 创建多个不同的配置（模拟不同的配置文件）
    configs = []
    for i in range(5):
        config = Config(timeout=30+i)  # 稍微不同的配置
        is_valid = await config_cache.is_config_valid(config)
        configs.append((config, is_valid))

    # 验证验证缓存大小限制（注意这里测试的是验证缓存，不是配置缓存）
    memory_stats = await config_cache.get_memory_stats()
    assert memory_stats['validation_cache_size'] <= config_cache._max_validation_cache_size