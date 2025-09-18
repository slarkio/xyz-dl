"""安全的文件名清理器

实现平台感知的文件名安全清理，防范多种安全漏洞：
- Unicode控制字符攻击
- Windows保留文件名攻击
- 平台特定危险字符
- 文件名注入攻击
- 长度截断安全问题
"""

import platform
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Optional, Pattern, Set

# 常量定义
DEFAULT_MAX_LENGTH = 200
DEFAULT_FALLBACK_NAME = "untitled"
DEFAULT_EXTENSION = "txt"
MAX_EXTENSION_LENGTH = 10
MIN_FILENAME_LENGTH = 1
MAX_UNICODE_DECODE_ITERATIONS = 10


class FilenameSanitizer(ABC):
    """文件名清理器抽象基类"""

    @abstractmethod
    def sanitize(self, filename: str, max_length: int = 200) -> str:
        """清理文件名

        Args:
            filename: 原始文件名
            max_length: 最大长度限制

        Returns:
            清理后的安全文件名
        """
        pass


class SecureFilenameSanitizer(FilenameSanitizer):
    """安全的文件名清理器 - 多层防护"""

    # Unicode控制字符 - 使用frozenset提升查找性能
    _UNICODE_CONTROL_CHARS: frozenset[str] = frozenset(
        {
            # C0控制字符 (0x00-0x1F)
            *[chr(i) for i in range(0x00, 0x20)],
            chr(0x7F),  # DEL
            # C1控制字符 (0x80-0x9F)
            *[chr(i) for i in range(0x80, 0xA0)],
            # 其他危险Unicode字符
            "\u00ad",  # 软连字符
            "\u200b",
            "\u200c",
            "\u200d",  # 零宽字符
            "\u200e",
            "\u200f",  # 方向标记
            "\u202a",
            "\u202b",
            "\u202c",
            "\u202d",
            "\u202e",  # 双向文本控制
            "\u2028",
            "\u2029",  # 行/段分隔符
            "\u2060",
            "\u2061",
            "\u2062",
            "\u2063",
            "\u2064",  # 不可见分隔符
            "\ufeff",  # 字节序标记
            "\ufff9",
            "\ufffa",
            "\ufffb",  # 插入字符
        }
    )

    # Windows保留文件名 - 使用frozenset提升查找性能
    _WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset(
        {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    )

    # 全角到半角字符映射
    _FULLWIDTH_TO_HALFWIDTH = {
        "：": ":",
        "｜": "|",
        '"': '"',
        '"': '"',
        """: "'", """: "'",
        "？": "?",
        "＊": "*",
        "＜": "<",
        "＞": ">",
        "｜": "|",
    }

    def __init__(self, platform_name: Optional[str] = None):
        """初始化清理器

        Args:
            platform_name: 平台名称，None时自动检测
        """
        self.platform = platform_name or platform.system()
        self.illegal_chars: Set[str] = set()
        self._compiled_patterns: list[Pattern[str]] = []
        self._setup_platform_rules()

    def _setup_platform_rules(self):
        """根据平台设置清理规则 - 预编译正则表达式提升性能"""
        # 基础非法字符 (跨平台) - 使用set提升查找性能
        base_illegal = {'"', "'", "<", ">", ":", "|", "?", "*"}
        # 路径相关危险字符 - 所有平台都应该移除这些
        path_chars = {"/", "\\"}
        # 合并所有非法字符
        self.illegal_chars = base_illegal | path_chars

        # 预编译正则表达式模式
        if self.platform == "Windows":
            patterns = [
                r"[\x00-\x1f\x7f-\x9f]",  # 控制字符
                r"[\s.]+$",  # 结尾空白或点号
                r"^[\s.]+",  # 开头空白或点号
                r"\.{2,}",  # 多个连续点号 (路径遍历)
            ]
        else:
            patterns = [
                r"[\x00-\x1f\x7f]",  # 控制字符 (Unix系统不包括\x80-\x9f)
                r"^[\s.]+",  # 开头空白或点号
                r"\.{2,}",  # 多个连续点号 (路径遍历)
            ]

        # 预编译所有正则表达式
        self._compiled_patterns = [re.compile(pattern) for pattern in patterns]
        # 预编译空白字符清理模式
        self._whitespace_pattern = re.compile(r"\s+")

    def sanitize(self, filename: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
        """多层安全清理文件名

        Args:
            filename: 原始文件名
            max_length: 最大长度限制

        Returns:
            清理后的安全文件名
        """
        if not filename or not filename.strip():
            return DEFAULT_FALLBACK_NAME

        # 依次应用各层清理策略
        pipeline = [
            self._normalize_unicode,
            self._remove_control_characters,
            self._remove_illegal_characters,
            self._handle_reserved_names,
            lambda text: self._safe_truncate(text, max_length),
            self._final_validation,
        ]

        cleaned = filename
        for sanitize_func in pipeline:
            cleaned = sanitize_func(cleaned)
            if not cleaned:  # 如果任何步骤导致空字符串，立即返回默认值
                return DEFAULT_FALLBACK_NAME

        return cleaned

    def _normalize_unicode(self, text: str) -> str:
        """Unicode规范化 - 防止Unicode变体攻击"""
        # 使用NFKC规范化 - 兼容性分解后再组合
        normalized = unicodedata.normalize("NFKC", text)

        # 批量处理全角到半角字符转换 - 性能优化
        for fullwidth, halfwidth in self._FULLWIDTH_TO_HALFWIDTH.items():
            normalized = normalized.replace(fullwidth, halfwidth)

        return normalized

    def _remove_control_characters(self, text: str) -> str:
        """移除Unicode控制字符 - 性能优化版本"""
        # 使用字符串转换表进行批量替换 - 比逐个replace更高效
        translation_table = str.maketrans("", "", "".join(self._UNICODE_CONTROL_CHARS))
        text = text.translate(translation_table)

        # 过滤其他Unicode控制字符类别 - 使用生成器表达式优化内存
        return "".join(
            char for char in text if unicodedata.category(char) not in ("Cc", "Cf")
        )

    def _remove_illegal_characters(self, text: str) -> str:
        """移除平台特定的非法字符 - 优化版本"""
        # 使用字符串转换表批量移除非法字符 - 比逐个replace更高效
        if self.illegal_chars:
            translation_table = str.maketrans("", "", "".join(self.illegal_chars))
            text = text.translate(translation_table)

        # 应用预编译的正则表达式模式
        for pattern in self._compiled_patterns:
            text = pattern.sub("", text)

        # 清理多余空白 - 使用预编译的模式
        text = self._whitespace_pattern.sub(" ", text).strip()

        return text

    def _handle_reserved_names(self, text: str) -> str:
        """处理Windows保留名称 - 优化版本"""
        if self.platform != "Windows" or not text:
            return text

        # 提取文件名部分（去除扩展名）并转为大写进行检查
        name_part = text.split(".", 1)[0].upper()

        # 使用frozenset进行O(1)查找
        if name_part in self._WINDOWS_RESERVED_NAMES:
            return f"file_{text}"

        return text

    def _safe_truncate(self, text: str, max_length: int) -> str:
        """安全截断 - 优化版本"""
        if len(text) <= max_length:
            return text

        # 分离文件名和扩展名
        if "." in text:
            name, ext = text.rsplit(".", 1)
            # 限制扩展名长度
            ext = ext[:MAX_EXTENSION_LENGTH] if len(ext) > MAX_EXTENSION_LENGTH else ext

            # 计算可用的文件名长度
            available_length = max_length - len(ext) - 1  # -1 for the dot
            if available_length < MIN_FILENAME_LENGTH:
                # 如果空间不足，使用默认扩展名
                available_length = max_length - len(DEFAULT_EXTENSION) - 1
                ext = DEFAULT_EXTENSION

            truncated_name = name[:available_length]
        else:
            truncated_name = text[:max_length]
            ext = ""

        # 移除结尾的危险字符 - 使用rstrip更高效
        truncated_name = truncated_name.rstrip(". \t")

        # 重新组合文件名
        result = f"{truncated_name}.{ext}" if ext else truncated_name

        # 最终长度验证
        if len(result) > max_length:
            result = result[:max_length].rstrip(". \t")

        return result

    def _final_validation(self, text: str) -> str:
        """最终验证和备用方案 - 优化版本"""
        # 统一处理空值情况
        if not text or not text.strip() or text.strip(".") == "":
            return DEFAULT_FALLBACK_NAME

        # 移除开头的点号 (Unix隐藏文件问题) - 使用lstrip更高效
        text = text.lstrip(".")

        # 检查清理后的长度
        if len(text.strip()) < MIN_FILENAME_LENGTH:
            return DEFAULT_FALLBACK_NAME

        # Windows平台特殊处理
        if self.platform == "Windows":
            text = text.rstrip(". ")
            if not text:
                return DEFAULT_FALLBACK_NAME

        return text


class LegacyFilenameSanitizer(FilenameSanitizer):
    """传统的文件名清理器 - 向后兼容"""

    def __init__(self):
        """初始化传统清理器 - 预编译正则表达式"""
        self._illegal_pattern = re.compile(r'[<>:"/\\|?*]')
        self._whitespace_pattern = re.compile(r"\s+")

    def sanitize(self, filename: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
        """传统的清理方法 - 保持向后兼容但优化性能"""
        if not filename:
            return DEFAULT_FALLBACK_NAME

        # 使用预编译的正则表达式
        cleaned = self._illegal_pattern.sub("", filename)
        cleaned = self._whitespace_pattern.sub(" ", cleaned).strip()

        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip()

        return cleaned or DEFAULT_FALLBACK_NAME


def create_filename_sanitizer(
    secure: bool = True, platform_name: Optional[str] = None
) -> FilenameSanitizer:
    """工厂函数：创建文件名清理器

    Args:
        secure: 是否使用安全清理器
        platform_name: 平台名称

    Returns:
        文件名清理器实例
    """
    if secure:
        return SecureFilenameSanitizer(platform_name)
    else:
        return LegacyFilenameSanitizer()
