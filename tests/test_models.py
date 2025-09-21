"""测试数据模型"""

import pytest
from pydantic import ValidationError

from src.xyz_dl.models import (
    PodcastInfo,
    EpisodeInfo,
    DownloadRequest,
    DownloadResult,
    DownloadProgress,
    Config,
)


class TestPodcastInfo:
    """测试播客信息模型"""

    def test_valid_podcast_info(self):
        """测试有效的播客信息"""
        podcast = PodcastInfo(title="测试播客", author="测试作者")
        assert podcast.title == "测试播客"
        assert podcast.author == "测试作者"

    def test_podcast_info_required_fields(self):
        """测试必需字段"""
        with pytest.raises(ValidationError):
            PodcastInfo()  # 缺少必需字段


class TestEpisodeInfo:
    """测试节目信息模型"""

    def test_valid_episode_info(self):
        """测试有效的节目信息"""
        podcast = PodcastInfo(title="测试播客", author="测试作者")
        episode = EpisodeInfo(
            title="测试节目",
            podcast=podcast,
            duration=3600000,  # 60分钟
            pub_date="2025-01-01T00:00:00Z",
            eid="test123",
        )

        assert episode.title == "测试节目"
        assert episode.duration_minutes == 60
        assert episode.eid == "test123"

    def test_duration_validation(self):
        """测试时长验证"""
        podcast = PodcastInfo(title="测试播客", author="测试作者")

        # 负数时长应该抛出异常
        with pytest.raises(ValidationError):
            EpisodeInfo(title="测试", podcast=podcast, duration=-1)

    def test_formatted_pub_date(self):
        """测试格式化发布日期"""
        podcast = PodcastInfo(title="测试播客", author="测试作者")
        episode = EpisodeInfo(
            title="测试节目", podcast=podcast, pub_date="2025-01-01T00:00:00Z"
        )

        assert "2025年01月01日" in episode.formatted_pub_date


class TestDownloadRequest:
    """测试下载请求模型"""

    def test_valid_download_request(self):
        """测试有效的下载请求"""
        request = DownloadRequest(url="https://www.xiaoyuzhoufm.com/episode/test123")
        assert str(request.url) == "https://www.xiaoyuzhoufm.com/episode/test123"
        assert request.mode == "both"  # 默认值
        assert request.download_dir == "."  # 默认值

    def test_invalid_url(self):
        """测试无效的URL"""
        with pytest.raises(ValidationError):
            DownloadRequest(url="https://invalid-url.com/episode/test")

    def test_invalid_mode(self):
        """测试无效的模式"""
        with pytest.raises(ValidationError):
            DownloadRequest(
                url="https://www.xiaoyuzhoufm.com/episode/test123", mode="invalid"
            )

    def test_episode_id_normalization(self):
        """测试 episode ID 会被自动标准化为完整 URL"""
        # 使用 episode ID 创建请求
        request = DownloadRequest(url="12345678", mode="both")

        # 验证 URL 被标准化为完整 URL
        expected_url = "https://www.xiaoyuzhoufm.com/episode/12345678"
        assert str(request.url) == expected_url

        # 测试另一个 episode ID 格式
        request2 = DownloadRequest(url="67890123", mode="audio")
        expected_url2 = "https://www.xiaoyuzhoufm.com/episode/67890123"
        assert str(request2.url) == expected_url2

    def test_invalid_episode_id_or_url(self):
        """测试无效的 episode ID 或 URL"""
        invalid_inputs = [
            "https://example.com/episode/123",  # 错误的域名
            "http://www.xiaoyuzhoufm.com/episode/123",  # 错误的协议
            "",  # 空字符串
            "/invalid/path",  # 无效路径
        ]

        for invalid_input in invalid_inputs:
            with pytest.raises(ValidationError):
                DownloadRequest(url=invalid_input)


class TestDownloadProgress:
    """测试下载进度模型"""

    def test_progress_calculation(self):
        """测试进度计算"""
        progress = DownloadProgress(filename="test.mp3", downloaded=500, total=1000)

        assert progress.percentage == 50.0
        assert not progress.is_complete

        progress.downloaded = 1000
        assert progress.is_complete

    def test_formatted_size(self):
        """测试格式化大小"""
        progress = DownloadProgress(filename="test.mp3", downloaded=1024, total=2048)

        formatted = progress.formatted_size
        assert "KB" in formatted


class TestConfig:
    """测试配置模型"""

    def test_default_config(self):
        """测试默认配置"""
        config = Config()

        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.chunk_size == 8192
        assert config.max_filename_length == 200
        assert config.max_concurrent_downloads == 3

    def test_config_validation(self):
        """测试配置验证"""
        # 负数应该抛出异常
        with pytest.raises(ValidationError):
            Config(timeout=-1)

        with pytest.raises(ValidationError):
            Config(max_retries=0)
