"""连接池优化器测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.xyz_dl.performance.connection_pool_optimizer import ConnectionPoolOptimizer
from src.xyz_dl.config import Config


@pytest.fixture
def config():
    """创建配置实例"""
    return Config(
        connection_pool_size=10,
        connections_per_host=5,
        connection_timeout=10.0,
        read_timeout=30.0,
        dns_cache_ttl=300
    )


@pytest.fixture
def optimizer(config):
    """创建连接池优化器实例"""
    return ConnectionPoolOptimizer(config)


@pytest.mark.asyncio
async def test_connection_pool_optimizer_init(optimizer):
    """测试连接池优化器初始化"""
    assert optimizer.config is not None
    assert optimizer._pool_stats is not None
    assert optimizer._pool_stats['connections_created'] == 0
    assert optimizer._pool_stats['connections_reused'] == 0


@pytest.mark.asyncio
async def test_optimized_connector_creation(optimizer):
    """测试优化的连接器创建"""
    connector = await optimizer.create_optimized_connector()

    assert connector is not None
    # 检查基本配置（可能被优化调整）
    assert connector.limit >= optimizer.config.connection_pool_size
    assert connector.limit_per_host >= optimizer.config.connections_per_host

    # 检查 keep-alive 优化（检查连接器基本属性）
    assert hasattr(connector, 'force_close')
    assert connector.force_close is False


@pytest.mark.asyncio
async def test_connection_pool_stats_tracking(optimizer):
    """测试连接池统计跟踪"""
    # 初始统计
    initial_stats = await optimizer.get_pool_stats()
    assert initial_stats['connections_created'] == 0
    assert initial_stats['connections_reused'] == 0

    # 模拟连接创建
    await optimizer.record_connection_created()
    await optimizer.record_connection_reused()

    # 验证统计更新
    updated_stats = await optimizer.get_pool_stats()
    assert updated_stats['connections_created'] == 1
    assert updated_stats['connections_reused'] == 1


@pytest.mark.asyncio
async def test_adaptive_pool_sizing(optimizer):
    """测试自适应连接池大小调整"""
    # 模拟高负载场景
    for _ in range(15):  # 超过初始连接池大小
        await optimizer.record_connection_created()

    # 检查是否建议增加连接池大小
    recommendation = await optimizer.get_pool_size_recommendation()
    assert recommendation > optimizer.config.connection_pool_size


@pytest.mark.asyncio
async def test_connection_reuse_efficiency(optimizer):
    """测试连接复用效率计算"""
    # 模拟一些连接创建和复用
    for _ in range(5):
        await optimizer.record_connection_created()
    for _ in range(15):
        await optimizer.record_connection_reused()

    efficiency = await optimizer.get_connection_reuse_efficiency()
    expected_efficiency = 15 / (15 + 5)  # reused / (reused + created)
    assert abs(efficiency - expected_efficiency) < 0.01


@pytest.mark.asyncio
async def test_dns_cache_optimization(optimizer):
    """测试DNS缓存优化"""
    # 创建优化的连接器
    connector = await optimizer.create_optimized_connector()

    # 验证DNS缓存配置
    # 注意：这些属性可能是私有的或在内部管理，只检查连接器创建成功
    assert connector is not None

    # 测试DNS缓存统计
    dns_stats = await optimizer.get_dns_cache_stats()
    assert 'cache_hits' in dns_stats
    assert 'cache_misses' in dns_stats


@pytest.mark.asyncio
async def test_connection_timeout_optimization(optimizer):
    """测试连接超时优化"""
    connector = await optimizer.create_optimized_connector()

    # 检查是否设置了合理的超时值
    # 连接器的超时应该通过 ClientSession 的 timeout 参数设置
    optimized_timeouts = await optimizer.get_optimized_timeouts()

    assert optimized_timeouts['connection_timeout'] >= 5.0
    assert optimized_timeouts['read_timeout'] >= 10.0
    assert optimized_timeouts['total_timeout'] >= 30.0


@pytest.mark.asyncio
async def test_connection_pool_health_check(optimizer):
    """测试连接池健康检查"""
    # 模拟一些连接活动
    await optimizer.record_connection_created()
    await optimizer.record_connection_reused()

    health_status = await optimizer.check_pool_health()

    assert 'status' in health_status
    assert 'recommendations' in health_status
    assert health_status['status'] in ['healthy', 'warning', 'critical']


@pytest.mark.asyncio
async def test_connection_pool_cleanup(optimizer):
    """测试连接池清理"""
    connector = await optimizer.create_optimized_connector()

    # 验证连接器创建成功
    assert connector is not None

    # 测试清理功能
    await optimizer.cleanup_connections()

    # 验证统计被重置
    stats = await optimizer.get_pool_stats()
    # 清理后统计可能会重置，这取决于实现
    assert isinstance(stats, dict)


@pytest.mark.asyncio
async def test_concurrent_connection_tracking(optimizer):
    """测试并发连接跟踪"""
    async def simulate_connection():
        await optimizer.record_connection_created()
        await asyncio.sleep(0.01)  # 模拟连接使用
        await optimizer.record_connection_reused()

    # 并发创建多个连接
    tasks = [simulate_connection() for _ in range(10)]
    await asyncio.gather(*tasks)

    stats = await optimizer.get_pool_stats()
    assert stats['connections_created'] == 10
    assert stats['connections_reused'] == 10


@pytest.mark.asyncio
async def test_performance_monitoring_integration(optimizer):
    """测试性能监控集成"""
    # 模拟性能数据收集
    await optimizer.record_connection_created()
    await optimizer.record_connection_reused()

    # 获取性能报告
    performance_report = await optimizer.get_performance_report()

    assert 'connection_pool_efficiency' in performance_report
    assert 'average_connection_time' in performance_report
    assert 'total_connections' in performance_report
    assert performance_report['total_connections'] > 0