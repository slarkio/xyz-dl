"""命令行界面模块

使用 Rich 库提供美化的命令行体验
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, List, Optional

from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from .async_adapter import smart_run
from .config import get_config
from .downloader import XiaoYuZhouDL
from .exceptions import XyzDlException
from .models import Config, DownloadProgress, DownloadRequest, DownloadResult


class RichProgressHandler:
    """Rich进度处理器"""

    def __init__(self, console: Console):
        self.console = console
        self.progress: Optional[Progress] = None
        self.task_id: Optional[TaskID] = None

    def start_progress(self, filename: str, total: int = 0) -> None:
        """开始进度显示"""
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )
        if self.progress is not None:
            self.progress.start()

        description = f"Downloading {filename}"
        if self.progress is not None:
            self.task_id = self.progress.add_task(description, total=total)

    def update_progress(self, progress_info: DownloadProgress) -> None:
        """更新进度"""
        if self.progress is not None and self.task_id is not None:
            self.progress.update(
                self.task_id,
                completed=progress_info.downloaded,
                total=progress_info.total,
            )

    def stop_progress(self) -> None:
        """停止进度显示"""
        if self.progress is not None:
            self.progress.stop()
            self.progress = None
            self.task_id = None


class CLIApplication:
    """命令行应用程序"""

    def __init__(self) -> None:
        self.console = Console()
        self.progress_handler = RichProgressHandler(self.console)

    def create_parser(self) -> argparse.ArgumentParser:
        """创建命令行参数解析器"""
        parser = argparse.ArgumentParser(
            prog="xyz-dl",
            description="小宇宙播客音频下载器",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
使用示例:
  xyz-dl https://www.xiaoyuzhoufm.com/episode/12345678
  xyz-dl -d ~/Downloads --mode both https://www.xiaoyuzhoufm.com/episode/12345678
  xyz-dl --mode audio https://www.xiaoyuzhoufm.com/episode/12345678
  xyz-dl --mode md https://www.xiaoyuzhoufm.com/episode/12345678
  xyz-dl 12345678  # 直接使用episode ID
  xyz-dl -u https://www.xiaoyuzhoufm.com/episode/12345678  # 只获取下载地址
  xyz-dl --url-only 12345678  # 只获取下载地址(使用episode ID)
  xyz-dl --timeout 60 https://www.xiaoyuzhoufm.com/episode/12345678  # 设置超时时间

更多信息请访问: https://github.com/slarkio/xyz-dl
            """,
        )

        parser.add_argument(
            "url", nargs="?", help="小宇宙播客episode页面URL或episode ID"
        )

        parser.add_argument(
            "-d", "--dir", default=".", help="下载目录 (默认: 当前目录)"
        )

        parser.add_argument(
            "--mode",
            choices=["audio", "md", "both"],
            default="both",
            help="下载模式: audio(仅音频), md(仅Show Notes), both(同时下载) (默认: both)",
        )

        parser.add_argument("-v", "--verbose", action="store_true", help="显示详细输出")
        parser.add_argument(
            "-u",
            "--url-only",
            action="store_true",
            help="只获取音频下载地址，不实际下载文件",
        )

        # 常用配置参数
        parser.add_argument("--timeout", type=int, help="请求超时时间(秒)，默认30")
        parser.add_argument("--max-retries", type=int, help="最大重试次数，默认3")
        parser.add_argument("--user-agent", help="用户代理字符串")

        parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")

        return parser

    def progress_callback(self, progress: DownloadProgress) -> None:
        """进度回调函数"""
        self.progress_handler.update_progress(progress)

    def print_banner(self) -> None:
        """打印应用横幅"""
        banner = Text("XYZ-DL", style="bold blue")
        banner.append(" - 小宇宙播客下载器 v2.0.0", style="dim")

        panel = Panel(
            banner, title="🎙️ Podcast Downloader", border_style="blue", padding=(1, 2)
        )

        self.console.print(panel)

    def print_episode_info(self, result: DownloadResult) -> None:
        """打印节目信息"""
        if not result.episode_info:
            return

        episode = result.episode_info

        # 创建信息表格
        table = Table(title="📻 节目信息", show_header=False, border_style="dim")
        table.add_column("属性", style="bold cyan", width=12)
        table.add_column("值", style="white")

        table.add_row("标题", episode.title)
        table.add_row("播客", episode.podcast.title)
        table.add_row("主播", episode.podcast.author)

        if episode.duration_minutes:
            table.add_row("时长", f"{episode.duration_minutes}分钟")

        if episode.formatted_pub_date != "未知":
            table.add_row("发布时间", episode.formatted_pub_date)

        if episode.eid:
            table.add_row("节目ID", episode.eid)

        self.console.print(table)
        self.console.print()

    def print_success_result(self, result: DownloadResult) -> None:
        """打印成功结果"""
        success_text = Text("✅ 下载完成!", style="bold green")
        self.console.print(Panel(success_text, border_style="green"))

        if result.audio_path:
            self.console.print(f"🎵 音频文件: [link]{result.audio_path}[/link]")

        if result.md_path:
            self.console.print(f"📝 Show Notes: [link]{result.md_path}[/link]")

    def print_url_only_result(self, result: DownloadResult) -> None:
        """打印URL获取结果"""
        if result.episode_info and result.episode_info.audio_url:
            url_text = Text("🔗 音频下载地址:", style="bold blue")
            self.console.print(Panel(url_text, border_style="blue"))

            # 突出显示URL，便于复制
            self.console.print(f"[yellow]{result.episode_info.audio_url}[/yellow]")
            self.console.print()
            self.console.print("[dim]提示: 可以复制上面的URL进行手动下载[/dim]")
        else:
            self.print_error("未能获取到音频下载地址")

    def print_error(self, error: str) -> None:
        """打印错误信息"""
        error_text = Text(f"❌ 错误: {error}", style="bold red")
        self.console.print(Panel(error_text, border_style="red"))

    async def run_download(self, args: argparse.Namespace) -> int:
        """执行下载任务"""
        try:
            # 创建下载请求
            request = DownloadRequest(
                url=args.url,
                download_dir=args.dir,
                mode=args.mode,
                url_only=args.url_only,
            )

            # 加载基础配置
            config = get_config()

            # 从命令行参数覆盖配置
            config_dict = config.model_dump()
            if args.timeout is not None:
                config_dict["timeout"] = args.timeout
            if args.max_retries is not None:
                config_dict["max_retries"] = args.max_retries
            if args.user_agent is not None:
                config_dict["user_agent"] = args.user_agent

            # 重新创建配置对象
            config = Config(**config_dict)
            async with XiaoYuZhouDL(
                config=config, progress_callback=self.progress_callback
            ) as downloader:

                # 显示开始信息
                self.console.print(f"🔍 正在解析: [link]{args.url}[/link]")

                # 执行下载
                result = await downloader.download(request)

                if result.success:
                    self.print_episode_info(result)
                    if args.url_only:
                        self.print_url_only_result(result)
                    else:
                        self.print_success_result(result)
                else:
                    self.print_error(result.error or "Unknown error")
                    return 1

        except XyzDlException as e:
            self.print_error(str(e))
            return 1
        except KeyboardInterrupt:
            self.console.print("\n🛑 用户取消下载")
            return 1
        except Exception as e:
            self.print_error(f"意外错误: {e}")
            return 1

        return 0

    async def main(self, argv: Optional[List[str]] = None) -> int:
        """主入口函数"""
        parser = self.create_parser()
        args = parser.parse_args(argv)

        # 显示横幅
        if not args.verbose:
            self.print_banner()

        # 验证URL参数
        if not args.url:
            parser.print_help()
            return 1

        # 执行下载
        return await self.run_download(args)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI入口点 - 智能同步包装器

    使用智能适配器自动处理事件循环嵌套问题
    支持在任何环境中调用，包括 Jupyter Notebook
    """
    app = CLIApplication()

    try:
        return smart_run(app.main(argv))
    except KeyboardInterrupt:
        print("\n🛑 程序被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        return 1


def async_main(argv: Optional[List[str]] = None) -> Any:
    """异步CLI入口点"""
    app = CLIApplication()
    return app.main(argv)


if __name__ == "__main__":
    sys.exit(main())
