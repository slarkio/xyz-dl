"""Show Notes下载功能测试

验证Markdown文件生成和下载功能的完整性
"""

import os
import pytest
from pathlib import Path

from src.xyz_dl.parsers import JsonScriptParser
from src.xyz_dl.downloader import XiaoYuZhouDL


class TestShowNotesDownload:
    """Show Notes下载功能测试"""

    @pytest.mark.asyncio
    async def test_show_notes_markdown_generation(self, test_data_manager, sample_urls):
        """测试Show Notes Markdown文件生成"""
        parser = JsonScriptParser()

        # 使用第一个样本URL
        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        # 验证Show Notes内容结构
        assert episode_info.shownotes != ""
        assert len(episode_info.shownotes) > 500

        # 验证包含Markdown格式元素（链接格式）
        assert "[" in episode_info.shownotes and "](" in episode_info.shownotes
        assert "http" in episode_info.shownotes  # 应该包含链接

        print(f"Show Notes preview (first 200 chars):")
        print(episode_info.shownotes[:200])

    @pytest.mark.asyncio
    async def test_show_notes_content_structure(self, test_data_manager, sample_urls):
        """测试Show Notes内容结构和完整性"""
        parser = JsonScriptParser()

        for i, test_url in enumerate(sample_urls[:2]):  # 测试前两个URL
            episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
            filename = f"episode_{episode_id}.html"

            html_content = await test_data_manager.load_html(filename)
            episode_info = await parser.parse_episode_info(html_content, test_url)

            print(f"\n=== 测试URL {i+1}: {episode_info.title} ===")
            print(f"Show Notes 长度: {len(episode_info.shownotes)} 字符")

            # 检查Show Notes内容的关键元素
            show_notes = episode_info.shownotes

            # 验证包含时间轴信息
            assert "时间轴" in show_notes or ":" in show_notes[:100]

            # 验证包含链接格式
            link_count = show_notes.count("](")
            print(f"包含 {link_count} 个Markdown链接")
            assert link_count > 0

            # 验证包含图片
            image_count = show_notes.count("![")
            print(f"包含 {image_count} 个图片")

            # 验证段落结构
            paragraph_count = show_notes.count("\n\n")
            print(f"包含 {paragraph_count} 个段落分隔")
            assert paragraph_count > 5  # 应该有多个段落

    @pytest.mark.asyncio
    async def test_downloader_show_notes_integration(
        self, test_data_manager, test_download_dir, sample_urls, http_mocker
    ):
        """测试下载器的Show Notes集成功能"""
        # 使用Mock HTTP来避免实际网络请求
        downloader = XiaoYuZhouDL()

        test_url = sample_urls[0]

        # 由于我们的Mock HTTP还需要完善，这里先测试解析部分
        parser = JsonScriptParser()
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        # 模拟下载器生成Markdown文件的过程
        markdown_content = self._generate_markdown_content(episode_info)

        # 验证生成的Markdown内容
        assert markdown_content.startswith("# ")  # 标题
        assert episode_info.title in markdown_content
        assert episode_info.podcast.title in markdown_content
        assert "## Show Notes" in markdown_content

        print(f"生成的Markdown内容长度: {len(markdown_content)}")
        print("Markdown内容预览:")
        print(markdown_content[:500] + "...")

    def _generate_markdown_content(self, episode_info) -> str:
        """生成Markdown内容（模拟下载器逻辑）"""
        lines = [
            f"# {episode_info.title}",
            "",
            f"**播客**: {episode_info.podcast.title}",
            f"**主播**: {episode_info.podcast.author}",
            f"**时长**: {episode_info.duration_minutes}分钟",
            f"**发布日期**: {episode_info.formatted_pub_date}",
            "",
            "## Show Notes",
            "",
            episode_info.shownotes,
        ]

        return "\n".join(lines)

    @pytest.mark.asyncio
    async def test_markdown_file_writing(self, test_download_dir):
        """测试Markdown文件写入功能"""
        test_content = """# 测试节目

**播客**: 测试播客
**时长**: 60分钟

## Show Notes

这是测试的Show Notes内容，包含：

- 列表项1
- 列表项2

[测试链接](https://example.com)

**粗体文本**

普通段落文本。
"""

        # 写入测试文件
        test_file_path = Path(test_download_dir) / "test_episode.md"

        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(test_content)

        # 验证文件存在和内容正确
        assert test_file_path.exists()

        with open(test_file_path, "r", encoding="utf-8") as f:
            read_content = f.read()

        assert read_content == test_content
        assert "测试节目" in read_content
        assert "Show Notes" in read_content

        # 清理测试文件
        test_file_path.unlink()

    @pytest.mark.asyncio
    async def test_filename_generation_and_sanitization(self, sample_urls):
        """测试文件名生成和清理功能"""
        from src.xyz_dl.downloader import XiaoYuZhouDL

        downloader = XiaoYuZhouDL()

        # 测试正常文件名生成
        normal_title = "正常的播客节目标题"
        author = "播客主播"
        filename = downloader._create_safe_filename(normal_title, author)

        assert filename.endswith(".md")
        assert "正常的播客节目标题" in filename
        assert "播客主播" in filename

        # 测试包含特殊字符的文件名清理
        special_title = '节目标题：包含/特殊\\字符<>|和"引号?'
        special_author = "作者名*字"
        safe_filename = downloader._create_safe_filename(special_title, special_author)

        # 验证特殊字符被清理
        illegal_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]
        for char in illegal_chars:
            assert char not in safe_filename

        # 验证文件名长度限制
        very_long_title = "这是一个" + "非常" * 50 + "长的标题"
        long_filename = downloader._create_safe_filename(very_long_title, author)

        assert len(long_filename) <= 250  # 考虑文件扩展名

        print(f"正常文件名: {filename}")
        print(f"清理后文件名: {safe_filename}")
        print(f"长文件名截断: {long_filename}")


class TestShowNotesFormatting:
    """Show Notes格式化测试"""

    @pytest.mark.asyncio
    async def test_markdown_link_formatting(self, test_data_manager, sample_urls):
        """测试Markdown链接格式化"""
        parser = JsonScriptParser()

        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        show_notes = episode_info.shownotes

        # 检查链接格式
        import re

        markdown_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", show_notes)

        print(f"发现 {len(markdown_links)} 个Markdown格式链接:")
        for i, (text, url) in enumerate(markdown_links[:5]):  # 显示前5个
            print(f"  {i+1}. [{text}]({url})")
            assert text.strip() != ""  # 链接文本不能为空
            assert url.startswith("http")  # URL应该是完整的

    @pytest.mark.asyncio
    async def test_timestamp_formatting(self, test_data_manager, sample_urls):
        """测试时间戳格式化"""
        parser = JsonScriptParser()

        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        show_notes = episode_info.shownotes

        # 检查时间戳格式（如：**01:30** 或 01:30）
        import re

        timestamp_patterns = [
            r"\*\*\d{1,2}:\d{2}\*\*",  # **01:30**
            r"\*\*\d{1,2}:\d{2}:\d{2}\*\*",  # **01:30:45**
            r"\d{1,2}:\d{2}",  # 01:30
        ]

        total_timestamps = 0
        for pattern in timestamp_patterns:
            timestamps = re.findall(pattern, show_notes)
            total_timestamps += len(timestamps)

            if timestamps:
                print(f"找到时间戳格式 '{pattern}': {len(timestamps)} 个")
                for ts in timestamps[:3]:  # 显示前3个例子
                    print(f"  - {ts}")

        assert total_timestamps > 5  # 应该包含多个时间戳

    @pytest.mark.asyncio
    async def test_image_embedding(self, test_data_manager, sample_urls):
        """测试图片嵌入"""
        parser = JsonScriptParser()

        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        show_notes = episode_info.shownotes

        # 检查图片Markdown格式
        import re

        images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", show_notes)

        print(f"发现 {len(images)} 个图片:")
        for i, (alt_text, url) in enumerate(images):
            print(f"  {i+1}. ![{alt_text}]({url})")
            assert url.startswith("http")  # 图片URL应该是完整的
            assert "image.xyzcdn.net" in url  # 应该是小宇宙的CDN

        assert len(images) > 0  # 应该包含图片


class TestShowNotesQuality:
    """Show Notes质量测试"""

    @pytest.mark.asyncio
    async def test_content_completeness_comparison(
        self, test_data_manager, sample_urls
    ):
        """测试内容完整性对比"""
        parser = JsonScriptParser()

        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)

        # 直接从HTML提取Show Notes
        html_show_notes = parser.extract_show_notes_from_html(html_content)

        # 通过完整解析流程获取Show Notes
        episode_info = await parser.parse_episode_info(html_content, test_url)
        parsed_show_notes = episode_info.shownotes

        print(f"HTML提取长度: {len(html_show_notes)}")
        print(f"解析后长度: {len(parsed_show_notes)}")
        print(f"长度差异: {abs(len(html_show_notes) - len(parsed_show_notes))}")

        # 验证解析后的内容不小于HTML提取的内容
        assert len(parsed_show_notes) >= len(html_show_notes) * 0.9

        # 验证包含关键内容
        key_phrases = ["时间轴", "欢迎", "播客", "投资", "基金"]
        found_phrases = [
            phrase for phrase in key_phrases if phrase in parsed_show_notes
        ]

        print(f"包含关键词: {found_phrases}")
        assert len(found_phrases) >= 3  # 应该包含大部分关键词

    @pytest.mark.asyncio
    async def test_multilingual_content_handling(self, test_data_manager, sample_urls):
        """测试多语言内容处理"""
        parser = JsonScriptParser()

        # 测试所有样本URL以确保多样性
        for i, test_url in enumerate(sample_urls):
            episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
            filename = f"episode_{episode_id}.html"

            html_content = await test_data_manager.load_html(filename)
            episode_info = await parser.parse_episode_info(html_content, test_url)

            show_notes = episode_info.shownotes

            # 验证中文内容处理
            chinese_chars = sum(
                1 for char in show_notes if "\u4e00" <= char <= "\u9fff"
            )
            english_chars = sum(
                1 for char in show_notes if char.isalpha() and ord(char) < 256
            )

            print(f"\nURL {i+1}: {episode_info.title}")
            print(f"中文字符: {chinese_chars}, 英文字符: {english_chars}")

            assert chinese_chars > 100  # 应该包含大量中文
            assert len(show_notes.encode("utf-8")) > len(
                show_notes
            )  # UTF-8编码长度应该更大

    @pytest.mark.asyncio
    async def test_show_notes_no_html_tags(self, test_data_manager, sample_urls):
        """测试Show Notes不包含HTML标签"""
        parser = JsonScriptParser()

        test_url = sample_urls[0]
        episode_id = test_url.split("/episode/")[-1].split("?")[0][:12]
        filename = f"episode_{episode_id}.html"

        html_content = await test_data_manager.load_html(filename)
        episode_info = await parser.parse_episode_info(html_content, test_url)

        show_notes = episode_info.shownotes

        # 检查是否包含HTML标签
        import re

        html_tags = re.findall(r"<[^>]+>", show_notes)

        print(f"发现HTML标签: {len(html_tags)}")
        for tag in html_tags[:5]:  # 显示前5个
            print(f"  - {tag}")

        # Show Notes应该是纯Markdown，不应该包含HTML标签
        assert len(html_tags) == 0, f"Show Notes中不应该包含HTML标签: {html_tags}"
