"""XYZ-DL - 小宇宙播客下载器

现代化的异步Python包，支持小宇宙播客的音频和文本下载
"""

from .downloader import XiaoYuZhouDL, download_episode, download_episode_sync
from .models import (
    DownloadRequest,
    DownloadResult,
    DownloadProgress,
    EpisodeInfo,
    PodcastInfo,
    Config,
)
from .parsers import CompositeParser, JsonScriptParser, HtmlFallbackParser
from .config import get_config, load_config, save_config
from .exceptions import (
    XyzDlException,
    ValidationError,
    NetworkError,
    ParseError,
    DownloadError,
    FileOperationError,
    ConfigurationError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)
from .cli import main

# 版本信息
__version__ = "2.0.0"
__title__ = "xyz-dl"
__description__ = "小宇宙播客音频下载器 - 现代化异步版本"
__author__ = "Your Name"
__email__ = "your.email@example.com"
__license__ = "MIT"

# 公共API
__all__ = [
    # 核心类
    "XiaoYuZhouDL",
    # 数据模型
    "DownloadRequest",
    "DownloadResult",
    "DownloadProgress",
    "EpisodeInfo",
    "PodcastInfo",
    "Config",
    # 解析器
    "CompositeParser",
    "JsonScriptParser",
    "HtmlFallbackParser",
    # 便捷函数
    "download_episode",
    "download_episode_sync",
    # 配置管理
    "get_config",
    "load_config",
    "save_config",
    # 异常类
    "XyzDlException",
    "ValidationError",
    "NetworkError",
    "ParseError",
    "DownloadError",
    "FileOperationError",
    "ConfigurationError",
    "AuthenticationError",
    "NotFoundError",
    "RateLimitError",
    # 命令行入口
    "main",
    # 元数据
    "__version__",
]


# 向后兼容性 - 为旧代码提供兼容接口
class XiaoyuzhouDownloader:
    """向后兼容的下载器类 - 包装新的XiaoYuZhouDL类"""

    def __init__(self):
        self._downloader = None
        import warnings

        warnings.warn(
            "XiaoyuzhouDownloader is deprecated. Use XiaoYuZhouDL instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    def validate_url(self, url: str) -> bool:
        """验证URL格式"""
        from .parsers import UrlValidator

        return UrlValidator.validate_xiaoyuzhou_url(url)

    def extract_audio_info(self, url: str) -> dict:
        """提取音频信息 - 同步版本"""
        result = download_episode_sync(url)
        if result.success and result.episode_info:
            return {
                "audio_url": result.audio_path
                or "",  # 注意：这里返回的是本地路径，不是URL
                "filename": (
                    self._extract_filename_from_path(result.audio_path)
                    if result.audio_path
                    else ""
                ),
                "title": result.episode_info.title,
            }
        else:
            raise Exception(result.error or "Failed to extract audio info")

    def download_audio(
        self, audio_url: str, filename: str, download_dir: str = "."
    ) -> str:
        """下载音频文件 - 兼容接口"""
        # 注意：这个接口在新版本中语义不同，因为我们现在从URL解析所有信息
        # 这里简化处理，假设audio_url实际是episode URL
        result = download_episode_sync(audio_url, download_dir, "audio")
        if result.success and result.audio_path:
            return result.audio_path
        else:
            raise Exception(result.error or "Download failed")

    def download(self, url: str, download_dir: str = ".", mode: str = "both") -> dict:
        """主下载方法 - 兼容接口"""
        result = download_episode_sync(url, download_dir, mode)
        if result.success:
            return {"audio": result.audio_path, "md": result.md_path}
        else:
            raise Exception(result.error or "Download failed")

    def _extract_filename_from_path(self, file_path: str) -> str:
        """从文件路径提取文件名"""
        from pathlib import Path

        return Path(file_path).stem


# 添加到公共API
__all__.append("XiaoyuzhouDownloader")


def print_version_info():
    """打印版本信息"""
    print(f"{__title__} v{__version__}")
    print(f"{__description__}")
    print(f"Author: {__author__}")
    print(f"License: {__license__}")


def get_version() -> str:
    """获取版本号"""
    return __version__


if __name__ == "__main__":
    print_version_info()
