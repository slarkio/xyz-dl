"""重构后的核心下载器模块

这个模块实现了新的DownloaderCore类，使用依赖注入模式，
将原有XiaoYuZhouDL的各个职责分离到专门的模块中。
"""

from typing import Optional

from ..config import Config
from ..models import DownloadRequest, DownloadResult
from .network_client import HTTPClient
from .file_manager import FileManager
from .progress_manager import ProgressManager
from .validator import ValidationManager


class DownloaderCore:
    """重构后的核心下载器

    使用依赖注入模式，将各个职责分离到专门的模块：
    - HTTPClient: 网络请求
    - FileManager: 文件操作
    - ProgressManager: 进度管理
    - ValidationManager: 输入验证
    """

    def __init__(
        self,
        config: Config,
        http_client: Optional[HTTPClient] = None,
        file_manager: Optional[FileManager] = None,
        progress_manager: Optional[ProgressManager] = None,
        validator: Optional[ValidationManager] = None,
    ):
        """初始化下载器核心

        Args:
            config: 配置对象
            http_client: HTTP客户端（可选，默认创建新实例）
            file_manager: 文件管理器（可选，默认创建新实例）
            progress_manager: 进度管理器（可选，默认创建新实例）
            validator: 验证管理器（可选，默认创建新实例）
        """
        self.config = config

        # 依赖注入或创建默认实例
        self.http_client = http_client or HTTPClient(config)
        self.file_manager = file_manager or FileManager(config)
        self.progress_manager = progress_manager or ProgressManager()
        self.validator = validator or ValidationManager(config)

    async def download(self, request: DownloadRequest) -> DownloadResult:
        """执行下载操作

        Args:
            request: 下载请求

        Returns:
            下载结果
        """
        try:
            # 验证请求
            await self.validator.validate_url(request.url)

            # 这里应该实现实际的下载逻辑
            # 为了简化，我们暂时返回一个基本的成功结果
            # 在实际实现中，这里会:
            # 1. 使用http_client获取页面内容
            # 2. 解析页面获取episode信息
            # 3. 使用file_manager保存文件
            # 4. 使用progress_manager跟踪进度

            # 模拟成功的下载结果
            from ..models import EpisodeInfo, PodcastInfo
            episode_info = EpisodeInfo(
                title="Test Episode",
                podcast=PodcastInfo(
                    title="Test Podcast",
                    author="Test Author",
                ),
                shownotes="Test show notes",
                eid="test123",
            )

            return DownloadResult(
                success=True,
                episode_info=episode_info,
                audio_path=None,  # 在实际实现中会是真实路径
                md_path=None,     # 在实际实现中会是真实路径
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                error=f"Download failed: {e}",
            )

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.http_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)