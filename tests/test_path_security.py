"""路径遍历安全测试模块

测试路径遍历漏洞的修复情况，确保用户无法通过恶意路径访问系统敏感文件
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from xyz_dl.downloader import XiaoYuZhouDL
from xyz_dl.exceptions import PathSecurityError


class TestPathTraversalSecurity:
    """路径遍历安全测试类"""

    def setup_method(self):
        """设置测试环境"""
        self.downloader = XiaoYuZhouDL()
        self.temp_dir = tempfile.mkdtemp()
        self.safe_download_dir = str(Path(self.temp_dir) / "safe_downloads")

    def teardown_method(self):
        """清理测试环境"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_path_traversal_parent_directory_attack(self):
        """测试父目录遍历攻击 - 应该被阻止"""
        malicious_path = "../../../etc/passwd"

        with pytest.raises(PathSecurityError) as exc_info:
            await self.downloader._download_audio(
                "http://example.com/audio.mp3", "test_file", malicious_path
            )

        assert "Path traversal" in str(exc_info.value) or "attack detected" in str(
            exc_info.value
        )

    def test_path_traversal_absolute_system_path_attack(self):
        """测试绝对系统路径攻击 - 应该被阻止"""
        unix_system_paths = [
            "/etc",
            "/var/log",
        ]

        for malicious_path in unix_system_paths:
            with pytest.raises(PathSecurityError) as exc_info:
                self.downloader._validate_download_path(malicious_path)

            error_msg = str(exc_info.value).lower()
            assert any(
                keyword in error_msg
                for keyword in [
                    "path traversal",
                    "system directories",
                    "unsafe area",
                    "attack detected",
                    "unsafe_area_access",
                ]
            )

    @pytest.mark.asyncio
    async def test_path_traversal_show_notes_attack(self):
        """测试Show Notes下载路径遍历攻击 - 应该被阻止"""
        malicious_path = "../../../home/user/.ssh"

        with pytest.raises(PathSecurityError):
            # 创建一个模拟的EpisodeInfo
            from xyz_dl.models import EpisodeInfo, PodcastInfo

            mock_episode = EpisodeInfo(
                title="Test Episode",
                podcast=PodcastInfo(title="Test Podcast", author="Test Author"),
                shownotes="Test Notes",
                audio_url="http://example.com/audio.mp3",
            )
            await self.downloader._generate_markdown(
                mock_episode, "test_file", malicious_path
            )

    def test_symlink_attack_prevention(self):
        """测试符号链接攻击防护"""
        # 创建指向系统目录的符号链接
        symlink_path = Path(self.temp_dir) / "malicious_symlink"
        if os.name != "nt":  # Unix系统支持符号链接
            try:
                symlink_path.symlink_to("/etc")

                with pytest.raises(PathSecurityError) as exc_info:
                    self.downloader._validate_download_path(str(symlink_path))

                error_msg = str(exc_info.value).lower()
                assert any(
                    keyword in error_msg
                    for keyword in [
                        "symlink",
                        "system directories",
                        "unsafe area",
                        "attack detected",
                        "unsafe_area_access",
                    ]
                )
            except OSError:
                pytest.skip("Cannot create symlink in test environment")

    def test_unicode_path_traversal_attack(self):
        """测试Unicode路径遍历攻击"""
        unicode_attacks = [
            "..%2F..%2F..%2Fetc%2Fpasswd",  # URL编码
            "..\\..\\..\\windows\\system32",  # Windows路径
            "..／..／..／etc／passwd",  # 全角斜杠
        ]

        for attack_path in unicode_attacks:
            with pytest.raises(PathSecurityError):
                self.downloader._validate_download_path(attack_path)

    def test_path_length_limit_exceeded(self):
        """测试路径长度限制 - Windows 260字符限制"""
        long_path = "A" * 300  # 超过Windows路径长度限制

        with pytest.raises(PathSecurityError) as exc_info:
            self.downloader._validate_download_path(long_path)

        assert "path too long" in str(exc_info.value).lower()

    def test_valid_safe_path_allowed(self):
        """测试合法安全路径应该被允许"""
        # 使用当前工作目录下的相对路径，这应该是安全的
        safe_relative_path = "downloads"

        try:
            # 简化测试，只验证路径验证通过即可
            validated_path = self.downloader._validate_download_path(safe_relative_path)

            # 应该成功返回有效路径
            assert validated_path
            assert str(validated_path).endswith("downloads")

        except PathSecurityError:
            pytest.fail("Valid safe path should be allowed")

    def test_validate_download_path_function_exists(self):
        """测试_validate_download_path函数是否存在"""
        # 这个测试会失败，直到我们实现该函数
        assert hasattr(
            self.downloader, "_validate_download_path"
        ), "_validate_download_path method must be implemented"

    @pytest.mark.parametrize(
        "attack_path",
        [
            "../etc/passwd",
            "../../windows/system32",
            "/etc/shadow",
            "..\\..\\..\\sensitive_file",
            "~/../../etc/passwd",
        ],
    )
    def test_various_path_traversal_attacks(self, attack_path):
        """参数化测试各种路径遍历攻击向量"""
        # 直接测试验证函数（一旦实现）
        with pytest.raises(PathSecurityError):
            # 这个调用会失败，直到我们实现_validate_download_path
            self.downloader._validate_download_path(attack_path)

    def test_windows_absolute_path_attack(self):
        """测试Windows绝对路径攻击 - 仅在Windows上或在Unix上作为相对路径"""
        import os

        windows_path = "C:\\Windows\\System32"

        if os.name == "nt":
            # 在Windows上应该被检测为系统目录攻击
            with pytest.raises(PathSecurityError):
                self.downloader._validate_download_path(windows_path)
        else:
            # 在Unix系统上，这会被当作相对路径，应该创建在当前目录下
            # 但如果我们识别出它是Windows路径模式，也应该阻止
            try:
                result = self.downloader._validate_download_path(windows_path)
                # 如果允许通过，至少确保它不是指向系统目录
                assert not str(result).lower().startswith("/c/windows")
            except PathSecurityError:
                # 如果被阻止也是可以接受的
                pass

    def test_ensure_safe_filename_path_traversal(self):
        """测试_ensure_safe_filename方法防止路径遍历"""
        downloader = XiaoYuZhouDL()

        # 测试各种路径遍历攻击
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "/etc/passwd",
            "C:\\Windows\\System32\\config",
            "file/with/slashes.txt",
            "file\\with\\backslashes.txt",
            "file:with:colons.txt",
            "file*with*wildcards.txt",
            "file?with?questions.txt",
            "file<with>brackets.txt",
            "file|with|pipes.txt",
        ]

        for malicious_filename in malicious_filenames:
            with pytest.raises(PathSecurityError) as exc_info:
                downloader._ensure_safe_filename(malicious_filename)
            assert "path_traversal" in str(exc_info.value) or "invalid_filename" in str(exc_info.value)

    def test_ensure_safe_filename_valid_cases(self):
        """测试_ensure_safe_filename方法的有效情况"""
        downloader = XiaoYuZhouDL()

        valid_filenames = [
            "normal_file.txt",
            "中文文件名.mp3",
            "file-with-dashes.md",
            "file_with_underscores.wav",
            "file123.m4a",
            "UPPERCASE.MP3",
        ]

        for valid_filename in valid_filenames:
            result = downloader._ensure_safe_filename(valid_filename)
            assert result == valid_filename
            assert ".." not in result
            assert "/" not in result
            assert "\\" not in result

    def test_ensure_safe_filename_empty_cases(self):
        """测试_ensure_safe_filename方法的空值情况"""
        downloader = XiaoYuZhouDL()

        empty_cases = ["", ".", "   "]

        for empty_case in empty_cases:
            with pytest.raises(PathSecurityError) as exc_info:
                downloader._ensure_safe_filename(empty_case)
            assert "invalid_filename" in str(exc_info.value)

        # 单独测试包含..的情况，这些会被归类为路径遍历
        traversal_cases = ["..", "..."]
        for traversal_case in traversal_cases:
            with pytest.raises(PathSecurityError) as exc_info:
                downloader._ensure_safe_filename(traversal_case)
            assert "path_traversal" in str(exc_info.value)

    def test_filename_length_truncation(self):
        """测试文件名长度截断"""
        downloader = XiaoYuZhouDL()

        # 创建超长文件名
        long_filename = "a" * 300 + ".txt"
        result = downloader._ensure_safe_filename(long_filename)

        # 应该被截断到255字符
        assert len(result) <= 255
        assert result.endswith(".txt")

    @pytest.mark.asyncio
    async def test_path_validation_in_audio_download(self):
        """测试音频下载中的路径验证"""
        downloader = XiaoYuZhouDL()

        # 创建包含路径遍历的恶意文件名
        malicious_filename = "../../../malicious"

        with pytest.raises(PathSecurityError):
            await downloader._prepare_download_file_path(
                "https://example.com/audio.mp3",
                malicious_filename,
                "/tmp/downloads"
            )

    @pytest.mark.asyncio
    async def test_path_validation_in_markdown_generation(self):
        """测试Markdown生成中的路径验证"""
        from xyz_dl.models import EpisodeInfo, PodcastInfo

        downloader = XiaoYuZhouDL()

        # 创建模拟的episode信息
        mock_episode = EpisodeInfo(
            title="Test Episode",
            podcast=PodcastInfo(title="Test Podcast", author="Test Author"),
            shownotes="Test Notes",
            audio_url="http://example.com/audio.mp3",
        )

        # 测试恶意文件名
        malicious_filename = "../../../malicious"

        with pytest.raises(PathSecurityError):
            await downloader._generate_markdown(
                mock_episode, malicious_filename, "/tmp/downloads"
            )
