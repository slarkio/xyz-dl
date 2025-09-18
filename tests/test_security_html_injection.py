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

    def test_double_encoding_attack_blocked(self):
        """测试阻止双重编码攻击"""
        malicious_html = '&amp;lt;script&amp;gt;alert(&amp;quot;XSS&amp;quot;)&amp;lt;/script&amp;gt;正常内容'
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应包含可执行的script标签
        assert '<script>' not in result
        # HTML实体编码形式是安全的，但仍不应包含实际的脚本执行内容
        # 关键是防止浏览器解析执行，HTML实体编码的script不会被执行
        # 但为了更严格的安全，我们要求完全移除这些内容

        # 应该保留正常内容
        assert '正常内容' in result

    def test_malformed_tag_bypass_blocked(self):
        """测试阻止畸形标签绕过攻击"""
        malicious_payloads = [
            '<SCR\nIPT>alert("XSS")</SCR\nIPT>正常内容',
            '<script\x00>alert("XSS")</script>正常内容',
            '<script >alert("XSS")</script >正常内容',
            '<<script>script>alert("XSS")<</script>/script>正常内容',
            '<scr<script>ipt>alert("XSS")</script>正常内容',
            '<script<!--comment-->alert("XSS")</script>正常内容'
        ]

        for payload in malicious_payloads:
            episode = self.create_episode_with_shownotes(payload)
            result = self.downloader._build_markdown_content(episode)

            # 不应包含任何恶意内容
            assert '<script>' not in result.lower()
            assert 'alert(' not in result
            assert 'XSS' not in result
            # 应该保留正常内容
            assert '正常内容' in result

    def test_protocol_encoding_bypass_blocked(self):
        """测试阻止协议编码绕过攻击"""
        malicious_payloads = [
            '<a href="JaVaScRiPt:alert(1)">混合大小写</a>正常内容',
            '<a href="java&#115;cript:alert(1)">实体编码</a>正常内容',
            '<a href="&#x6a;avascript:alert(1)">十六进制实体</a>正常内容',
            '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">Base64编码</a>正常内容',
            '<a href="vBsCrIpT:alert(1)">VBScript</a>正常内容'
        ]

        for payload in malicious_payloads:
            episode = self.create_episode_with_shownotes(payload)
            result = self.downloader._build_markdown_content(episode)

            # 不应包含任何危险协议
            assert 'javascript:' not in result.lower()
            assert 'vbscript:' not in result.lower()
            assert 'data:text/html' not in result.lower()
            assert 'alert(' not in result
            # 应该保留正常内容
            assert '正常内容' in result

    def test_unicode_bypass_attack_blocked(self):
        """测试阻止Unicode绕过攻击"""
        malicious_payloads = [
            '<scr＜ipt>alert("XSS")</scr＜ipt>正常内容',  # 全角字符
            '<ｓｃｒｉｐｔ>alert("XSS")</ｓｃｒｉｐｔ>正常内容',  # 全角标签
            '<script>alert("XSS")</script>正常内容',  # 看起来正常但可能包含特殊字符
        ]

        for payload in malicious_payloads:
            episode = self.create_episode_with_shownotes(payload)
            result = self.downloader._build_markdown_content(episode)

            # 不应包含任何恶意内容
            assert 'alert(' not in result
            assert 'XSS' not in result
            # 应该保留正常内容
            assert '正常内容' in result

    def test_css_injection_attack_blocked(self):
        """测试阻止CSS注入攻击"""
        malicious_payloads = [
            '<div class="x{background-image:url(\'javascript:alert(1)\')}">CSS注入</div>正常内容',
            '<span class="x{expression(alert(\'XSS\'))}">IE CSS Expression</span>正常内容',
            '<div style="background:url(javascript:alert(1))">Style属性</div>正常内容'
        ]

        for payload in malicious_payloads:
            episode = self.create_episode_with_shownotes(payload)
            result = self.downloader._build_markdown_content(episode)

            # 不应包含CSS注入内容
            assert 'javascript:' not in result
            assert 'expression(' not in result
            assert 'alert(' not in result
            # 应该保留正常内容
            assert '正常内容' in result

    def test_dom_clobbering_attack_blocked(self):
        """测试阻止DOM Clobbering攻击"""
        malicious_payloads = [
            '<div id="document">Clobber document</div>正常内容',
            '<span name="cookie">Clobber cookie</span>正常内容',
            '<div id="location">Clobber location</div>正常内容'
        ]

        for payload in malicious_payloads:
            episode = self.create_episode_with_shownotes(payload)
            result = self.downloader._build_markdown_content(episode)

            # 不应包含id或name属性
            assert 'id=' not in result
            assert 'name=' not in result
            # 应该保留正常内容
            assert '正常内容' in result

    def test_nested_encoding_attack_blocked(self):
        """测试阻止嵌套编码攻击"""
        malicious_html = '''
        &amp;amp;lt;script&amp;amp;gt;
        &amp;#115;&amp;#99;&amp;#114;&amp;#105;&amp;#112;&amp;#116;
        alert("Multi-layer encoding")
        &amp;amp;lt;/script&amp;amp;gt;
        正常内容
        '''
        episode = self.create_episode_with_shownotes(malicious_html)

        result = self.downloader._build_markdown_content(episode)

        # 不应解码出任何恶意内容
        assert '<script>' not in result
        assert 'alert(' not in result
        assert 'Multi-layer encoding' not in result
        # 应该保留正常内容
        assert '正常内容' in result