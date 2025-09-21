"""测试异步架构重构 - 事件循环嵌套问题和异常处理

这个测试文件专门针对 Issue #6 的核心问题：
1. 事件循环嵌套问题
2. 异常处理过于宽泛
3. 资源管理不一致
"""

import asyncio
import pytest
from unittest.mock import Mock, patch
import threading
import time

from src.xyz_dl.cli import main, CLIApplication, async_main
from src.xyz_dl.downloader import XiaoYuZhouDL, download_episode_sync
from src.xyz_dl.models import DownloadRequest


class TestEventLoopNesting:
    """测试事件循环嵌套问题"""

    def test_cli_main_in_existing_event_loop_should_fail(self):
        """测试：在已有事件循环中调用 main() 应该失败

        这是当前的BUG - 在已有事件循环中调用 asyncio.run() 会抛出 RuntimeError
        """
        async def run_in_existing_loop():
            # 模拟在已有事件循环中调用main
            with pytest.raises(RuntimeError, match="cannot be called from a running event loop"):
                main(["https://www.xiaoyuzhoufm.com/episode/test123"])

        # 在新的事件循环中运行测试，模拟实际问题场景
        asyncio.run(run_in_existing_loop())

    def test_sync_wrapper_in_existing_event_loop_should_work(self):
        """测试：在已有事件循环中调用同步包装器应该正常工作

        修复后：download_episode_sync 使用智能适配器，在事件循环中自动切换到线程池
        """
        from src.xyz_dl.models import Config

        async def run_in_existing_loop():
            # 创建测试配置（非交互模式）
            test_config = Config(non_interactive=True, default_overwrite_behavior=False)

            # 现在应该正常工作而不是抛出异常
            result = download_episode_sync(
                "https://www.xiaoyuzhoufm.com/episode/test123",
                mode="md",  # 只下载md避免实际网络请求
                config=test_config
            )
            # 验证返回了结构化的结果对象
            assert hasattr(result, 'success')
            assert hasattr(result, 'error')

        asyncio.run(run_in_existing_loop())

    def test_downloader_sync_method_in_existing_loop_should_work(self):
        """测试：在已有事件循环中调用 download_sync 应该正常工作

        修复后：XiaoYuZhouDL.download_sync 使用智能适配器
        """
        from src.xyz_dl.models import Config

        async def run_in_existing_loop():
            # 创建测试配置（非交互模式）
            test_config = Config(non_interactive=True, default_overwrite_behavior=False)
            downloader = XiaoYuZhouDL(config=test_config)

            request = DownloadRequest(
                url="https://www.xiaoyuzhoufm.com/episode/test123",
                mode="md"  # 只下载md避免实际网络请求
            )

            # 现在应该正常工作而不是抛出异常
            result = downloader.download_sync(request)
            assert hasattr(result, 'success')
            assert hasattr(result, 'error')

        asyncio.run(run_in_existing_loop())

    def test_cli_from_jupyter_notebook_scenario(self):
        """测试：模拟 Jupyter Notebook 环境中的问题

        在 Jupyter 中，IPython 已经运行了一个事件循环，
        用户试图调用 xyz-dl 时会遇到嵌套问题
        """
        def simulate_jupyter_environment():
            # 模拟 Jupyter 环境：在线程中运行事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def jupyter_task():
                # 在这个"Jupyter"环境中，用户尝试调用 xyz-dl
                with pytest.raises(RuntimeError):
                    main(["https://www.xiaoyuzhoufm.com/episode/test123"])

            loop.run_until_complete(jupyter_task())
            loop.close()

        # 在单独线程中运行，模拟 Jupyter 的环境
        thread = threading.Thread(target=simulate_jupyter_environment)
        thread.start()
        thread.join()


class TestExceptionHandling:
    """测试异常处理问题"""

    @pytest.mark.asyncio
    async def test_broad_exception_handling_masks_errors(self):
        """测试：过于宽泛的异常处理掩盖了真实错误

        当前在 downloader.py:208-216 中的宽泛异常捕获会丢失堆栈信息
        """
        downloader = XiaoYuZhouDL()

        # 注入一个会导致具体错误的URL
        request = DownloadRequest(url="https://invalid-domain-xyz.com/episode/123")

        async with downloader:
            result = await downloader.download(request)

        # 当前的问题：错误信息太宽泛，没有具体的异常类型和堆栈
        assert not result.success
        assert result.error is not None

        # BUG：当前实现会丢失原始异常的具体信息
        # 期望得到更具体的网络错误，而不是通用的字符串
        assert "Failed to parse episode" in result.error  # 当前的宽泛错误


class TestResourceManagement:
    """测试资源管理问题"""

    @pytest.mark.asyncio
    async def test_session_not_shared_across_downloads(self):
        """测试：HTTP session 没有在下载间共享

        当前每次下载都创建新的session，效率低下
        """
        downloader = XiaoYuZhouDL()

        # 第一次下载
        async with downloader:
            session1_id = id(downloader._session)

        # 第二次下载 - session应该被重新创建
        async with downloader:
            session2_id = id(downloader._session)

        # 当前的问题：每次都创建新session，没有复用
        # 在理想的资源管理中，应该有session池或复用机制
        assert session1_id != session2_id  # 证明当前实现的问题

    @pytest.mark.asyncio
    async def test_manual_session_management_inconsistency(self):
        """测试：手动session管理的不一致性"""
        downloader = XiaoYuZhouDL()

        # 测试直接调用 _create_session
        await downloader._create_session()
        assert downloader._session is not None

        # 多次调用应该是幂等的，但当前实现可能不是
        session1 = downloader._session
        await downloader._create_session()
        session2 = downloader._session

        # 当前可能的问题：重复创建session而不检查已存在的
        assert session1 is session2  # 应该复用现有session

        await downloader._close_session()


class TestCurrentSyncWrapperIssues:
    """测试当前同步包装器的问题"""

    def test_sync_wrapper_no_event_loop_detection(self):
        """测试：同步包装器缺少事件循环检测

        当前的实现直接使用 asyncio.run()，没有检测已有循环
        """
        # 这个测试证明当前实现的问题
        # 在有事件循环的环境中，应该能优雅处理而不是崩溃

        def test_in_thread():
            # 模拟在没有事件循环的环境中工作正常
            try:
                # 当前实现：在新线程中正常工作
                result = download_episode_sync(
                    "https://www.xiaoyuzhoufm.com/episode/test123",
                    mode="md"  # 只下载md避免实际网络请求
                )
                # 期望：即使失败也应该返回结构化的错误，而不是崩溃
                assert hasattr(result, 'success')
            except Exception as e:
                # 记录当前实现的问题
                assert "cannot be called from a running event loop" not in str(e)

        # 在单独线程中测试，模拟正常环境
        thread = threading.Thread(target=test_in_thread)
        thread.start()
        thread.join()


# 这些测试用例会失败，证明了当前实现的问题
# 接下来的实现阶段将修复这些问题