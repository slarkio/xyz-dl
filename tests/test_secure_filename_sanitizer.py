"""测试安全文件名清理器

验证新的安全文件名清理器能够正确处理各种安全威胁
"""

import platform

import pytest

from src.xyz_dl.filename_sanitizer import (
    LegacyFilenameSanitizer,
    SecureFilenameSanitizer,
    create_filename_sanitizer,
)


class TestSecureFilenameSanitizer:
    """测试安全文件名清理器"""

    def setup_method(self):
        """测试方法设置"""
        self.sanitizer = SecureFilenameSanitizer()

    def test_unicode_control_characters_removal(self):
        """测试Unicode控制字符移除"""
        test_cases = [
            ("normal_name\u0000null_byte", "normal_namenull_byte"),
            ("file\u202ename", "filename"),  # 右到左覆盖字符
            ("file\u200bname", "filename"),  # 零宽度空格
            ("file\u00adname", "filename"),  # 软连字符
            ("file\u0085name", "filename"),  # NEL字符
            ("file\u2028name", "filename"),  # 行分隔符
            ("file\u2029name", "filename"),  # 段分隔符
        ]

        for malicious_input, expected_safe in test_cases:
            result = self.sanitizer.sanitize(malicious_input)
            assert result == expected_safe, f"Failed for: {repr(malicious_input)}"
            # 确保不包含危险字符
            assert "\u0000" not in result
            assert "\u202e" not in result
            assert "\u200b" not in result

    def test_windows_reserved_names_handling(self):
        """测试Windows保留名称处理"""
        if platform.system() == "Windows":
            reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
            for reserved_name in reserved_names:
                result = self.sanitizer.sanitize(reserved_name)
                # 应该被修改为安全名称
                assert result.upper() != reserved_name.upper()
                assert "file_" in result or result != reserved_name

    def test_platform_specific_characters(self):
        """测试平台特定字符处理"""
        dangerous_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]

        for char in dangerous_chars:
            test_name = f"file{char}name"
            result = self.sanitizer.sanitize(test_name)
            # 危险字符应该被移除
            assert char not in result, f"Dangerous char '{char}' not removed"

    def test_unicode_normalization(self):
        """测试Unicode规范化"""
        # 测试不同Unicode表示的相同字符
        filename1 = "café"  # 使用组合字符 é
        filename2 = "café"  # 使用预组合字符 é

        result1 = self.sanitizer.sanitize(filename1)
        result2 = self.sanitizer.sanitize(filename2)

        # 规范化后应该相同
        assert result1 == result2

    def test_safe_truncation(self):
        """测试安全截断"""
        # 测试基本截断
        long_name = "a" * 250
        result = self.sanitizer.sanitize(long_name, max_length=100)
        assert len(result) <= 100

        # 测试带扩展名的截断
        long_name_with_ext = "a" * 250 + ".txt"
        result = self.sanitizer.sanitize(long_name_with_ext, max_length=50)
        assert len(result) <= 50
        assert result.endswith(".txt")

        # 测试恶意截断攻击
        malicious = "a" * 180 + "/../passwd"
        result = self.sanitizer.sanitize(malicious, max_length=200)
        assert "../" not in result

    def test_empty_and_whitespace_handling(self):
        """测试空值和空白字符处理"""
        test_cases = [
            ("", "untitled"),
            ("   ", "untitled"),
            ("...", "untitled"),
            ("   ..   ", "untitled"),
            ("\t\n\r", "untitled"),
        ]

        for input_name, expected in test_cases:
            result = self.sanitizer.sanitize(input_name)
            assert result == expected

    def test_path_traversal_prevention(self):
        """测试路径遍历攻击防护"""
        path_traversal_attacks = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "%2e%2e%2f",  # URL编码的../
        ]

        for attack in path_traversal_attacks:
            result = self.sanitizer.sanitize(attack)
            # 应该移除路径遍历字符
            assert "../" not in result
            assert "..\\" not in result

    def test_mixed_attacks(self):
        """测试混合攻击防护"""
        mixed_attacks = [
            "CON\u0000.txt",  # Windows保留名 + NULL字节
            "../\u202econ.txt",  # 路径遍历 + Unicode控制字符
            "a" * 180 + "/../passwd",  # 长度 + 路径遍历
        ]

        for attack in mixed_attacks:
            result = self.sanitizer.sanitize(attack)
            # 应该安全且不为空
            assert result
            assert len(result) > 0
            # 不应包含危险内容
            assert "\u0000" not in result
            assert "\u202e" not in result
            assert "../" not in result

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_windows_trailing_chars(self):
        """测试Windows文件名结尾字符处理"""
        windows_edge_cases = [
            ("filename.", "filename"),
            ("filename ", "filename"),
            ("filename..", "filename"),
            ("filename  ", "filename"),
        ]

        sanitizer = SecureFilenameSanitizer("Windows")
        for input_name, expected in windows_edge_cases:
            result = sanitizer.sanitize(input_name)
            assert result == expected

    def test_hidden_file_handling(self):
        """测试隐藏文件名处理"""
        # Unix系统中，以.开头的文件是隐藏文件
        hidden_names = [".hidden", "..hidden", "...hidden"]

        for hidden_name in hidden_names:
            result = self.sanitizer.sanitize(hidden_name)
            # 应该移除开头的点号
            assert not result.startswith(".")


class TestFilenameSanitizerFactory:
    """测试文件名清理器工厂函数"""

    def test_create_secure_sanitizer(self):
        """测试创建安全清理器"""
        sanitizer = create_filename_sanitizer(secure=True)
        assert isinstance(sanitizer, SecureFilenameSanitizer)

    def test_create_legacy_sanitizer(self):
        """测试创建传统清理器"""
        sanitizer = create_filename_sanitizer(secure=False)
        assert isinstance(sanitizer, LegacyFilenameSanitizer)

    def test_platform_specific_creation(self):
        """测试平台特定创建"""
        windows_sanitizer = create_filename_sanitizer(
            secure=True, platform_name="Windows"
        )
        unix_sanitizer = create_filename_sanitizer(secure=True, platform_name="Linux")

        assert windows_sanitizer.platform == "Windows"
        assert unix_sanitizer.platform == "Linux"


class TestLegacyCompatibility:
    """测试向后兼容性"""

    def test_legacy_sanitizer_behavior(self):
        """测试传统清理器行为"""
        legacy = LegacyFilenameSanitizer()
        secure = SecureFilenameSanitizer()

        # 对于简单情况，结果应该相似
        simple_name = "normal_filename"
        legacy_result = legacy.sanitize(simple_name)
        secure_result = secure.sanitize(simple_name)

        assert legacy_result == secure_result == simple_name

    def test_security_differences(self):
        """测试安全性差异"""
        legacy = LegacyFilenameSanitizer()
        secure = SecureFilenameSanitizer()

        # Unicode控制字符 - 安全清理器应该处理得更好
        dangerous_input = "file\u0000name"

        legacy_result = legacy.sanitize(dangerous_input)
        secure_result = secure.sanitize(dangerous_input)

        # 安全清理器应该移除NULL字节
        assert "\u0000" in legacy_result  # 传统清理器无法处理
        assert "\u0000" not in secure_result  # 安全清理器能处理


class TestRealWorldScenarios:
    """测试真实世界场景"""

    def setup_method(self):
        """测试方法设置"""
        self.sanitizer = SecureFilenameSanitizer()

    def test_chinese_podcast_names(self):
        """测试中文播客名称"""
        chinese_names = [
            "第1期 - 主播名字",
            "科技播客：AI的未来",
            "【特别节目】春节特辑",
        ]

        for name in chinese_names:
            result = self.sanitizer.sanitize(name)
            assert result  # 应该有结果
            assert len(result) > 0  # 不应为空

    def test_mixed_language_content(self):
        """测试混合语言内容"""
        mixed_content = [
            "Podcast第1期 - Host名字",
            "Tech播客: English & 中文",
            "🎵 Music & 音乐 Show",
        ]

        for content in mixed_content:
            result = self.sanitizer.sanitize(content)
            assert result
            # 应该保留可打印字符
            assert len(result) > 0

    def test_common_special_chars(self):
        """测试常见特殊字符"""
        special_chars_content = [
            "Episode #1 - Host",
            "Show @ 2024-01-01",
            "Tech & Science",
            "Q&A Session",
        ]

        for content in special_chars_content:
            result = self.sanitizer.sanitize(content)
            # 应该保留安全的特殊字符
            assert result
            assert len(result) > 0
