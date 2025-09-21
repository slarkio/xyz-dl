"""
HTML安全清理模块

实现安全的HTML清理功能，防止XSS注入攻击
"""

import html
from typing import Any, Dict, List

import bleach


class HtmlSanitizer:
    """HTML安全清理器"""

    # 允许的安全HTML标签白名单（移除span和div以防CSS注入）
    ALLOWED_TAGS: List[str] = [
        "p",
        "br",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "s",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "blockquote",
        "a",
    ]

    # 允许的安全HTML属性白名单（移除class属性以防CSS注入）
    ALLOWED_ATTRIBUTES: Dict[str, List[str]] = {"a": ["href", "title"]}

    # 允许的协议白名单
    ALLOWED_PROTOCOLS: List[str] = ["http", "https", "mailto"]

    def __init__(self) -> None:
        """初始化HTML清理器"""
        self._configure_bleach()

    def _configure_bleach(self) -> None:
        """配置bleach清理器"""
        # 使用严格的安全配置
        self.bleach_config = {
            "tags": self.ALLOWED_TAGS,
            "attributes": self.ALLOWED_ATTRIBUTES,
            "protocols": self.ALLOWED_PROTOCOLS,
            "strip": True,  # 移除不允许的标签而不是转义
            "strip_comments": True,  # 移除HTML注释
        }

    def sanitize_html(self, html_content: str) -> str:
        """
        安全清理HTML内容

        Args:
            html_content: 原始HTML内容

        Returns:
            清理后的安全HTML内容
        """
        if not html_content or not isinstance(html_content, str):
            return ""

        # 防护：输入长度限制，防止DoS攻击
        if len(html_content) > 100000:  # 100KB限制
            raise ValueError(f"HTML content too large: {len(html_content)} characters")

        # 第一步：Unicode标准化
        normalized_content = self._normalize_unicode(html_content)

        # 第二步：预处理，移除危险标签及其内容（在实体解码前）
        preprocessed_content = self._preprocess_dangerous_content(normalized_content)

        # 第三步：使用bleach清理HTML
        cleaned_html = bleach.clean(
            preprocessed_content,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRIBUTES,
            protocols=self.ALLOWED_PROTOCOLS,
            strip=True,  # 移除不允许的标签
            strip_comments=True,  # 移除HTML注释
        )

        # 第四步：再次检查是否有遗漏的危险内容
        cleaned_html = self._additional_security_check(cleaned_html)

        # 第五步：最后解码HTML实体（修复处理顺序）
        final_content = self._safe_html_decode(cleaned_html)

        return final_content.strip()

    def _normalize_unicode(self, content: str) -> str:
        """
        Unicode标准化，防止Unicode绕过攻击

        Args:
            content: 原始内容

        Returns:
            标准化后的内容
        """
        import unicodedata

        # Unicode标准化，转换全角字符等
        normalized = unicodedata.normalize("NFKC", content)

        # 移除不可见字符和控制字符
        cleaned = "".join(
            char
            for char in normalized
            if unicodedata.category(char) not in ["Cc", "Cf", "Cs", "Co", "Cn"]
        )

        return cleaned

    def _preprocess_dangerous_content(self, content: str) -> str:
        """
        预处理：移除危险标签及其全部内容（增强版）

        Args:
            content: 原始HTML内容

        Returns:
            移除危险内容后的HTML
        """
        import re

        # 定义需要完全移除的危险标签（包括内容）
        dangerous_tags = [
            "script",
            "iframe",
            "object",
            "embed",
            "form",
            "style",
            "link",
            "meta",
            "base",
            "applet",
            "noscript",
        ]

        result = content

        # 第一轮：移除HTML实体编码的危险标签
        result = self._remove_entity_encoded_tags(result, dangerous_tags)

        # 第二轮：移除常规HTML标签
        for tag in dangerous_tags:
            # 增强的正则表达式，处理空白字符、注释和畸形标签
            patterns = [
                # 标准标签，支持属性和空白字符
                rf"<\s*{tag}\b[^>]*>.*?</\s*{tag}\s*>",
                # 自闭合标签
                rf"<\s*{tag}\b[^>]*/?\s*>",
                # 不完整标签（开始标签后没有结束标签）
                rf"<\s*{tag}\b[^>]*>(?!.*</\s*{tag}\s*>)",
                # 处理标签中包含注释的情况
                rf"<\s*{tag}[^>]*(?:<!--[^>]*-->)*[^>]*>.*?</\s*{tag}\s*>",
                # 嵌套和畸形标签
                rf"<+\s*{tag}[^>]*>+.*?<+/\s*{tag}\s*>+",
            ]

            for pattern in patterns:
                result = re.sub(pattern, "", result, flags=re.IGNORECASE | re.DOTALL)

        return result

    def _remove_entity_encoded_tags(
        self, content: str, dangerous_tags: List[str]
    ) -> str:
        """
        移除HTML实体编码的危险标签

        Args:
            content: HTML内容
            dangerous_tags: 危险标签列表

        Returns:
            移除实体编码危险标签后的内容
        """
        import re

        result = content
        for tag in dangerous_tags:
            # 处理HTML实体编码的标签（如 &lt;script&gt;）
            entity_patterns = [
                # 完整的实体编码标签对
                rf"&lt;\s*{tag}\b[^&]*?&gt;.*?&lt;/\s*{tag}\s*&gt;",
                # 自闭合实体编码标签
                rf"&lt;\s*{tag}\b[^&]*?/?&gt;",
                # 混合编码（部分实体编码）
                rf"&lt;{tag}[^&]*?&gt;.*?&lt;/{tag}&gt;",
                rf"<{tag}[^>]*?&gt;.*?&lt;/{tag}>",
            ]
            for pattern in entity_patterns:
                result = re.sub(pattern, "", result, flags=re.IGNORECASE | re.DOTALL)

        # 同时移除包含脚本关键词的实体编码内容
        dangerous_keywords = [
            "alert",
            "eval",
            "document.cookie",
            "innerHTML",
            "outerHTML",
        ]
        for keyword in dangerous_keywords:
            # 移除包含危险关键词的内容
            result = re.sub(
                rf"[^a-zA-Z0-9]*{keyword}[^a-zA-Z0-9]*\([^)]*\)",
                "",
                result,
                flags=re.IGNORECASE,
            )

        return result

    def _additional_security_check(self, content: str) -> str:
        """
        额外的安全检查，防止绕过攻击（增强版）

        Args:
            content: 初步清理后的内容

        Returns:
            进一步清理后的安全内容
        """
        import re

        # 移除所有可能的危险协议（包括实体编码和各种变形）
        dangerous_protocol_patterns = [
            # 基础协议模式
            r"j\s*a\s*v\s*a\s*s\s*c\s*r\s*i\s*p\s*t\s*:",
            r"v\s*b\s*s\s*c\s*r\s*i\s*p\s*t\s*:",
            r"d\s*a\s*t\s*a\s*:\s*t\s*e\s*x\s*t\s*/\s*h\s*t\s*m\s*l",
            r"d\s*a\s*t\s*a\s*:\s*a\s*p\s*p\s*l\s*i\s*c\s*a\s*t\s*i\s*o\s*n\s*/",
            # 实体编码模式
            r"&#[xX]?[0-9a-fA-F]+;",
            # Unicode转义模式
            r"\\u[0-9a-fA-F]{4}",
            # 其他危险模式
            r"expression\s*\(",
            r"mocha\s*:",
            r"livescript\s*:",
        ]

        result = content
        for pattern in dangerous_protocol_patterns:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        # 移除可能的事件处理器属性
        event_handler_pattern = r'\s*on\w+\s*=\s*["\'][^"\'>]*["\']'
        result = re.sub(event_handler_pattern, "", result, flags=re.IGNORECASE)

        # 移除style属性中的危险内容
        style_pattern = (
            r'style\s*=\s*["\'][^"\'>]*(?:javascript|expression|@import)[^"\'>]*["\']'
        )
        result = re.sub(style_pattern, "", result, flags=re.IGNORECASE)

        return result

    def _safe_html_decode(self, content: str) -> str:
        """
        安全的HTML实体解码，防止多层编码攻击

        Args:
            content: HTML内容

        Returns:
            安全解码后的内容
        """
        if not content:
            return content

        # 记录原始内容，用于检测递归解码
        previous_content = ""
        current_content = content
        decode_count = 0

        # 最多解码3次，防止无限递归
        while previous_content != current_content and decode_count < 3:
            previous_content = current_content
            current_content = html.unescape(current_content)
            decode_count += 1

            # 每次解码后检查是否出现危险内容
            if any(
                danger in current_content.lower()
                for danger in ["<script", "javascript:", "vbscript:", "data:text/html"]
            ):
                # 如果解码后出现危险内容，返回解码前的安全版本
                return previous_content

        return current_content

    def html_to_markdown(self, html_content: str) -> str:
        """
        将HTML安全转换为Markdown格式

        Args:
            html_content: 原始HTML内容

        Returns:
            Markdown格式的内容
        """
        if not html_content or not isinstance(html_content, str):
            return ""

        # 首先清理HTML确保安全
        safe_html = self.sanitize_html(html_content)

        # 转换为Markdown格式
        markdown = self._convert_to_markdown(safe_html)

        return markdown.strip()

    def _convert_to_markdown(self, safe_html: str) -> str:
        """
        将安全的HTML转换为Markdown

        Args:
            safe_html: 已清理的安全HTML

        Returns:
            Markdown格式内容
        """
        import re

        result = safe_html

        # 转换标题
        for i in range(1, 7):
            result = re.sub(
                rf"<h{i}[^>]*>(.*?)</h{i}>",
                rf'{"#" * i} \1\n',
                result,
                flags=re.IGNORECASE,
            )

        # 转换段落
        result = re.sub(r"<p[^>]*>", "\n", result, flags=re.IGNORECASE)
        result = re.sub(r"</p>", "\n", result, flags=re.IGNORECASE)

        # 转换换行
        result = re.sub(r"<br[^>]*/?>", "\n", result, flags=re.IGNORECASE)

        # 转换粗体
        result = re.sub(
            r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", result, flags=re.IGNORECASE
        )

        # 转换斜体
        result = re.sub(
            r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", result, flags=re.IGNORECASE
        )

        # 转换链接
        result = re.sub(
            r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
            r"[\2](\1)",
            result,
            flags=re.IGNORECASE,
        )

        # 转换列表项
        result = re.sub(r"<li[^>]*>", "- ", result, flags=re.IGNORECASE)
        result = re.sub(r"</li>", "\n", result, flags=re.IGNORECASE)

        # 转换引用
        result = re.sub(
            r"<blockquote[^>]*>(.*?)</blockquote>",
            r"> \1\n",
            result,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # 移除剩余的HTML标签
        result = re.sub(r"<[^>]+>", "", result)

        # 清理多余的空行
        result = re.sub(r"\n\s*\n\s*\n", "\n\n", result)

        return result


# 全局安全清理器实例
_sanitizer = HtmlSanitizer()


def sanitize_show_notes(html_content: str) -> str:
    """
    便捷函数：安全清理Show Notes HTML内容并转换为Markdown

    Args:
        html_content: 原始HTML内容

    Returns:
        安全的Markdown格式内容
    """
    return _sanitizer.html_to_markdown(html_content)


def sanitize_html_content(html_content: str) -> str:
    """
    便捷函数：安全清理HTML内容

    Args:
        html_content: 原始HTML内容

    Returns:
        清理后的安全HTML内容
    """
    return _sanitizer.sanitize_html(html_content)
