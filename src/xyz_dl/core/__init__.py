"""重构后的核心模块

这个包包含了重构后的核心功能模块：
- downloader_core: 主下载器核心
- network_client: 网络请求客户端
- file_manager: 文件操作管理器
- progress_manager: 进度跟踪管理器
- validator: 输入验证管理器
"""

from .downloader_core import DownloaderCore
from .network_client import HTTPClient
from .file_manager import FileManager
from .progress_manager import ProgressManager, SimpleProgressManager
from .validator import ValidationManager

__all__ = [
    "DownloaderCore",
    "HTTPClient",
    "FileManager",
    "ProgressManager",
    "SimpleProgressManager",
    "ValidationManager",
]
