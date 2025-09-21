"""数据模型定义

使用 Pydantic 进行类型安全的数据验证和模型定义
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class PodcastInfo(BaseModel):
    """播客信息模型"""

    title: str = Field(..., description="播客标题")
    author: str = Field(..., description="播客作者/主播")
    podcast_id: str = Field(default="", description="播客ID")
    podcast_url: str = Field(default="", description="播客URL")

    model_config = ConfigDict(extra="allow")  # 允许额外字段


class EpisodeInfo(BaseModel):
    """播客节目信息模型"""

    title: str = Field(..., description="节目标题")
    podcast: PodcastInfo = Field(..., description="所属播客信息")
    duration: int = Field(default=0, description="时长(毫秒)")
    pub_date: str = Field(default="", description="发布日期")
    eid: str = Field(default="", description="节目ID")
    shownotes: Optional[str] = Field(default="", description="节目介绍")

    # 新增的元数据字段
    episode_url: str = Field(default="", description="节目完整URL")
    audio_url: str = Field(default="", description="音频文件URL")
    cover_image: str = Field(default="", description="节目封面图片URL")
    published_datetime: str = Field(default="", description="精确发布时间(ISO格式)")

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        """验证时长必须非负"""
        if v < 0:
            raise ValueError("Duration must be non-negative")
        return v

    @property
    def duration_minutes(self) -> int:
        """获取时长(分钟)"""
        return self.duration // 60000 if self.duration else 0

    @property
    def formatted_pub_date(self) -> str:
        """格式化发布日期"""
        # 优先使用 published_datetime，否则使用 pub_date
        date_str = self.published_datetime or self.pub_date
        if not date_str:
            return "未知"
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y年%m月%d日")
        except:
            return date_str

    @property
    def formatted_datetime(self) -> str:
        """格式化发布日期时间（包含时分秒）"""
        date_str = self.published_datetime or self.pub_date
        if not date_str:
            return "未知"
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            return date_str

    @property
    def duration_text(self) -> str:
        """获取时长文本"""
        if self.duration_minutes:
            return f"{self.duration_minutes}分钟"
        return "未知"

    model_config = ConfigDict(extra="allow")  # 允许额外字段


class DownloadRequest(BaseModel):
    """下载请求模型"""

    url: str = Field(..., description="小宇宙播客节目URL或episode ID")
    download_dir: str = Field(default=".", description="下载目录")
    mode: str = Field(default="both", description="下载模式: audio, md, both")
    url_only: bool = Field(default=False, description="只获取下载地址，不实际下载")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """验证下载模式"""
        valid_modes = ["audio", "md", "both"]
        if v not in valid_modes:
            raise ValueError(f"Mode must be one of {valid_modes}")
        return v

    @field_validator("url")
    @classmethod
    def validate_xiaoyuzhou_url(cls, v: Any) -> str:
        """验证并标准化 URL（支持 episode ID 或完整 URL）"""
        from .parsers import UrlValidator

        url_str = str(v).strip()
        try:
            # 使用 UrlValidator 标准化为完整的 URL
            normalized_url = UrlValidator.normalize_to_url(url_str)
            return normalized_url
        except Exception as e:
            raise ValueError(f"Invalid episode URL or ID: {url_str}. {str(e)}")


class DownloadResult(BaseModel):
    """下载结果模型"""

    success: bool = Field(..., description="是否成功")
    audio_path: Optional[str] = Field(None, description="音频文件路径")
    md_path: Optional[str] = Field(None, description="Markdown文件路径")
    error: Optional[str] = Field(None, description="错误信息")
    episode_info: Optional[EpisodeInfo] = Field(None, description="节目信息")


class DownloadProgress(BaseModel):
    """下载进度模型"""

    filename: str = Field(..., description="文件名")
    downloaded: int = Field(default=0, description="已下载字节数")
    total: int = Field(default=0, description="总字节数")
    speed: float = Field(default=0.0, description="下载速度(bytes/s)")

    @property
    def percentage(self) -> float:
        """下载百分比"""
        if self.total > 0:
            return (self.downloaded / self.total) * 100
        return 0.0

    @property
    def is_complete(self) -> bool:
        """是否下载完成"""
        return self.total > 0 and self.downloaded >= self.total

    @property
    def formatted_size(self) -> str:
        """格式化文件大小"""

        def format_bytes(bytes_num: float) -> str:
            for unit in ["B", "KB", "MB", "GB"]:
                if bytes_num < 1024.0:
                    return f"{bytes_num:.1f} {unit}"
                bytes_num = bytes_num / 1024.0
            return f"{bytes_num:.1f} TB"

        if self.total > 0:
            return f"{format_bytes(self.downloaded)} / {format_bytes(self.total)}"
        else:
            return format_bytes(self.downloaded)

    model_config = ConfigDict(extra="forbid")  # 不允许额外字段


class Config(BaseModel):
    """应用配置模型"""

    # 网络配置
    timeout: int = Field(default=30, description="请求超时时间(秒)")
    max_retries: int = Field(default=3, description="最大重试次数")
    chunk_size: int = Field(default=8192, description="下载块大小")

    # 用户代理
    user_agent: str = Field(
        default="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="HTTP用户代理",
    )

    # 文件名设置
    max_filename_length: int = Field(default=200, description="文件名最大长度")

    # 并发设置
    max_concurrent_downloads: int = Field(default=3, description="最大并发下载数")

    # 交互模式设置
    non_interactive: bool = Field(default=False, description="非交互模式，不询问用户输入")
    default_overwrite_behavior: bool = Field(default=False, description="非交互模式下的默认覆盖行为")
    debug_mode: bool = Field(default=False, description="调试模式，显示详细错误信息")

    @field_validator(
        "timeout",
        "max_retries",
        "chunk_size",
        "max_filename_length",
        "max_concurrent_downloads",
    )
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """验证必须为正数"""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    model_config = ConfigDict(extra="allow")  # 允许额外配置项
