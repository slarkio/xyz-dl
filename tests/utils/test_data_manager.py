"""测试数据管理器

负责获取、保存和管理HTML测试数据
"""

import asyncio
import os
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import aiohttp
import aiofiles


class TestDataManager:
    """测试数据管理器"""

    def __init__(self, fixtures_dir: str = None):
        """初始化测试数据管理器

        Args:
            fixtures_dir: 测试fixtures目录路径，默认为 tests/fixtures
        """
        if fixtures_dir is None:
            # 获取当前文件的父目录的父目录，即tests目录
            tests_dir = Path(__file__).parent.parent
            fixtures_dir = tests_dir / "fixtures"

        self.fixtures_dir = Path(fixtures_dir)
        self.fixtures_dir.mkdir(exist_ok=True, parents=True)

    async def fetch_and_save_html(self, url: str, filename: str = None) -> str:
        """获取URL的HTML内容并保存到本地文件

        Args:
            url: 要获取的URL
            filename: 保存的文件名，默认基于URL的episode ID生成

        Returns:
            保存的文件路径

        Raises:
            aiohttp.ClientError: 网络请求失败
            IOError: 文件操作失败
        """
        if filename is None:
            # 从URL提取episode ID作为文件名
            try:
                episode_id = url.split("/episode/")[-1].split("?")[0][:12]  # 限制长度
                filename = f"episode_{episode_id}.html"
            except Exception:
                # 使用URL hash作为后备方案
                filename = f"episode_{hash(url) % 1000000:06d}.html"

        file_path = self.fixtures_dir / filename

        # 如果文件已存在，直接返回路径
        if file_path.exists():
            print(f"HTML文件已存在: {file_path}")
            return str(file_path)

        # 获取HTML内容
        async with aiohttp.ClientSession() as session:
            print(f"正在获取HTML内容: {url}")
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(
                        f"HTTP {response.status}: {response.reason}"
                    )
                html_content = await response.text()

        # 保存到文件
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(html_content)

        print(f"HTML内容已保存: {file_path}")
        return str(file_path)

    async def load_html(self, filename: str) -> str:
        """从本地文件加载HTML内容

        Args:
            filename: 文件名

        Returns:
            HTML内容

        Raises:
            FileNotFoundError: 文件不存在
        """
        file_path = self.fixtures_dir / filename

        if not file_path.exists():
            raise FileNotFoundError(f"测试数据文件不存在: {file_path}")

        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            return await f.read()

    async def setup_test_data(self, urls: List[str]) -> Dict[str, str]:
        """设置测试数据，获取所有URL的HTML内容

        Args:
            urls: URL列表

        Returns:
            URL到文件路径的映射
        """
        url_to_file = {}
        tasks = []

        for url in urls:
            task = self.fetch_and_save_html(url)
            tasks.append((url, task))

        # 并发获取所有HTML内容
        for url, task in tasks:
            try:
                file_path = await task
                url_to_file[url] = file_path
                print(f"✅ {url} -> {file_path}")
            except Exception as e:
                print(f"❌ {url}: {e}")
                raise

        return url_to_file

    def get_fixture_path(self, filename: str) -> str:
        """获取fixture文件的完整路径

        Args:
            filename: 文件名

        Returns:
            完整文件路径
        """
        return str(self.fixtures_dir / filename)

    def list_fixtures(self) -> List[str]:
        """列出所有可用的fixture文件

        Returns:
            文件名列表
        """
        if not self.fixtures_dir.exists():
            return []

        return [
            f.name
            for f in self.fixtures_dir.iterdir()
            if f.is_file() and f.suffix == ".html"
        ]

    async def cleanup_fixtures(self) -> None:
        """清理所有fixture文件"""
        if self.fixtures_dir.exists():
            for file_path in self.fixtures_dir.glob("*.html"):
                file_path.unlink()
            print(f"已清理fixtures目录: {self.fixtures_dir}")


# 默认测试URL列表
DEFAULT_TEST_URLS = [
    "https://www.xiaoyuzhoufm.com/episode/68916f6b8e06fe8de75c9099",
    "https://www.xiaoyuzhoufm.com/episode/669f1f9f8fcadceb903e3f52",
    "https://www.xiaoyuzhoufm.com/episode/655b4216c9e7cfe025dd5a86",
]


async def setup_default_test_data() -> TestDataManager:
    """设置默认的测试数据

    Returns:
        配置好的TestDataManager实例
    """
    manager = TestDataManager()
    await manager.setup_test_data(DEFAULT_TEST_URLS)
    return manager


if __name__ == "__main__":
    # 直接运行此脚本来设置测试数据
    async def main():
        manager = await setup_default_test_data()
        fixtures = manager.list_fixtures()
        print(f"\n可用的测试数据文件:")
        for fixture in fixtures:
            print(f"  - {fixture}")

    asyncio.run(main())
