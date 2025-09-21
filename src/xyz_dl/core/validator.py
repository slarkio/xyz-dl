"""验证管理器模块

负责各种输入验证，包括URL验证、路径验证等。
从原有的验证逻辑中重构而来。
"""

from typing import Optional

from ..parsers import UrlValidator
from ..config import Config
from ..exceptions import ValidationError, ParseError
from .file_manager import FileManager


class ValidationManager:
    """验证管理器

    负责所有输入验证，包括:
    - URL验证和标准化
    - 路径验证和安全检查
    - 参数验证
    """

    def __init__(self, config: Config):
        """初始化验证管理器

        Args:
            config: 配置对象
        """
        self.config = config
        self.file_manager = FileManager(config)
        self.url_validator = UrlValidator()

    async def validate_url(self, url: str) -> bool:
        """验证URL格式和安全性

        Args:
            url: 要验证的URL

        Returns:
            True表示URL有效

        Raises:
            ValidationError: URL无效时
        """
        # 首先做基本的URL格式检查
        url = url.strip()
        if not url:
            raise ValidationError("Empty URL")

        # 检查是否包含明显的非法字符
        import re

        if re.search(r'[<>"|\\]', url):
            raise ValidationError(f"Invalid characters in URL: {url}")

        # 对于明显不是URL或episode ID的输入，直接拒绝
        # Episode ID应该是纯字母数字组合，不应该包含连字符或多个单词
        if not url.startswith("http"):
            # 检查是否为有效的episode ID格式
            if not re.match(r"^[a-zA-Z0-9]{6,24}$", url):
                raise ValidationError(f"Invalid URL format: {url}")

        try:
            # 使用现有的URL验证器
            normalized_url = self.url_validator.normalize_to_url(url)
            if not normalized_url:  # 额外检查确保返回了有效URL
                raise ValidationError(f"Invalid URL: {url}")
            return True
        except (ParseError, ValidationError):
            # 重新抛出为ValidationError以保持一致性
            raise ValidationError(f"Invalid URL: {url}")
        except Exception as e:
            # 其他异常也转换为ValidationError
            raise ValidationError(f"Invalid URL: {e}")

    async def validate_path(self, path: str) -> bool:
        """验证路径安全性

        Args:
            path: 要验证的路径

        Returns:
            True表示路径安全

        Raises:
            ValidationError: 路径不安全时
        """
        try:
            self.file_manager.validate_download_path(path)
            return True
        except Exception as e:
            raise ValidationError(f"Invalid path: {e}")

    def validate_filename(self, filename: str) -> bool:
        """验证文件名安全性

        Args:
            filename: 要验证的文件名

        Returns:
            True表示文件名安全

        Raises:
            ValidationError: 文件名不安全时
        """
        try:
            self.file_manager.ensure_safe_filename(filename)
            return True
        except Exception as e:
            raise ValidationError(f"Invalid filename: {e}")

    def validate_download_mode(self, mode: str) -> bool:
        """验证下载模式

        Args:
            mode: 下载模式

        Returns:
            True表示模式有效

        Raises:
            ValidationError: 模式无效时
        """
        valid_modes = ["audio", "md", "both", "url_only"]
        if mode not in valid_modes:
            raise ValidationError(
                f"Invalid download mode: {mode}. Valid modes: {valid_modes}"
            )
        return True
