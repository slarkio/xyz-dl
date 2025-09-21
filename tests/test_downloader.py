"""测试下载器模块"""

from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.xyz_dl.downloader import XiaoYuZhouDL
from src.xyz_dl.exceptions import ValidationError
from src.xyz_dl.models import Config, DownloadRequest, EpisodeInfo, PodcastInfo


class TestXiaoYuZhouDL:
    """测试XiaoYuZhouDL下载器"""

    def test_init_with_defaults(self):
        """测试默认初始化"""
        downloader = XiaoYuZhouDL()

        assert downloader.config is not None
        assert downloader.parser is not None
        assert downloader.progress_callback is None

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = Config(timeout=60)
        downloader = XiaoYuZhouDL(config=config)

        assert downloader.config.timeout == 60

    def test_sanitize_filename(self):
        """测试文件名清理"""
        downloader = XiaoYuZhouDL()

        # 测试非法字符清理
        dirty_filename = 'test<>:"/\\|?*file'
        clean_filename = downloader._sanitize_filename(dirty_filename)
        assert clean_filename == "testfile"

        # 测试长度限制
        long_filename = "a" * 300
        limited_filename = downloader._sanitize_filename(long_filename)
        assert len(limited_filename) <= 200

    def test_generate_filename(self):
        """测试文件名生成"""
        downloader = XiaoYuZhouDL()

        podcast = PodcastInfo(title="测试播客", author="测试作者")
        episode = EpisodeInfo(title="第1期 - 主播名", podcast=podcast, eid="test123")

        filename = downloader._generate_filename(episode)
        assert "test123" in filename
        assert "主播名" in filename

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试异步上下文管理器"""
        async with XiaoYuZhouDL() as downloader:
            assert downloader._session is not None

        # 退出上下文后会话应该被关闭
        # 注意：这里不能直接检查_session是否为None，因为关闭是异步的

    def test_download_sync_interface(self):
        """测试同步下载接口"""
        downloader = XiaoYuZhouDL()

        # Mock异步下载方法
        with patch.object(downloader, "download") as mock_download:
            mock_download.return_value = Mock()

            # 这里只测试接口存在，不执行真实下载
            assert hasattr(downloader, "download_sync")


class TestDownloadValidation:
    """测试下载验证"""

    @pytest.mark.asyncio
    async def test_invalid_url_validation(self):
        """测试无效URL验证"""
        downloader = XiaoYuZhouDL()

        with pytest.raises(PydanticValidationError):
            await downloader.download("https://invalid-url.com/episode/test")


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_xiaoyuzhou_downloader_import(self):
        """测试旧的下载器类可以导入"""
        from src.xyz_dl import XiaoyuzhouDownloader

        # 应该产生警告但不报错
        with pytest.warns(DeprecationWarning):
            downloader = XiaoyuzhouDownloader()

        assert downloader is not None

    def test_xiaoyuzhou_downloader_validate_url(self):
        """测试旧下载器的URL验证"""
        from src.xyz_dl import XiaoyuzhouDownloader

        with pytest.warns(DeprecationWarning):
            downloader = XiaoyuzhouDownloader()

        assert downloader.validate_url("https://www.xiaoyuzhoufm.com/episode/test")
        assert not downloader.validate_url("https://example.com/test")


class TestUrlOnlyMode:
    """测试只获取URL模式"""

    @pytest.mark.asyncio
    async def test_url_only_request_creation(self):
        """测试创建url_only请求"""
        request = DownloadRequest(
            url="https://www.xiaoyuzhoufm.com/episode/6745c73fe0ab7e4a32ae6ad1",
            url_only=True,
        )

        assert request.url_only is True
        assert request.mode == "both"  # 默认模式
        assert request.download_dir == "."

    @pytest.mark.asyncio
    async def test_url_only_mode_with_mock_parser(self):
        """测试url_only模式使用模拟解析器"""
        # 创建模拟的parser
        mock_parser = Mock()

        # 模拟episode信息
        mock_podcast = PodcastInfo(title="测试播客", author="测试作者")
        mock_episode = EpisodeInfo(
            title="测试节目", podcast=mock_podcast, eid="6745c73fe0ab7e4a32ae6ad1"
        )

        # 模拟解析结果
        mock_parser.parse_episode_page.return_value = (
            mock_episode,
            "https://test-audio-url.m4a",
        )

        downloader = XiaoYuZhouDL(parser=mock_parser)

        request = DownloadRequest(
            url="https://www.xiaoyuzhoufm.com/episode/6745c73fe0ab7e4a32ae6ad1",
            url_only=True,
        )

        # 模拟网络会话
        with patch.object(downloader, "_create_session"), patch(
            "src.xyz_dl.downloader.parse_episode_from_url",
            return_value=(mock_episode, "https://test-audio-url.m4a"),
        ):

            result = await downloader.download(request)

            # 验证结果
            assert result.success is True
            assert result.episode_info is not None
            assert result.episode_info.audio_url == "https://test-audio-url.m4a"
            assert result.audio_path is None  # 不应该有文件路径
            assert result.md_path is None  # 不应该有MD文件路径
            assert result.error is None

    @pytest.mark.asyncio
    async def test_url_only_mode_without_audio_url(self):
        """测试url_only模式但无法获取音频URL的情况"""
        mock_parser = Mock()
        mock_podcast = PodcastInfo(title="测试播客", author="测试作者")
        mock_episode = EpisodeInfo(
            title="测试节目", podcast=mock_podcast, eid="6745c73fe0ab7e4a32ae6ad1"
        )

        downloader = XiaoYuZhouDL(parser=mock_parser)

        request = DownloadRequest(
            url="https://www.xiaoyuzhoufm.com/episode/6745c73fe0ab7e4a32ae6ad1",
            url_only=True,
        )

        # 模拟无音频URL的情况
        with patch.object(downloader, "_create_session"), patch(
            "src.xyz_dl.downloader.parse_episode_from_url",
            return_value=(mock_episode, None),
        ):

            result = await downloader.download(request)

            # 应该返回失败结果
            assert result.success is False
            assert "Audio URL not found" in result.error
