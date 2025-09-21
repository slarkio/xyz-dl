"""测试重构后的模块结构

这个测试文件用于验证重构后的模块是否正确工作。
按照TDD原则，先写测试，然后实现功能。
"""

import pytest
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from unittest.mock import Mock, patch, AsyncMock

from src.xyz_dl.config import Config
from src.xyz_dl.models import DownloadRequest, DownloadResult, EpisodeInfo


class TestNetworkClient:
    """测试网络客户端模块"""

    @pytest.mark.asyncio
    async def test_http_client_creation(self):
        """测试HTTP客户端创建"""
        # 这个测试验证重构后的网络客户端可以正确创建
        try:
            from src.xyz_dl.core.network_client import HTTPClient
            config = Config()
            client = HTTPClient(config)
            assert client is not None
            assert client.config == config
        except ImportError:
            pytest.skip("HTTPClient not yet implemented")

    @pytest.mark.asyncio
    async def test_http_client_context_manager(self):
        """测试HTTP客户端上下文管理器"""
        try:
            from src.xyz_dl.core.network_client import HTTPClient
            config = Config()
            async with HTTPClient(config) as client:
                assert client._session is not None
        except ImportError:
            pytest.skip("HTTPClient not yet implemented")

    @pytest.mark.asyncio
    async def test_secure_request_method(self):
        """测试安全请求方法"""
        try:
            from src.xyz_dl.core.network_client import HTTPClient
            config = Config()

            # 更好的mock设置
            with patch('src.xyz_dl.core.network_client.aiohttp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.headers = {"content-length": "1000"}
                mock_response.closed = False

                mock_session.request.return_value = mock_response
                mock_session.close.return_value = None
                mock_session_class.return_value = mock_session

                async with HTTPClient(config) as client:
                    response = await client.safe_request("GET", "https://example.com")
                    assert response is not None
        except ImportError:
            pytest.skip("HTTPClient not yet implemented")


class TestFileManager:
    """测试文件管理器模块"""

    def test_file_manager_creation(self):
        """测试文件管理器创建"""
        try:
            from src.xyz_dl.core.file_manager import FileManager
            config = Config()
            manager = FileManager(config)
            assert manager is not None
            assert manager.config == config
        except ImportError:
            pytest.skip("FileManager not yet implemented")

    def test_path_validation(self):
        """测试路径验证功能"""
        try:
            from src.xyz_dl.core.file_manager import FileManager
            config = Config()
            manager = FileManager(config)

            # 测试安全路径
            safe_path = manager.validate_download_path("./downloads")
            assert isinstance(safe_path, Path)

            # 测试危险路径
            with pytest.raises(Exception):  # 应该抛出路径安全异常
                manager.validate_download_path("../../../etc/passwd")
        except ImportError:
            pytest.skip("FileManager not yet implemented")

    @pytest.mark.asyncio
    async def test_file_operations(self):
        """测试文件操作功能"""
        try:
            from src.xyz_dl.core.file_manager import FileManager
            config = Config()
            manager = FileManager(config)

            # 测试文件写入
            test_path = Path("/tmp/test_file.txt")
            await manager.write_file(test_path, "test content")

            # 测试文件存在检查
            exists = await manager.file_exists(test_path)
            assert exists is True

            # 清理
            test_path.unlink(missing_ok=True)
        except ImportError:
            pytest.skip("FileManager not yet implemented")


class TestProgressManager:
    """测试进度管理器模块"""

    def test_progress_manager_creation(self):
        """测试进度管理器创建"""
        try:
            from src.xyz_dl.core.progress_manager import ProgressManager
            manager = ProgressManager()
            assert manager is not None
        except ImportError:
            pytest.skip("ProgressManager not yet implemented")

    def test_progress_tracking(self):
        """测试进度跟踪功能"""
        try:
            from src.xyz_dl.core.progress_manager import ProgressManager
            manager = ProgressManager()

            # 创建进度跟踪任务
            task_id = manager.create_task("test download", total=1000)
            assert task_id is not None

            # 更新进度
            manager.update_progress(task_id, 500)
            progress = manager.get_progress(task_id)
            assert progress["completed"] == 500
            assert progress["total"] == 1000
        except ImportError:
            pytest.skip("ProgressManager not yet implemented")


class TestValidationManager:
    """测试验证管理器模块"""

    def test_validator_creation(self):
        """测试验证器创建"""
        try:
            from src.xyz_dl.core.validator import ValidationManager
            config = Config()
            validator = ValidationManager(config)
            assert validator is not None
        except ImportError:
            pytest.skip("ValidationManager not yet implemented")

    @pytest.mark.asyncio
    async def test_url_validation(self):
        """测试URL验证功能"""
        try:
            from src.xyz_dl.core.validator import ValidationManager
            config = Config()
            validator = ValidationManager(config)

            # 测试有效URL
            valid_url = "https://www.xiaoyuzhoufm.com/episode/12345"
            result = await validator.validate_url(valid_url)
            assert result is True

            # 测试无效URL
            with pytest.raises(Exception):  # 应该抛出验证异常
                await validator.validate_url("not-a-valid-url-at-all")
        except ImportError:
            pytest.skip("ValidationManager not yet implemented")


class TestFilenameUtils:
    """测试文件名工具模块"""

    def test_filename_sanitizer(self):
        """测试文件名清理器"""
        try:
            from src.xyz_dl.utils.filename_utils import FilenameSanitizer
            sanitizer = FilenameSanitizer()

            # 测试普通文件名
            clean_name = sanitizer.sanitize("normal filename.txt")
            assert clean_name == "normal filename.txt"

            # 测试包含非法字符的文件名
            dirty_name = "file<>:name*/?.txt"
            clean_name = sanitizer.sanitize(dirty_name)
            assert "<" not in clean_name
            assert ">" not in clean_name
            assert ":" not in clean_name
        except ImportError:
            pytest.skip("FilenameSanitizer not yet implemented")

    def test_filename_generator(self):
        """测试文件名生成器"""
        try:
            from src.xyz_dl.utils.filename_utils import FilenameGenerator
            generator = FilenameGenerator()

            # 创建模拟的节目信息
            episode_info = Mock()
            episode_info.title = "测试节目"
            episode_info.eid = "12345"
            episode_info.podcast.title = "测试播客"

            filename = generator.generate(episode_info)
            assert "12345" in filename
            assert "测试节目" in filename or "测试播客" in filename
        except ImportError:
            pytest.skip("FilenameGenerator not yet implemented")


class TestRefactoredDownloader:
    """测试重构后的主下载器"""

    @pytest.mark.asyncio
    async def test_refactored_downloader_initialization(self):
        """测试重构后的下载器初始化"""
        try:
            from src.xyz_dl.core.downloader_core import DownloaderCore
            config = Config()
            downloader = DownloaderCore(config)
            assert downloader is not None
            assert downloader.config == config
        except ImportError:
            pytest.skip("DownloaderCore not yet implemented")

    @pytest.mark.asyncio
    async def test_refactored_downloader_dependency_injection(self):
        """测试重构后的下载器依赖注入"""
        try:
            from src.xyz_dl.core.downloader_core import DownloaderCore
            from src.xyz_dl.core.network_client import HTTPClient
            from src.xyz_dl.core.file_manager import FileManager
            from src.xyz_dl.core.progress_manager import ProgressManager

            config = Config()

            # 创建依赖对象
            http_client = HTTPClient(config)
            file_manager = FileManager(config)
            progress_manager = ProgressManager()

            # 测试依赖注入
            downloader = DownloaderCore(
                config=config,
                http_client=http_client,
                file_manager=file_manager,
                progress_manager=progress_manager
            )

            assert downloader.http_client == http_client
            assert downloader.file_manager == file_manager
            assert downloader.progress_manager == progress_manager
        except ImportError:
            pytest.skip("DownloaderCore dependencies not yet implemented")

    @pytest.mark.asyncio
    async def test_backward_compatibility_interface(self):
        """测试向后兼容性接口"""
        # 原有的XiaoYuZhouDL类应该仍然可以工作
        from src.xyz_dl.downloader import XiaoYuZhouDL

        downloader = XiaoYuZhouDL()
        assert downloader is not None

        # 原有的API应该仍然可用
        assert hasattr(downloader, 'download')
        assert hasattr(downloader, 'download_sync')
        assert hasattr(downloader, '_generate_filename')
        assert hasattr(downloader, '_sanitize_filename')


class TestModuleIntegration:
    """测试模块集成"""

    @pytest.mark.asyncio
    async def test_modules_work_together(self):
        """测试重构后的模块能够协同工作"""
        try:
            from src.xyz_dl.core.downloader_core import DownloaderCore
            from src.xyz_dl.core.network_client import HTTPClient
            from src.xyz_dl.core.file_manager import FileManager
            from src.xyz_dl.core.progress_manager import ProgressManager
            from src.xyz_dl.core.validator import ValidationManager

            config = Config()

            # 创建所有组件
            http_client = HTTPClient(config)
            file_manager = FileManager(config)
            progress_manager = ProgressManager()
            validator = ValidationManager(config)

            # 创建下载器并注入依赖
            downloader = DownloaderCore(
                config=config,
                http_client=http_client,
                file_manager=file_manager,
                progress_manager=progress_manager,
                validator=validator
            )

            # 测试组件协作
            request = DownloadRequest(
                url="https://www.xiaoyuzhoufm.com/episode/test",
                mode="url_only"  # 只验证URL，不实际下载
            )

            # 这应该能够通过各个模块的协作完成
            result = await downloader.download(request)
            assert isinstance(result, DownloadResult)

        except ImportError:
            pytest.skip("Refactored modules not yet implemented")


class TestPerformanceAndSecurity:
    """测试性能和安全性"""

    @pytest.mark.asyncio
    async def test_refactored_modules_maintain_security(self):
        """测试重构后的模块保持安全性"""
        try:
            from src.xyz_dl.core.validator import ValidationManager
            config = Config()
            validator = ValidationManager(config)

            # 测试路径遍历防护
            with pytest.raises(Exception):
                await validator.validate_path("../../../etc/passwd")

            # 测试SSRF防护
            with pytest.raises(Exception):
                await validator.validate_url("http://127.0.0.1:8080/admin")

        except ImportError:
            pytest.skip("ValidationManager not yet implemented")

    def test_refactored_modules_reduce_complexity(self):
        """测试重构后的模块降低了复杂性"""
        # 这个测试检查每个模块的行数是否在合理范围内
        import inspect

        modules_to_check = [
            ("core.network_client", "HTTPClient"),
            ("core.file_manager", "FileManager"),
            ("core.progress_manager", "ProgressManager"),
            ("core.validator", "ValidationManager"),
            ("utils.filename_utils", "FilenameSanitizer")
        ]

        for module_name, class_name in modules_to_check:
            try:
                module = __import__(f"src.xyz_dl.{module_name}", fromlist=[class_name])
                cls = getattr(module, class_name)

                # 获取类的源码行数
                source_lines = inspect.getsourcelines(cls)[0]
                line_count = len(source_lines)

                # 每个模块应该在合理的大小范围内（比如不超过500行，比原来的1600行好很多）
                assert line_count < 500, f"{class_name} has {line_count} lines, too complex"

            except (ImportError, AttributeError):
                pytest.skip(f"{module_name}.{class_name} not yet implemented")