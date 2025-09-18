"""
HTML注入安全测试
测试Show Notes处理中的HTML注入漏洞修复
"""
import pytest
from xyz_dl.downloader import XiaoYuZhouDL
from xyz_dl.models import EpisodeInfo, PodcastInfo


class TestHtmlInjectionSecurity:
    """HTML注入安全测试类"""

    def setup_method(self):
        """测试前设置"""
        self.downloader = XiaoYuZhouDL()

    def create_episode_with_shownotes(self, shownotes_content) -> EpisodeInfo:
        """创建包含指定Show Notes的EpisodeInfo"""
        podcast = PodcastInfo(
            title="测试播客",
            author="测试主播",
            podcast_id="test123",
            podcast_url="https://test.com"
        )

        return EpisodeInfo(
            title="测试节目",
            eid="test456",
            shownotes=shownotes_content,
            podcast=podcast,
            audio_url="https://test.com/audio.mp3"
        )

    def test_script_tag_injection_blocked(self):
        """测试阻止script标签注入"""
        malicious_html = '<script>alert("XSS")</script>正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含script标签或其内容
        assert '<script>' not in result
        assert 'alert(' not in result
        assert 'XSS' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_javascript_event_handler_blocked(self):
        """测试阻止JavaScript事件处理器"""
        malicious_html = '<img src="x" onerror="alert(1)">正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含事件处理器
        assert 'onerror=' not in result
        assert 'alert(1)' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_javascript_protocol_blocked(self):
        """测试阻止javascript:协议"""
        malicious_html = '<a href="javascript:alert(1)">链接</a>正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含javascript协议
        assert 'javascript:' not in result
        assert 'alert(1)' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_html_entity_attack_blocked(self):
        """测试阻止HTML实体攻击"""
        malicious_html = '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应解码恶意HTML实体
        assert '<script>' not in result
        assert 'alert(' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_iframe_injection_blocked(self):
        """测试阻止iframe注入"""
        malicious_html = '<iframe src="javascript:alert(1)"></iframe>正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含iframe标签
        assert '<iframe' not in result
        assert 'javascript:alert(1)' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_style_injection_blocked(self):
        """测试阻止style注入"""
        malicious_html = '<style>body{background:url("javascript:alert(1)")}</style>正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含style标签和javascript
        assert '<style>' not in result
        assert 'javascript:alert(1)' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_complex_nested_attack_blocked(self):
        """测试阻止复杂嵌套攻击"""
        malicious_html = '''
        <div onclick="alert(1)">
            <script>
                document.cookie = "stolen";
            </script>
            <p>正常内容</p>
        </div>
        '''
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含任何恶意内容
        assert 'onclick=' not in result
        assert '<script>' not in result
        assert 'document.cookie' not in result
        assert 'alert(1)' not in result
        # 应该保留正常内容
        assert '正常内容' in result

    def test_safe_html_tags_preserved(self):
        """测试安全HTML标签被正确转换"""
        safe_html = '''
        <p>这是段落</p>
        <br>
        <h1>标题</h1>
        <strong>粗体</strong>
        <em>斜体</em>
        <a href="https://example.com">安全链接</a>
        '''
        episode = self.create_episode_with_shownotes(safe_html)

        result = self.downloader._build_markdown_content(episode)

        # 应该保留或转换为Markdown格式的内容
        assert '这是段落' in result
        assert '标题' in result
        assert '粗体' in result
        assert '斜体' in result
        assert '安全链接' in result
        # 不应有原始HTML标签
        assert '<p>' not in result
        assert '<h1>' not in result

    def test_real_world_malicious_payload(self):
        """测试真实世界的恶意载荷"""
        # 模拟真实的XSS攻击载荷
        malicious_html = '''
        <img src=x onerror="eval(String.fromCharCode(97,108,101,114,116,40,49,41))">
        <svg onload="alert(1)">
        "><script>alert(document.domain)</script>
        javascript:/*--></title></style></textarea></script></xmp>
        <svg/onload='+/"/+/onmouseover=1/+/[*/[]/+alert(1)//'>
        正常的节目介绍内容
        '''
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 所有恶意内容都应被清理
        assert 'onerror=' not in result
        assert 'onload=' not in result
        assert 'onmouseover=' not in result
        assert '<script>' not in result
        assert 'alert(' not in result
        assert 'eval(' not in result
        assert 'document.domain' not in result
        # 正常内容应保留
        assert '正常的节目介绍内容' in result

    def test_empty_or_none_shownotes(self):
        """测试空或None的Show Notes"""
        # 测试None
        episode_none = self.create_episode_with_shownotes(None)
        result_none = self.downloader._build_markdown_content(episode_none)
        assert '暂无节目介绍' in result_none

        # 测试空字符串
        episode_empty = self.create_episode_with_shownotes("")
        result_empty = self.downloader._build_markdown_content(episode_empty)
        assert '暂无节目介绍' in result_empty

    def test_unicode_and_special_characters(self):
        """测试Unicode和特殊字符处理"""
        content_with_unicode = '''
        <p>包含中文：你好世界</p>
        <p>包含emoji：😀🎧📻</p>
        <p>包含特殊符号：@#$%^&*()</p>
        '''
        episode = self.create_episode_with_shownotes(content_with_unicode)

        result = self.downloader._build_markdown_content(episode)

        # Unicode内容应正确保留
        assert '你好世界' in result
        assert '😀🎧📻' in result
        # & 会被编码为 &amp; 这是正确的
        assert '@#$%^&amp;*()' in result or '@#$%^&*()' in result
        # HTML标签应被清理
        assert '<p>' not in result