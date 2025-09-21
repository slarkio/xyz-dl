"""异常场景测试套件

测试各种异常情况下的错误处理和恢复机制
"""

import pytest
import aiohttp
from unittest.mock import patch

from src.xyz_dl.parsers import JsonScriptParser, CompositeParser
from src.xyz_dl.exceptions import ParseError, NetworkError
from .utils.mock_http import (
    create_network_error,
    create_timeout_error,
    create_http_error,
)


class TestNetworkExceptions:
    """网络异常测试"""

    @pytest.mark.asyncio
    async def test_connection_error(self, http_mocker, sample_urls):
        """测试连接错误处理"""
        test_url = sample_urls[0]

        # 模拟连接错误
        http_mocker.set_failure(test_url, create_network_error("Connection refused"))

        parser = JsonScriptParser()

        with pytest.raises(NetworkError) as exc_info:
            # 注意：这里需要使用CompositeParser并通过parse_episode_from_url
            # 因为JsonScriptParser本身不处理网络请求
            from src.xyz_dl.parsers import parse_episode_from_url

            await parse_episode_from_url(test_url)

        assert "Connection refused" in str(exc_info.value) or "Network error" in str(
            exc_info.value
        )

    @pytest.mark.asyncio
    async def test_timeout_error(self, http_mocker, sample_urls):
        """测试超时错误处理"""
        test_url = sample_urls[0]

        # 模拟超时错误
        http_mocker.set_failure(test_url, create_timeout_error("Request timeout"))

        with pytest.raises(NetworkError) as exc_info:
            from src.xyz_dl.parsers import parse_episode_from_url

            await parse_episode_from_url(test_url)

        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_http_404_error(self, http_mocker, sample_urls):
        """测试404错误处理"""
        test_url = sample_urls[0]

        # 模拟404错误
        http_mocker.set_failure(test_url, create_http_error(404, "Not Found"))

        with pytest.raises(NetworkError) as exc_info:
            from src.xyz_dl.parsers import parse_episode_from_url

            await parse_episode_from_url(test_url)

        assert "404" in str(exc_info.value) or "Not Found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_http_500_error(self, http_mocker, sample_urls):
        """测试500服务器错误处理"""
        test_url = sample_urls[0]

        # 模拟500错误
        http_mocker.set_failure(
            test_url, create_http_error(500, "Internal Server Error")
        )

        with pytest.raises(NetworkError) as exc_info:
            from src.xyz_dl.parsers import parse_episode_from_url

            await parse_episode_from_url(test_url)

        assert "500" in str(exc_info.value) or "Server Error" in str(exc_info.value)


class TestParsingExceptions:
    """解析异常测试"""

    @pytest.mark.asyncio
    async def test_empty_html_content(self):
        """测试空HTML内容"""
        parser = JsonScriptParser()

        with pytest.raises(ParseError) as exc_info:
            await parser.parse_episode_info(
                "", "https://www.xiaoyuzhoufm.com/episode/test"
            )

        assert "Failed to extract episode data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_malformed_html_content(self):
        """测试格式错误的HTML内容"""
        parser = JsonScriptParser()

        malformed_html = (
            "<html><head><title>Test</title></head><body><p>Incomplete HTML"
        )

        with pytest.raises(ParseError) as exc_info:
            await parser.parse_episode_info(
                malformed_html, "https://www.xiaoyuzhoufm.com/episode/test"
            )

        assert "Failed to extract episode data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_json_script(self):
        """测试缺少JSON脚本的HTML"""
        parser = JsonScriptParser()

        html_without_json = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>No JSON data here</h1>
                <p>This page doesn't have any JSON-LD or JavaScript data</p>
            </body>
        </html>
        """

        with pytest.raises(ParseError) as exc_info:
            await parser.parse_episode_info(
                html_without_json, "https://www.xiaoyuzhoufm.com/episode/test"
            )

        assert "Failed to extract episode data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_json_ld_content(self):
        """测试无效的JSON-LD内容"""
        parser = JsonScriptParser()

        html_with_invalid_json = """
        <html>
            <head>
                <title>Test Page</title>
                <script name="schema:podcast-show" type="application/ld+json">
                    {invalid json content here}
                </script>
            </head>
            <body>
                <h1>Test</h1>
            </body>
        </html>
        """

        with pytest.raises(ParseError) as exc_info:
            await parser.parse_episode_info(
                html_with_invalid_json, "https://www.xiaoyuzhoufm.com/episode/test"
            )

        assert "Failed to extract episode data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_incomplete_json_ld_data(self):
        """测试不完整的JSON-LD数据"""
        parser = JsonScriptParser()

        # JSON-LD缺少必要字段
        html_with_incomplete_json = """
        <html>
            <head>
                <title>Test Page</title>
                <script name="schema:podcast-show" type="application/ld+json">
                {
                    "@context": "https://schema.org/",
                    "@type": "PodcastEpisode"
                }
                </script>
            </head>
            <body>
                <h1>Test</h1>
            </body>
        </html>
        """

        # 应该能解析，但会使用默认值
        episode_info = await parser.parse_episode_info(
            html_with_incomplete_json, "https://www.xiaoyuzhoufm.com/episode/test"
        )

        # 验证使用了默认值
        assert episode_info.title == "未知标题"
        assert episode_info.podcast.title == "未知播客"
        assert episode_info.duration == 0


class TestShowNotesExtractionExceptions:
    """Show Notes提取异常测试"""

    @pytest.mark.asyncio
    async def test_missing_show_notes_section(self, test_data_manager, sample_urls):
        """测试缺少Show Notes部分的HTML"""
        parser = JsonScriptParser()

        html_without_show_notes = """
        <html>
            <head>
                <title>Test Page</title>
                <script name="schema:podcast-show" type="application/ld+json">
                {
                    "@context": "https://schema.org/",
                    "@type": "PodcastEpisode",
                    "name": "Test Episode",
                    "partOfSeries": {"name": "Test Podcast"},
                    "timeRequired": "PT60M",
                    "description": "Test description"
                }
                </script>
            </head>
            <body>
                <h1>Test Episode</h1>
                <p>No show notes section here</p>
            </body>
        </html>
        """

        episode_info = await parser.parse_episode_info(
            html_without_show_notes, "https://www.xiaoyuzhoufm.com/episode/test"
        )

        # 应该使用JSON-LD中的description
        assert episode_info.shownotes == "Test description"

    @pytest.mark.asyncio
    async def test_empty_show_notes_content(self):
        """测试空的Show Notes内容"""
        parser = JsonScriptParser()

        html_with_empty_show_notes = """
        <html>
            <head>
                <title>Test Page</title>
                <script name="schema:podcast-show" type="application/ld+json">
                {
                    "@context": "https://schema.org/",
                    "@type": "PodcastEpisode",
                    "name": "Test Episode",
                    "partOfSeries": {"name": "Test Podcast"},
                    "timeRequired": "PT60M",
                    "description": "Test description"
                }
                </script>
            </head>
            <body>
                <section class="css-omm69k" aria-label="节目show notes">
                    <div class="sn-content">
                        <article>
                            <!-- Empty article -->
                        </article>
                    </div>
                </section>
            </body>
        </html>
        """

        episode_info = await parser.parse_episode_info(
            html_with_empty_show_notes, "https://www.xiaoyuzhoufm.com/episode/test"
        )

        # 应该回退到JSON-LD中的description
        assert episode_info.shownotes == "Test description"


class TestCompositeParserFallback:
    """组合解析器回退机制测试"""

    @pytest.mark.asyncio
    async def test_fallback_to_html_parser(self):
        """测试回退到HTML解析器"""
        parser = CompositeParser()

        # 使用只有基本HTML结构的内容，没有JSON数据
        basic_html = """
        <html>
            <head>
                <title>Test Episode - Test Podcast | 小宇宙</title>
                <meta name="description" content="This is a test episode description">
            </head>
            <body>
                <h1>Test Episode</h1>
                <audio src="https://example.com/test.mp3"></audio>
            </body>
        </html>
        """

        episode_info = await parser.parse_episode_info(
            basic_html, "https://www.xiaoyuzhoufm.com/episode/test"
        )

        # 验证使用了HTML解析器的结果
        assert episode_info.title == "Test Episode - Test Podcast"
        assert "test" in episode_info.eid.lower()

    @pytest.mark.asyncio
    async def test_all_parsers_fail(self):
        """测试所有解析器都失败的情况"""
        parser = CompositeParser()

        # 使用None作为HTML内容，这应该会让BeautifulSoup解析失败
        # 或者使用空字符串，然后mock BeautifulSoup让它抛出异常
        with patch('src.xyz_dl.parsers.BeautifulSoup') as mock_bs:
            mock_bs.side_effect = Exception("HTML parsing failed")

            with pytest.raises(ParseError) as exc_info:
                await parser.parse_episode_info(
                    "<html></html>", "https://www.xiaoyuzhoufm.com/episode/test"
                )

            assert "All parsers failed" in str(exc_info.value) or "HTML parsing failed" in str(exc_info.value)


class TestFileOperationExceptions:
    """文件操作异常测试"""

    @pytest.mark.asyncio
    async def test_invalid_download_directory(self, test_download_dir):
        """测试无效的下载目录"""
        # 这个测试主要是为了验证下载器的异常处理
        # 实际的文件下载测试在其他测试文件中

        # 创建一个无效的目录路径
        invalid_dir = "/invalid/nonexistent/directory/path"

        # 验证目录不存在
        import os

        assert not os.path.exists(invalid_dir)

        # 这里主要是验证测试基础设施的工作
        assert os.path.exists(test_download_dir)

    @pytest.mark.asyncio
    async def test_test_data_file_not_found(self, test_data_manager):
        """测试测试数据文件不存在"""
        with pytest.raises(FileNotFoundError):
            await test_data_manager.load_html("nonexistent_file.html")


class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_extremely_long_show_notes(self, test_data_manager, sample_urls):
        """测试极长的Show Notes处理"""
        parser = JsonScriptParser()

        # 使用真实数据测试
        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        # 验证能处理长内容
        assert len(episode_info.shownotes) > 1000
        assert isinstance(episode_info.shownotes, str)

    @pytest.mark.asyncio
    async def test_unicode_content_handling(self):
        """测试Unicode内容处理"""
        parser = JsonScriptParser()

        # 包含各种Unicode字符的HTML
        unicode_html = """
        <html>
            <head>
                <title>测试节目 - 播客名称 | 小宇宙</title>
                <script name="schema:podcast-show" type="application/ld+json">
                {
                    "@context": "https://schema.org/",
                    "@type": "PodcastEpisode",
                    "name": "测试节目：特殊字符 & 符号 © ® ™ 🎧",
                    "partOfSeries": {"name": "播客名称"},
                    "timeRequired": "PT30M",
                    "description": "包含emoji的描述 🎵 和特殊字符 & < > \\\\ \\""
                }
                </script>
            </head>
            <body>
                <h1>Unicode Content Test</h1>
            </body>
        </html>
        """

        episode_info = await parser.parse_episode_info(
            unicode_html, "https://www.xiaoyuzhoufm.com/episode/test"
        )

        # 验证Unicode字符正确处理
        assert "🎧" in episode_info.title
        assert "🎵" in episode_info.shownotes
        assert "播客名称" == episode_info.podcast.title
