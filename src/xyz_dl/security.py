"""
HTML安全清理模块

实现安全的HTML清理功能，防止XSS注入攻击
"""
import bleach
import html
from typing import List, Dict, Any


class HtmlSanitizer:
    """HTML安全清理器"""

    # 允许的安全HTML标签白名单
    ALLOWED_TAGS: List[str] = [
        'p', 'br', 'strong', 'em', 'b', 'i', 'u', 's',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li',
        'blockquote',
        'a',
        'span', 'div'
    ]

    # 允许的安全HTML属性白名单
    ALLOWED_ATTRIBUTES: Dict[str, List[str]] = {
        'a': ['href', 'title'],
        'span': ['class'],
        'div': ['class'],
    }

    # 允许的协议白名单
    ALLOWED_PROTOCOLS: List[str] = ['http', 'https', 'mailto']

    def __init__(self):
        """初始化HTML清理器"""
        self._configure_bleach()

    def _configure_bleach(self) -> None:
        """配置bleach清理器"""
        # 使用严格的安全配置
        self.bleach_config = {
            'tags': self.ALLOWED_TAGS,
            'attributes': self.ALLOWED_ATTRIBUTES,
            'protocols': self.ALLOWED_PROTOCOLS,
            'strip': True,  # 移除不允许的标签而不是转义
            'strip_comments': True,  # 移除HTML注释
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

        # 第一步：解码HTML实体（防止实体绕过）
        decoded_content = html.unescape(html_content)

        # 第二步：预处理，移除危险标签及其内容
        preprocessed_content = self._preprocess_dangerous_content(decoded_content)

        # 第三步：使用bleach清理HTML
        cleaned_html = bleach.clean(
            preprocessed_content,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRIBUTES,
            protocols=self.ALLOWED_PROTOCOLS,
            strip=True,  # 移除不允许的标签
            strip_comments=True,  # 移除HTML注释
        )

        # 第三步：再次检查是否有遗漏的危险内容
        cleaned_html = self._additional_security_check(cleaned_html)

        return cleaned_html.strip()

    def _preprocess_dangerous_content(self, content: str) -> str:
        """
        预处理：移除危险标签及其全部内容

        Args:
            content: 原始HTML内容

        Returns:
            移除危险内容后的HTML
        """
        import re

        # 定义需要完全移除的危险标签（包括内容）
        dangerous_tags = [
            'script', 'iframe', 'object', 'embed', 'form',
            'style', 'link', 'meta', 'base', 'applet'
        ]

        result = content
        for tag in dangerous_tags:
            # 移除标签及其所有内容（不区分大小写，支持多行）
            pattern = rf'<{tag}[^>]*>.*?</{tag}>'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE | re.DOTALL)

            # 移除自闭合标签
            pattern = rf'<{tag}[^>]*/?>'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        return result

    def _additional_security_check(self, content: str) -> str:
        """
        额外的安全检查，防止绕过攻击

        Args:
            content: 初步清理后的内容

        Returns:
            进一步清理后的安全内容
        """
        # 移除潜在的JavaScript协议引用
        dangerous_patterns = [
            'javascript:',
            'vbscript:',
            'data:text/html',
            'data:application/',
        ]

        result = content
        for pattern in dangerous_patterns:
            # 不区分大小写移除危险模式
            result = result.replace(pattern.lower(), '')
            result = result.replace(pattern.upper(), '')
            result = result.replace(pattern.capitalize(), '')

        return result

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
            result = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', rf'{"#" * i} \1\n', result, flags=re.IGNORECASE)

        # 转换段落
        result = re.sub(r'<p[^>]*>', '\n', result, flags=re.IGNORECASE)
        result = re.sub(r'</p>', '\n', result, flags=re.IGNORECASE)

        # 转换换行
        result = re.sub(r'<br[^>]*/?>', '\n', result, flags=re.IGNORECASE)

        # 转换粗体
        result = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', result, flags=re.IGNORECASE)

        # 转换斜体
        result = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', result, flags=re.IGNORECASE)

        # 转换链接
        result = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', result, flags=re.IGNORECASE)

        # 转换列表项
        result = re.sub(r'<li[^>]*>', '- ', result, flags=re.IGNORECASE)
        result = re.sub(r'</li>', '\n', result, flags=re.IGNORECASE)

        # 转换引用
        result = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'> \1\n', result, flags=re.IGNORECASE | re.DOTALL)

        # 移除剩余的HTML标签
        result = re.sub(r'<[^>]+>', '', result)

        # 清理多余的空行
        result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)

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