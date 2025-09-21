"""连接池优化器实现

提供HTTP连接池的优化功能，包括连接复用、自适应大小调整和性能监控
"""

import asyncio
import ssl
import time
from typing import Dict, Any, Optional, Union
from collections import defaultdict

import aiohttp

from ..config import Config


class ConnectionPoolOptimizer:
    """连接池优化器

    Features:
    - Keep-alive连接复用优化
    - 自适应连接池大小调整
    - 连接状态监控和统计
    - DNS缓存优化
    - 性能监控集成
    """

    def __init__(self, config: Config):
        """初始化连接池优化器

        Args:
            config: 应用配置
        """
        self.config = config
        self._pool_stats = {
            "connections_created": 0,
            "connections_reused": 0,
            "connections_closed": 0,
            "connection_errors": 0,
            "start_time": time.time(),
        }
        self._dns_stats = {"cache_hits": 0, "cache_misses": 0}
        self._lock = asyncio.Lock()

    async def create_optimized_connector(
        self, ssl_context: Optional[Union[ssl.SSLContext, bool]] = None
    ) -> aiohttp.TCPConnector:
        """创建优化的TCP连接器

        Args:
            ssl_context: SSL上下文，如果未提供将使用默认安全设置

        Returns:
            优化的TCP连接器
        """
        if ssl_context is None:
            ssl_context = self._create_default_ssl_context()

        # 计算优化的连接池大小
        optimized_pool_size = await self._calculate_optimal_pool_size()
        optimized_per_host = await self._calculate_optimal_per_host_connections()

        # 创建优化的连接器
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            limit=optimized_pool_size,
            limit_per_host=optimized_per_host,
            ttl_dns_cache=self.config.dns_cache_ttl,
            use_dns_cache=True,
            enable_cleanup_closed=True,
            # Keep-alive优化
            keepalive_timeout=30,  # 保持连接30秒
            force_close=False,  # 允许连接复用
        )

        return connector

    def _create_default_ssl_context(self) -> Union[ssl.SSLContext, bool]:
        """创建默认SSL上下文"""
        if not self.config.ssl_verify:
            return False

        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers(
            "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
        )
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED

        return ssl_context

    async def _calculate_optimal_pool_size(self) -> int:
        """计算最优连接池大小"""
        base_size = self.config.connection_pool_size

        # 基于历史统计数据调整
        async with self._lock:
            total_connections = (
                self._pool_stats["connections_created"]
                + self._pool_stats["connections_reused"]
            )

            if total_connections > 0:
                reuse_ratio = self._pool_stats["connections_reused"] / total_connections

                # 如果复用率低，增加连接池大小
                if reuse_ratio < 0.3:
                    return min(base_size * 2, 50)  # 最大50个连接
                # 如果复用率很高，可以适当减少
                elif reuse_ratio > 0.8:
                    return max(base_size // 2, 5)  # 最小5个连接

            return base_size

    async def _calculate_optimal_per_host_connections(self) -> int:
        """计算每个主机的最优连接数"""
        base_per_host = self.config.connections_per_host

        # 对于小宇宙这样的单一主机应用，可以增加每主机连接数
        optimal_per_host = min(base_per_host + 2, 10)

        return optimal_per_host

    async def record_connection_created(self) -> None:
        """记录连接创建事件"""
        async with self._lock:
            self._pool_stats["connections_created"] += 1

    async def record_connection_reused(self) -> None:
        """记录连接复用事件"""
        async with self._lock:
            self._pool_stats["connections_reused"] += 1

    async def record_connection_closed(self) -> None:
        """记录连接关闭事件"""
        async with self._lock:
            self._pool_stats["connections_closed"] += 1

    async def record_connection_error(self) -> None:
        """记录连接错误事件"""
        async with self._lock:
            self._pool_stats["connection_errors"] += 1

    async def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        async with self._lock:
            return self._pool_stats.copy()

    async def get_pool_size_recommendation(self) -> int:
        """获取连接池大小建议"""
        return await self._calculate_optimal_pool_size()

    async def get_connection_reuse_efficiency(self) -> float:
        """获取连接复用效率"""
        async with self._lock:
            total_connections = (
                self._pool_stats["connections_created"]
                + self._pool_stats["connections_reused"]
            )

            if total_connections == 0:
                return 0.0

            return self._pool_stats["connections_reused"] / total_connections

    async def get_dns_cache_stats(self) -> Dict[str, int]:
        """获取DNS缓存统计"""
        async with self._lock:
            return self._dns_stats.copy()

    async def get_optimized_timeouts(self) -> Dict[str, float]:
        """获取优化的超时配置"""
        return {
            "connection_timeout": max(self.config.connection_timeout, 5.0),
            "read_timeout": max(self.config.read_timeout, 10.0),
            "total_timeout": max(self.config.timeout, 30.0),
            "keepalive_timeout": 30.0,
        }

    async def check_pool_health(self) -> Dict[str, Any]:
        """检查连接池健康状态"""
        stats = await self.get_pool_stats()
        efficiency = await self.get_connection_reuse_efficiency()

        # 计算健康状态
        total_connections = stats["connections_created"] + stats["connections_reused"]
        error_rate = stats["connection_errors"] / max(total_connections, 1)

        # 确定健康状态
        if error_rate > 0.1:  # 错误率超过10%
            status = "critical"
        elif efficiency < 0.3:  # 复用率低于30%
            status = "warning"
        else:
            status = "healthy"

        recommendations = []
        if efficiency < 0.5:
            recommendations.append("考虑增加连接池大小以提高复用率")
        if error_rate > 0.05:
            recommendations.append("检查网络稳定性和超时配置")

        return {
            "status": status,
            "efficiency": efficiency,
            "error_rate": error_rate,
            "recommendations": recommendations,
        }

    async def cleanup_connections(self) -> None:
        """清理连接池"""
        # 这个方法主要用于测试和维护
        # 实际的连接清理由aiohttp的连接器自动处理
        pass

    async def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        stats = await self.get_pool_stats()
        efficiency = await self.get_connection_reuse_efficiency()
        dns_stats = await self.get_dns_cache_stats()

        uptime = time.time() - stats["start_time"]
        total_connections = stats["connections_created"] + stats["connections_reused"]

        return {
            "connection_pool_efficiency": efficiency,
            "average_connection_time": uptime / max(total_connections, 1),
            "total_connections": total_connections,
            "connections_per_second": total_connections / max(uptime, 1),
            "error_rate": stats["connection_errors"] / max(total_connections, 1),
            "dns_cache_hit_rate": (
                dns_stats["cache_hits"]
                / max(dns_stats["cache_hits"] + dns_stats["cache_misses"], 1)
            ),
            "uptime_seconds": uptime,
        }
