"""文件管理器模块

负责文件操作的安全管理，包括路径验证、文件读写、目录创建等。
从原有的XiaoYuZhouDL中提取文件操作相关功能。
"""

import os
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional, Union

import aiofiles

from ..config import Config
from ..exceptions import FileOperationError, PathSecurityError


class FileManager:
    """文件管理器

    负责所有文件操作的安全管理，包括:
    - 路径验证和安全检查
    - 文件读写操作
    - 目录创建和管理
    - 路径遍历攻击防护
    """

    # 最大路径长度限制
    MAX_PATH_LENGTH = 260  # Windows路径长度限制
    MAX_DECODE_ITERATIONS = 10  # Unicode解码最大迭代次数

    # 安全的临时目录前缀
    TEMP_DIRS = [
        "/tmp",
        "/var/folders",
        "/private/var/folders",
        "/private/tmp",
    ]

    def __init__(self, config: Config):
        """初始化文件管理器

        Args:
            config: 配置对象
        """
        self.config = config

    def validate_download_path(self, download_dir: str) -> Path:
        """验证下载路径安全性，防止路径遍历攻击

        Args:
            download_dir: 用户提供的下载目录路径

        Returns:
            安全的绝对路径

        Raises:
            PathSecurityError: 检测到路径遍历攻击或不安全路径
        """
        try:
            # 递归解码所有可能的编码格式
            decoded_path = self._decode_all_encodings(download_dir)

            # 创建Path对象并解析为绝对路径
            path = Path(decoded_path).resolve()

            # 检查路径长度限制
            if len(str(path)) > self.MAX_PATH_LENGTH:
                raise PathSecurityError(
                    f"Path too long: exceeds {self.MAX_PATH_LENGTH} characters limit",
                    path=str(path),
                    attack_type="path_length_limit",
                )

            # 检查是否包含危险的路径遍历模式
            self._check_path_traversal_attacks(decoded_path)

            # 检查是否为符号链接（Unix系统）
            if path.is_symlink():
                real_path = path.readlink()
                if self._is_dangerous_system_path(real_path):
                    raise PathSecurityError(
                        "Symlink points to dangerous system directory",
                        path=str(path),
                        attack_type="symlink_attack",
                    )

            # 检查是否指向危险的系统目录
            if self._is_dangerous_system_path(path):
                raise PathSecurityError(
                    "Access to system directories not allowed",
                    path=str(path),
                    attack_type="system_directory_access",
                )

            # 检查是否在安全区域内
            if not self._is_safe_area(path):
                raise PathSecurityError(
                    "Path outside of allowed safe areas",
                    path=str(path),
                    attack_type="unsafe_area_access",
                )

            return path

        except PathSecurityError:
            raise
        except (OSError, ValueError, RuntimeError) as e:
            raise PathSecurityError(
                f"Invalid path format: {e}",
                path=download_dir,
                attack_type="invalid_path",
            )

    def _decode_all_encodings(self, path: str) -> str:
        """递归解码所有可能的编码格式，防止编码攻击

        Args:
            path: 待解码的路径字符串

        Returns:
            完全解码后的路径字符串
        """
        prev_path = ""
        current_path = path

        # 定义特殊编码攻击模式
        attack_patterns = {
            "%c0%af": "/",  # 空字节攻击
            "%c1%9c": "\\",  # 反斜杠变体
        }

        for _ in range(self.MAX_DECODE_ITERATIONS):
            if prev_path == current_path:
                break
            prev_path = current_path

            # URL解码
            current_path = urllib.parse.unquote(current_path)

            # Unicode转义解码
            current_path = self._safe_unicode_decode(current_path)

            # 批量处理特殊编码模式
            for pattern, replacement in attack_patterns.items():
                current_path = current_path.replace(pattern, replacement)

        return current_path

    def _safe_unicode_decode(self, text: str) -> str:
        """安全的Unicode解码，忽略解码错误"""
        try:
            import codecs
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return codecs.decode(text, "unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return text

    def _check_path_traversal_attacks(self, decoded_path: str) -> None:
        """检查路径遍历攻击模式"""
        dangerous_patterns = [
            "../",
            "..\\",
            "/..",
            "\\..",
            "%2e%2e",  # URL编码的..
            "%2f",     # URL编码的/
            "%5c",     # URL编码的\
        ]

        for pattern in dangerous_patterns:
            if pattern.lower() in decoded_path.lower():
                raise PathSecurityError(
                    f"Path traversal attack detected: contains '{pattern}'",
                    path=decoded_path,
                    attack_type="path_traversal",
                )

    def _is_safe_temp_path(self, path: Path) -> bool:
        """检查路径是否在安全的临时目录中"""
        temp_paths = [
            *self.TEMP_DIRS,
            os.environ.get("TEMP", ""),
            os.environ.get("TMPDIR", ""),
        ]

        return any(
            temp_path and str(path).startswith(temp_path)
            for temp_path in temp_paths
            if temp_path
        )

    def _is_dangerous_system_path(self, path: Path) -> bool:
        """检查路径是否指向危险的系统目录

        Args:
            path: 要检查的路径

        Returns:
            True表示危险路径，False表示安全路径
        """
        path_str = str(path).lower().replace("\\", "/")

        # Unix系统危险目录
        unix_dangerous = [
            "/etc",
            "/bin",
            "/sbin",
            "/usr/bin",
            "/usr/sbin",
            "/var/log",
            "/root",
            "/boot",
            "/sys",
            "/proc",
        ]

        # Windows系统危险目录
        windows_dangerous = [
            "c:/windows",
            "c:/program files",
            "c:/program files (x86)",
            "c:/system32",
            "c:/syswow64",
            "windows/system32",
            "/c/windows",
        ]

        dangerous_paths = unix_dangerous + windows_dangerous

        for dangerous in dangerous_paths:
            if path_str.startswith(dangerous):
                return True

        return False

    def _is_safe_area(self, path: Path) -> bool:
        """检查路径是否在安全区域内"""
        # 检查是否在安全的临时目录中
        is_temp_safe = self._is_safe_temp_path(path)

        # 用户安全区域
        user_safe_areas = [
            Path.home(),  # 用户主目录
            Path.cwd(),   # 当前工作目录
        ]

        # 检查路径是否在安全区域内或其子目录中
        is_safe = is_temp_safe
        for safe_area in user_safe_areas:
            try:
                safe_area_resolved = safe_area.resolve()
                if str(path).startswith(str(safe_area_resolved)):
                    is_safe = True
                    break
            except (OSError, RuntimeError):
                continue

        return is_safe

    def ensure_safe_filename(self, filename: str) -> str:
        """确保文件名绝对安全，防止路径遍历攻击

        Args:
            filename: 待验证的文件名

        Returns:
            安全的文件名

        Raises:
            PathSecurityError: 检测到不安全的文件名
        """
        # 先检查原始filename是否包含路径分隔符
        dangerous_patterns = ["..", "/", "\\"]
        for pattern in dangerous_patterns:
            if pattern in filename:
                raise PathSecurityError(
                    f"Dangerous pattern '{pattern}' found in filename",
                    path=filename,
                    attack_type="path_traversal"
                )

        # 检查是否为绝对路径
        if (filename.startswith('/') or
            (len(filename) >= 3 and filename[1:3] == ':\\')):
            raise PathSecurityError(
                "Absolute path not allowed in filename",
                path=filename,
                attack_type="path_traversal"
            )

        # 使用Path.name确保只有文件名部分
        try:
            safe_filename = Path(filename).name
        except (OSError, ValueError) as e:
            raise PathSecurityError(
                f"Invalid filename: {filename}",
                path=filename,
                attack_type="invalid_filename"
            ) from e

        # 检查文件名中是否包含其他危险字符
        other_dangerous_chars = [":", "*", "?", "<", ">", "|"]
        for char in other_dangerous_chars:
            if char in safe_filename:
                raise PathSecurityError(
                    f"Dangerous character '{char}' found in filename",
                    path=filename,
                    attack_type="path_traversal"
                )

        # 检查是否为空或只包含点号和空格
        if not safe_filename or safe_filename.strip() == "" or safe_filename in [".", ".."]:
            raise PathSecurityError(
                "Empty or invalid filename",
                path=filename,
                attack_type="invalid_filename"
            )

        # 限制文件名长度
        if len(safe_filename) > 255:
            path_obj = Path(safe_filename)
            extension = path_obj.suffix
            name_without_ext = path_obj.stem

            if extension:
                available_length = 255 - len(extension)
                if available_length > 0:
                    safe_filename = name_without_ext[:available_length] + extension
                else:
                    safe_filename = safe_filename[:255]
            else:
                safe_filename = safe_filename[:255]

        return safe_filename

    async def write_file(self, file_path: Path, content: str, encoding: str = "utf-8") -> None:
        """异步写入文件

        Args:
            file_path: 文件路径
            content: 文件内容
            encoding: 文件编码，默认utf-8

        Raises:
            FileOperationError: 文件写入失败时
        """
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "w", encoding=encoding) as f:
                await f.write(content)
        except IOError as e:
            raise FileOperationError(
                f"File write failed: {e}",
                file_path=str(file_path),
                operation="write",
            )

    async def read_file(self, file_path: Path, encoding: str = "utf-8") -> str:
        """异步读取文件

        Args:
            file_path: 文件路径
            encoding: 文件编码，默认utf-8

        Returns:
            文件内容

        Raises:
            FileOperationError: 文件读取失败时
        """
        try:
            async with aiofiles.open(file_path, "r", encoding=encoding) as f:
                return await f.read()
        except IOError as e:
            raise FileOperationError(
                f"File read failed: {e}",
                file_path=str(file_path),
                operation="read",
            )

    async def file_exists(self, file_path: Path) -> bool:
        """检查文件是否存在

        Args:
            file_path: 文件路径

        Returns:
            文件是否存在
        """
        return file_path.exists()

    async def create_directory(self, dir_path: Path) -> None:
        """创建目录

        Args:
            dir_path: 目录路径

        Raises:
            FileOperationError: 目录创建失败时
        """
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise FileOperationError(
                f"Directory creation failed: {e}",
                file_path=str(dir_path),
                operation="mkdir",
            )

    def get_file_size(self, file_path: Path) -> int:
        """获取文件大小

        Args:
            file_path: 文件路径

        Returns:
            文件大小（字节）

        Raises:
            FileOperationError: 无法获取文件大小时
        """
        try:
            return file_path.stat().st_size
        except OSError as e:
            raise FileOperationError(
                f"Cannot get file size: {e}",
                file_path=str(file_path),
                operation="stat",
            )