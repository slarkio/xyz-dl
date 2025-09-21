"""测试解析器模块"""

import pytest

from src.xyz_dl.parsers import (
    UrlValidator,
    HtmlFallbackParser,
    JsonScriptParser,
    CompositeParser,
)
from src.xyz_dl.exceptions import ParseError


class TestUrlValidator:
    """测试URL验证器"""

    def test_valid_xiaoyuzhou_url(self):
        """测试有效的小宇宙URL"""
        valid_urls = [
            "https://www.xiaoyuzhoufm.com/episode/12345678",
            "https://www.xiaoyuzhoufm.com/episode/67890123",
            "https://www.xiaoyuzhoufm.com/episode/test123?param=value",
        ]

        for url in valid_urls:
            assert UrlValidator.validate_xiaoyuzhou_url(url)

    def test_invalid_xiaoyuzhou_url(self):
        """测试无效的小宇宙URL"""
        invalid_urls = [
            "https://www.example.com/episode/12345678",
            "https://xiaoyuzhoufm.com/episode/12345678",  # 缺少www
            "http://www.xiaoyuzhoufm.com/episode/12345678",  # http协议
            "https://www.xiaoyuzhoufm.com/podcast/12345678",  # 不是episode
            "",
        ]

        for url in invalid_urls:
            assert not UrlValidator.validate_xiaoyuzhou_url(url)

    def test_extract_episode_id(self):
        """测试提取节目ID"""
        url = "https://www.xiaoyuzhoufm.com/episode/test123?param=value"
        episode_id = UrlValidator.extract_episode_id(url)
        assert episode_id == "test123"

    def test_is_episode_id(self):
        """测试判断是否为episode ID"""
        # 有效的 episode ID（基于小宇宙的实际格式）
        valid_ids = ["12345678", "67890123", "5f8a1b2c3d4e", "abc123def456"]

        for episode_id in valid_ids:
            assert UrlValidator.is_episode_id(episode_id)

        # 不是 episode ID（是URL）
        invalid_ids = [
            "https://www.xiaoyuzhoufm.com/episode/12345678",
            "http://example.com",
            "/path/to/something",
            "ftp://example.com",
        ]

        for invalid_id in invalid_ids:
            assert not UrlValidator.is_episode_id(invalid_id)

    def test_normalize_to_url(self):
        """测试将 episode ID 或 URL 标准化为 URL"""
        # 测试 episode ID 转 URL
        episode_id = "12345678"
        expected_url = "https://www.xiaoyuzhoufm.com/episode/12345678"
        assert UrlValidator.normalize_to_url(episode_id) == expected_url

        # 测试已有效的 URL 直接返回
        valid_url = "https://www.xiaoyuzhoufm.com/episode/test123"
        assert UrlValidator.normalize_to_url(valid_url) == valid_url

        # 测试无效输入抛出异常
        invalid_inputs = [
            "https://example.com/episode/123",  # 错误的域名
            "http://www.xiaoyuzhoufm.com/episode/123",  # 错误的协议
            "",  # 空字符串
            "/invalid/path",  # 包含路径但不是有效URL
        ]

        for invalid_input in invalid_inputs:
            with pytest.raises(ParseError):
                UrlValidator.normalize_to_url(invalid_input)

    def test_extract_episode_id_invalid_url(self):
        """测试从无效URL提取节目ID"""
        with pytest.raises(ParseError):
            UrlValidator.extract_episode_id("https://example.com/invalid")


class TestHtmlFallbackParser:
    """测试HTML回退解析器"""

    def test_parser_name(self):
        """测试解析器名称"""
        parser = HtmlFallbackParser()
        assert parser.name == "html_fallback"

    @pytest.mark.asyncio
    async def test_extract_title_from_html(self):
        """测试从HTML提取标题"""
        parser = HtmlFallbackParser()

        html_content = """
        <html>
            <head>
                <title>测试节目 - 测试播客 | 小宇宙</title>
            </head>
            <body></body>
        </html>
        """

        episode_info = await parser.parse_episode_info(html_content, "test_url")
        assert episode_info.title == "测试节目 - 测试播客"

    @pytest.mark.asyncio
    async def test_extract_audio_url_from_html(self):
        """测试从HTML提取音频URL"""
        parser = HtmlFallbackParser()

        html_content = """
        <html>
            <body>
                <audio src="https://example.com/audio.mp3"></audio>
            </body>
        </html>
        """

        audio_url = await parser.extract_audio_url(html_content, "test_url")
        assert audio_url == "https://example.com/audio.mp3"

    @pytest.mark.asyncio
    async def test_extract_audio_url_not_found(self):
        """测试音频URL未找到"""
        parser = HtmlFallbackParser()

        html_content = """
        <html>
            <body>
                <p>No audio here</p>
            </body>
        </html>
        """

        audio_url = await parser.extract_audio_url(html_content, "test_url")
        assert audio_url is None


class TestJsonScriptParserOffline:
    """测试JsonScriptParser - 使用离线数据"""

    @pytest.mark.asyncio
    async def test_parse_episode_info_with_real_data(
        self, test_data_manager, sample_urls
    ):
        """测试使用真实HTML数据解析episode信息"""
        parser = JsonScriptParser()

        # 测试第一个URL
        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        # 验证基本信息
        assert episode_info.title != "未知标题"
        assert episode_info.podcast.title != "未知播客"
        # 注意：JSON-LD数据中没有作者信息，所以author可能是默认值
        assert episode_info.eid != ""
        assert episode_info.duration > 0  # 应该解析出正确的时长

        # 验证Show Notes已被提取且不为空
        assert episode_info.shownotes != ""
        assert len(episode_info.shownotes) > 100  # 应该是完整的Show Notes

        print(f"Episode Title: {episode_info.title}")
        print(f"Podcast: {episode_info.podcast.title} - {episode_info.podcast.author}")
        print(f"Show Notes length: {len(episode_info.shownotes)}")

    @pytest.mark.asyncio
    async def test_extract_audio_url_with_real_data(
        self, test_data_manager, sample_urls
    ):
        """测试使用真实HTML数据提取音频URL"""
        parser = JsonScriptParser()

        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        audio_url = await parser.extract_audio_url(html_content, test_url)

        assert audio_url is not None
        assert audio_url.startswith("https://")
        assert any(ext in audio_url for ext in [".mp3", ".m4a", ".wav"])

        print(f"Extracted audio URL: {audio_url}")

    @pytest.mark.asyncio
    async def test_show_notes_extraction_completeness(
        self, test_data_manager, sample_urls
    ):
        """测试Show Notes提取的完整性"""
        parser = JsonScriptParser()

        for i, test_url in enumerate(sample_urls[:2]):  # 测试前两个URL
            episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
            filename = f"episode_{episode_id}.html"

            html_content = await test_data_manager.load_html(filename)

            # 直接提取HTML中的Show Notes
            html_show_notes = parser.extract_show_notes_from_html(html_content)

            # 解析完整的episode信息
            episode_info = await parser.parse_episode_info(html_content, test_url)

            print(f"\nTest URL {i+1}: {test_url}")
            print(f"HTML Show Notes length: {len(html_show_notes)}")
            print(f"Episode Show Notes length: {len(episode_info.shownotes)}")

            # 验证Show Notes内容
            assert len(html_show_notes) > 500  # HTML提取的应该很长
            assert (
                "时间轴" in episode_info.shownotes or "【" in episode_info.shownotes
            )  # 应包含典型内容
            assert (
                len(episode_info.shownotes) >= len(html_show_notes) * 0.8
            )  # 应该使用了HTML提取的内容


class TestCompositeParserOffline:
    """测试CompositeParser - 使用离线数据"""

    @pytest.mark.asyncio
    async def test_parse_with_mock_http(self, http_mocker, sample_urls):
        """测试使用Mock HTTP的组合解析器"""
        parser = CompositeParser()

        test_url = sample_urls[0]
        episode_info = await parser.parse_episode_info("dummy_html", test_url)

        # 由于我们的Mock还没有完全集成，这里先测试基本结构
        assert episode_info is not None
        print(f"Parsed episode: {episode_info.title}")


class TestOfflineIntegration:
    """离线集成测试"""

    @pytest.mark.asyncio
    async def test_all_sample_urls_parsing(self, test_data_manager, sample_urls):
        """测试所有样本URL的解析"""
        parser = JsonScriptParser()

        for i, test_url in enumerate(sample_urls):
            episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
            filename = f"episode_{episode_id}.html"

            try:
                html_content = await test_data_manager.load_html(filename)
                episode_info = await parser.parse_episode_info(html_content, test_url)

                print(f"\n✅ URL {i+1} 解析成功:")
                print(f"   标题: {episode_info.title}")
                print(f"   播客: {episode_info.podcast.title}")
                print(f"   时长: {episode_info.duration_minutes}分钟")
                print(f"   Show Notes长度: {len(episode_info.shownotes)}")

                # 基本验证
                assert episode_info.title != "未知标题"
                assert len(episode_info.shownotes) > 0

            except Exception as e:
                print(f"❌ URL {i+1} 解析失败: {e}")
                raise
