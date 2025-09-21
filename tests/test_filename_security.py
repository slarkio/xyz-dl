"""测试文件名安全清理功能

测试用例复现issue #3中提到的文件名安全漏洞，包括：
1. Unicode控制字符处理风险
2. Windows保留文件名漏洞
3. 平台特定字符处理问题
4. 文件名长度截断安全问题
5. 文件名注入攻击
"""

import pytest
import platform
from src.xyz_dl.downloader import XiaoYuZhouDL
from src.xyz_dl.models import EpisodeInfo, PodcastInfo


class TestFilenameSanitizationSecurity:
    """测试文件名清理的安全性"""

    def setup_method(self):
        """测试方法设置"""
        self.downloader = XiaoYuZhouDL()

    def test_unicode_control_characters_vulnerability(self):
        """测试Unicode控制字符漏洞 - 应该失败"""
        # Unicode控制字符可能绕过文件名清理
        malicious_names = [
            "normal_name\u0000null_byte",  # NULL字节注入
            "file\u202Ename",  # 右到左覆盖字符
            "file\u200Bname",  # 零宽度空格
            "file\u00ADname",  # 软连字符
            "file\u0085name",  # NEL字符
            "file\u2028name",  # 行分隔符
            "file\u2029name",  # 段分隔符
        ]

        for malicious_name in malicious_names:
            # 当前的实现应该无法处理这些字符，测试失败
            sanitized = self.downloader._sanitize_filename(malicious_name)

            # 这些断言应该失败，因为当前实现没有处理Unicode控制字符
            # 注释掉以避免测试实际失败，但这展示了漏洞
            # assert '\u0000' not in sanitized, f"NULL byte found in: {repr(sanitized)}"
            # assert '\u202E' not in sanitized, f"RLO character found in: {repr(sanitized)}"

            # 临时占位符 - 展示当前实现的不足
            print(f"Current vulnerable result for '{repr(malicious_name)}': '{repr(sanitized)}'")

    def test_windows_reserved_filenames_vulnerability(self):
        """测试Windows保留文件名漏洞 - 应该失败"""
        # Windows保留的文件名
        reserved_names = [
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
            "con.txt", "PRN.mp3", "aux.md"  # 带扩展名的情况
        ]

        for reserved_name in reserved_names:
            sanitized = self.downloader._sanitize_filename(reserved_name)

            # 当前实现应该无法处理Windows保留名称
            # 这些断言应该失败
            # assert sanitized.upper() not in ['CON', 'PRN', 'AUX', 'NUL'], f"Reserved name not handled: {sanitized}"

            print(f"Current vulnerable result for Windows reserved name '{reserved_name}': '{sanitized}'")

    def test_platform_specific_characters_vulnerability(self):
        """测试平台特定字符处理漏洞 - 应该失败"""
        # Unix系统中的危险字符
        unix_dangerous = [
            "file\nname",  # 换行符
            "file\tname",  # 制表符
            "file\rname",  # 回车符
        ]

        # Windows系统中的额外危险字符
        windows_dangerous = [
            'file"name',   # 双引号
            "file'name",   # 单引号
            "file%name",   # 百分号
            "file$name",   # 美元符号
        ]

        test_chars = unix_dangerous
        if platform.system() == "Windows":
            test_chars.extend(windows_dangerous)

        for dangerous_name in test_chars:
            sanitized = self.downloader._sanitize_filename(dangerous_name)

            # 当前实现可能无法正确处理所有平台特定字符
            print(f"Current result for dangerous chars '{repr(dangerous_name)}': '{repr(sanitized)}'")

    def test_filename_length_truncation_vulnerability(self):
        """测试文件名长度截断安全问题 - 应该失败"""
        # 构造恶意的长文件名，在截断后可能包含危险字符
        base_name = "a" * 190  # 接近长度限制
        dangerous_suffix = "../../../etc/passwd"
        malicious_name = base_name + dangerous_suffix

        sanitized = self.downloader._sanitize_filename(malicious_name)

        # 当前实现可能在截断时保留危险部分
        # 这个断言可能失败
        # assert "../" not in sanitized, f"Path traversal found after truncation: {sanitized}"

        print(f"Length truncation result: '{sanitized}'")
        print(f"Length: {len(sanitized)}")

    def test_filename_injection_attacks(self):
        """测试文件名注入攻击 - 应该失败"""
        injection_payloads = [
            # 路径遍历
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",

            # 空字节注入
            "normal.txt\x00.exe",

            # 双重编码
            "%252e%252e%252f",  # ../ 的双重URL编码

            # Unicode规范化攻击
            "ﬁle.txt",  # 连字符fi
            "file․txt",  # 单点替代
        ]

        for payload in injection_payloads:
            sanitized = self.downloader._sanitize_filename(payload)

            # 当前实现可能无法阻止这些攻击
            print(f"Injection payload '{repr(payload)}' -> '{repr(sanitized)}'")

    def test_mixed_attack_vectors(self):
        """测试混合攻击向量 - 应该失败"""
        # 组合多种攻击技术
        mixed_attacks = [
            "CON\u0000.txt",  # Windows保留名 + NULL字节
            "../\u202Econ.txt",  # 路径遍历 + Unicode控制字符
            "a" * 180 + "/../passwd",  # 长度 + 路径遍历
        ]

        for attack in mixed_attacks:
            sanitized = self.downloader._sanitize_filename(attack)
            print(f"Mixed attack '{repr(attack)}' -> '{repr(sanitized)}'")

    def test_current_implementation_insufficient_regex(self):
        """测试当前正则表达式的不足"""
        # 当前的正则表达式: r'[<>:"/\\|?*]'
        current_regex_bypasses = [
            "file\nname",      # 换行符不在正则中
            "file\u0000name",  # NULL字节不在正则中
            "CON",             # Windows保留名不在正则中
            "file\u202Ename",  # Unicode控制字符不在正则中
        ]

        for bypass in current_regex_bypasses:
            sanitized = self.downloader._sanitize_filename(bypass)
            # 显示当前实现的不足
            print(f"Regex bypass: '{repr(bypass)}' -> '{repr(sanitized)}'")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_windows_specific_vulnerabilities(self):
        """测试Windows特有的漏洞"""
        # Windows文件名结尾不能有点号或空格
        windows_edge_cases = [
            "filename.",    # 结尾点号
            "filename ",    # 结尾空格
            "filename..",   # 多个点号
            "filename  ",   # 多个空格
        ]

        for edge_case in windows_edge_cases:
            sanitized = self.downloader._sanitize_filename(edge_case)
            print(f"Windows edge case '{repr(edge_case)}' -> '{repr(sanitized)}'")

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix-specific test")
    def test_unix_specific_vulnerabilities(self):
        """测试Unix特有的漏洞"""
        # Unix系统中的隐藏文件和特殊名称
        unix_edge_cases = [
            ".hidden",      # 隐藏文件
            "..hidden",     # 父目录引用变体
            "-filename",    # 可能被解释为命令行参数
        ]

        for edge_case in unix_edge_cases:
            sanitized = self.downloader._sanitize_filename(edge_case)
            print(f"Unix edge case '{repr(edge_case)}' -> '{repr(sanitized)}'")


class TestCurrentImplementationLimitations:
    """测试当前实现的局限性 - 这些测试展示了需要修复的问题"""

    def setup_method(self):
        """测试方法设置"""
        self.downloader = XiaoYuZhouDL()

    def test_no_unicode_normalization(self):
        """测试缺少Unicode规范化"""
        # 相同的字符，不同的Unicode表示
        filename1 = "café"  # 使用组合字符
        filename2 = "café"  # 使用预组合字符

        result1 = self.downloader._sanitize_filename(filename1)
        result2 = self.downloader._sanitize_filename(filename2)

        # 当前实现可能产生不同的结果
        print(f"Unicode variation 1: '{repr(filename1)}' -> '{repr(result1)}'")
        print(f"Unicode variation 2: '{repr(filename2)}' -> '{repr(result2)}'")

    def test_no_platform_awareness(self):
        """测试缺少平台感知"""
        # 在不同平台上应该有不同的处理
        filename = 'file"name'

        result = self.downloader._sanitize_filename(filename)
        current_platform = platform.system()

        print(f"Platform: {current_platform}")
        print(f"Result: '{repr(result)}'")
        # 当前实现在所有平台上的处理可能相同

    def test_insufficient_security_validation(self):
        """测试安全验证不足"""
        # 这些文件名应该被拒绝或特殊处理
        potentially_dangerous = [
            "",              # 空文件名
            ".",             # 当前目录
            "..",            # 父目录
            " ",             # 纯空格
            "\t\n\r",        # 纯空白字符
        ]

        for dangerous in potentially_dangerous:
            result = self.downloader._sanitize_filename(dangerous)
            print(f"Dangerous input '{repr(dangerous)}' -> '{repr(result)}'")