"""异常定义模块

定义应用专用的异常类，提供清晰的错误处理机制
"""

from typing import Any, Dict, Optional


class XyzDlException(Exception):
    """XYZ-DL 基础异常类"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} (Context: {context_str})"
        return self.message


class ValidationError(XyzDlException):
    """数据验证异常"""

    pass


class NetworkError(XyzDlException):
    """网络请求异常"""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.url = url
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [self.message]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class ParseError(XyzDlException):
    """页面解析异常"""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        parser_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.url = url
        self.parser_type = parser_type

    def __str__(self) -> str:
        parts = [self.message]
        if self.parser_type:
            parts.append(f"Parser: {self.parser_type}")
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class DownloadError(XyzDlException):
    """文件下载异常"""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        file_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.url = url
        self.file_path = file_path

    def __str__(self) -> str:
        parts = [self.message]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class FileOperationError(XyzDlException):
    """文件操作异常"""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.file_path = file_path
        self.operation = operation

    def __str__(self) -> str:
        parts = [self.message]
        if self.operation:
            parts.append(f"Operation: {self.operation}")
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class ConfigurationError(XyzDlException):
    """配置异常"""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.config_key = config_key
        self.config_value = config_value

    def __str__(self) -> str:
        parts = [self.message]
        if self.config_key:
            parts.append(f"Key: {self.config_key}")
        if self.config_value is not None:
            parts.append(f"Value: {self.config_value}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class AuthenticationError(XyzDlException):
    """认证异常 - 需要登录或权限不足"""

    pass


class NotFoundError(XyzDlException):
    """资源未找到异常"""

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.resource_type = resource_type
        self.resource_id = resource_id

    def __str__(self) -> str:
        parts = [self.message]
        if self.resource_type:
            parts.append(f"Type: {self.resource_type}")
        if self.resource_id:
            parts.append(f"ID: {self.resource_id}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class RateLimitError(XyzDlException):
    """请求频率限制异常"""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.retry_after = retry_after

    def __str__(self) -> str:
        parts = [self.message]
        if self.retry_after:
            parts.append(f"Retry after: {self.retry_after} seconds")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


class PathSecurityError(XyzDlException):
    """路径安全异常 - 路径遍历攻击检测"""

    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        attack_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.path = path
        self.attack_type = attack_type

    def __str__(self) -> str:
        parts = [self.message]
        if self.attack_type:
            parts.append(f"Attack Type: {self.attack_type}")
        if self.path:
            parts.append(f"Path: {self.path}")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        return " | ".join(parts)


# 异常映射表 - 用于将外部异常转换为内部异常
EXCEPTION_MAPPING = {
    # HTTP状态码映射
    400: ValidationError,
    401: AuthenticationError,
    403: AuthenticationError,
    404: NotFoundError,
    429: RateLimitError,
    500: NetworkError,
    502: NetworkError,
    503: NetworkError,
    504: NetworkError,
}


def map_http_exception(status_code: int, message: str, **kwargs) -> XyzDlException:
    """根据HTTP状态码映射异常"""
    exception_class = EXCEPTION_MAPPING.get(status_code, NetworkError)
    return exception_class(message, **kwargs)


def wrap_exception(func):
    """异常包装装饰器 - 将标准异常转换为应用异常"""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except XyzDlException:
            # 已经是应用异常，直接抛出
            raise
        except (IOError, OSError) as e:
            raise FileOperationError(f"File operation failed: {e}")
        except (ConnectionError, TimeoutError) as e:
            raise NetworkError(f"Network error: {e}")
        except ValueError as e:
            raise ValidationError(f"Validation error: {e}")
        except Exception as e:
            # 其他未知异常
            raise XyzDlException(f"Unexpected error: {e}")

    return wrapper
