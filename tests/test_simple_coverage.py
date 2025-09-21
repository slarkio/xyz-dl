"""简单覆盖率测试 - 专注于测试基本、容易通过的功能

这个文件专注于测试一些基本的、不容易出错的功能来提升覆盖率。
"""

import pytest
from unittest.mock import patch

from xyz_dl.models import (
    Config, PodcastInfo, EpisodeInfo, DownloadProgress, DownloadResult
)
from xyz_dl.config import get_config
from xyz_dl.exceptions import ValidationError, ParseError, NetworkError


class TestBasicModels:
    """测试基本数据模型"""

    def test_podcast_info(self):
        """测试播客信息模型"""
        podcast = PodcastInfo(title="测试播客", author="测试作者")
        assert podcast.title == "测试播客"
        assert podcast.author == "测试作者"
        assert podcast.podcast_id == ""

    def test_episode_info_properties(self):
        """测试节目信息属性"""
        podcast = PodcastInfo(title="播客", author="作者")
        episode = EpisodeInfo(
            title="节目",
            podcast=podcast,
            duration=3600000,  # 1小时
            pub_date="2023-01-01T00:00:00Z"
        )

        assert episode.duration_minutes == 60
        assert episode.duration_text == "60分钟"
        assert "2023年01月01日" in episode.formatted_pub_date

        # 测试空日期
        episode2 = EpisodeInfo(title="节目2", podcast=podcast)
        assert episode2.formatted_pub_date == "未知"
        assert episode2.duration_text == "未知"

    def test_download_progress(self):
        """测试下载进度计算"""
        progress = DownloadProgress(
            filename="test.mp3",
            downloaded=50,
            total=100
        )
        assert progress.percentage == 50.0

        # 测试除零保护
        progress2 = DownloadProgress(filename="test2.mp3", downloaded=10, total=0)
        assert progress2.percentage == 0.0

    def test_download_result(self):
        """测试下载结果模型"""
        result = DownloadResult(
            success=True,
            audio_path="/path/to/audio.mp3",
            md_path="/path/to/notes.md"
        )
        assert result.success is True
        assert result.audio_path == "/path/to/audio.mp3"
        assert result.md_path == "/path/to/notes.md"

    def test_config_model(self):
        """测试配置模型"""
        config = Config()
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.chunk_size == 8192
        assert len(config.user_agent) > 0

        # 自定义配置
        config2 = Config(timeout=60, max_retries=5)
        assert config2.timeout == 60
        assert config2.max_retries == 5


class TestBasicConfig:
    """测试基本配置功能"""

    def test_get_default_config(self):
        """测试获取默认配置"""
        config = get_config()
        assert isinstance(config, Config)
        assert config.timeout > 0
        assert config.max_retries > 0
        assert config.chunk_size > 0


class TestBasicExceptions:
    """测试基本异常类"""

    def test_validation_error(self):
        """测试验证错误"""
        error = ValidationError("测试错误")
        assert str(error) == "测试错误"
        assert error.message == "测试错误"

    def test_parse_error(self):
        """测试解析错误"""
        error = ParseError("解析失败", "https://example.com")
        assert "解析失败" in str(error)
        assert error.url == "https://example.com"

    def test_network_error(self):
        """测试网络错误"""
        error = NetworkError("网络错误", "https://example.com")
        assert "网络错误" in str(error)
        assert error.url == "https://example.com"


class TestPackageImports:
    """测试包导入"""

    def test_main_imports(self):
        """测试主要导入"""
        # 测试能够导入主要组件
        from xyz_dl import XiaoYuZhouDL
        from xyz_dl import download_episode
        from xyz_dl import Config
        from xyz_dl import ValidationError

        assert XiaoYuZhouDL is not None
        assert download_episode is not None
        assert Config is not None
        assert ValidationError is not None

    def test_version_attribute(self):
        """测试版本属性"""
        import xyz_dl
        assert hasattr(xyz_dl, '__version__')
        assert isinstance(xyz_dl.__version__, str)


class TestFilenameUtils:
    """测试文件名工具"""

    def test_filename_sanitizer_import(self):
        """测试文件名清理器导入"""
        from xyz_dl.filename_sanitizer import create_filename_sanitizer

        sanitizer = create_filename_sanitizer()
        assert sanitizer is not None

        # 测试基本清理
        clean_name = sanitizer.sanitize("测试<>文件名")
        assert "<" not in clean_name
        assert ">" not in clean_name
        assert "测试" in clean_name


class TestUtilityFunctions:
    """测试工具函数"""

    def test_episode_duration_validation(self):
        """测试节目时长验证"""
        podcast = PodcastInfo(title="播客", author="作者")

        # 正常时长
        episode = EpisodeInfo(title="节目", podcast=podcast, duration=1800000)
        assert episode.duration == 1800000
        assert episode.duration_minutes == 30

        # 负数时长应该抛出异常
        with pytest.raises(ValueError):
            EpisodeInfo(title="节目", podcast=podcast, duration=-1)

    def test_formatted_datetime_edge_cases(self):
        """测试格式化日期时间的边界情况"""
        podcast = PodcastInfo(title="播客", author="作者")

        # 有效日期
        episode1 = EpisodeInfo(
            title="节目1",
            podcast=podcast,
            published_datetime="2023-01-01T12:30:00Z"
        )
        formatted = episode1.formatted_datetime
        assert "2023-01-01" in formatted
        assert "12:30:00" in formatted

        # 无效日期
        episode2 = EpisodeInfo(
            title="节目2",
            podcast=podcast,
            pub_date="invalid-date"
        )
        assert episode2.formatted_datetime == "invalid-date"

        # 空日期
        episode3 = EpisodeInfo(title="节目3", podcast=podcast)
        assert episode3.formatted_datetime == "未知"