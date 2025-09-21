"""文件名工具模块

负责文件名生成和清理，从原有的文件名处理逻辑中重构而来。
"""

import re
from datetime import datetime
from typing import Optional

from ..models import EpisodeInfo
from ..filename_sanitizer import create_filename_sanitizer


class FilenameSanitizer:
    """文件名清理器

    负责清理文件名中的非法字符，确保跨平台兼容性。
    """

    def __init__(self, secure: bool = True):
        """初始化文件名清理器

        Args:
            secure: 是否使用安全模式
        """
        self._sanitizer = create_filename_sanitizer(secure=secure)

    def sanitize(self, filename: str, max_length: int = 200) -> str:
        """清理文件名

        Args:
            filename: 原始文件名
            max_length: 最大长度

        Returns:
            清理后的文件名
        """
        return self._sanitizer.sanitize(filename, max_length)


class FilenameGenerator:
    """文件名生成器

    负责根据节目信息生成标准化的文件名。
    """

    DEFAULT_UNKNOWN_PODCAST = "未知播客"
    DEFAULT_UNKNOWN_AUTHOR = "未知作者"

    def __init__(self, sanitizer: Optional[FilenameSanitizer] = None):
        """初始化文件名生成器

        Args:
            sanitizer: 文件名清理器，如果为None则使用默认清理器
        """
        self.sanitizer = sanitizer or FilenameSanitizer()

    def generate(self, episode_info: EpisodeInfo) -> str:
        """生成文件名

        Args:
            episode_info: 节目信息

        Returns:
            生成的文件名（不包含扩展名）
        """
        episode_id = episode_info.eid or self._extract_id_from_title(episode_info.title)
        title = episode_info.title
        podcast_title = episode_info.podcast.title or self.DEFAULT_UNKNOWN_PODCAST

        # 解析标题格式
        episode_name, host_name = self._parse_episode_title(title, podcast_title)

        # 构建文件名
        if host_name and episode_name and host_name != self.DEFAULT_UNKNOWN_PODCAST:
            filename = f"{episode_id}_{host_name} - {episode_name}"
        else:
            filename = f"{episode_id}_{title}"

        return self.sanitizer.sanitize(filename)

    def _parse_episode_title(self, title: str, podcast_title: str) -> tuple[str, str]:
        """解析节目标题，提取节目名和主播名

        Args:
            title: 节目标题
            podcast_title: 播客标题

        Returns:
            (节目名, 主播名) 元组
        """
        if " - " in title:
            parts = title.split(" - ", 1)
            episode_name = parts[0].strip()
            host_name = parts[1].strip() if len(parts) > 1 else podcast_title
        else:
            episode_name = title
            host_name = podcast_title

        return episode_name, host_name

    def _extract_id_from_title(self, title: str) -> str:
        """从标题中提取ID（备用方案）"""
        return str(int(datetime.now().timestamp()))

    def create_safe_filename(self, title: str, author: str, extension: str = ".md") -> str:
        """创建安全的文件名

        Args:
            title: 节目标题
            author: 作者/主播名
            extension: 文件扩展名

        Returns:
            清理后的安全文件名
        """
        # 构建基础文件名：作者 - 标题
        if author and author != self.DEFAULT_UNKNOWN_AUTHOR:
            base_name = f"{author} - {title}"
        else:
            base_name = title

        # 清理文件名并添加扩展名
        safe_name = self.sanitizer.sanitize(base_name)
        return safe_name + extension


# 便捷函数
def create_filename_generator(secure: bool = True) -> FilenameGenerator:
    """创建文件名生成器的便捷函数

    Args:
        secure: 是否使用安全模式

    Returns:
        文件名生成器实例
    """
    sanitizer = FilenameSanitizer(secure=secure)
    return FilenameGenerator(sanitizer=sanitizer)