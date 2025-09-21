"""进度管理器模块

负责下载进度的跟踪和显示，提供Rich进度条和回调支持。
从原有的进度显示逻辑中重构而来。
"""

import uuid
from typing import Any, Callable, Dict, Optional

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ..models import DownloadProgress


class ProgressManager:
    """进度管理器

    负责管理下载进度的显示和跟踪，包括:
    - Rich进度条创建和管理
    - 进度任务的创建和更新
    - 进度回调函数支持
    - 多任务进度跟踪
    """

    def __init__(
        self, progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ):
        """初始化进度管理器

        Args:
            progress_callback: 可选的进度回调函数
        """
        self.progress_callback = progress_callback
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._progress_display: Optional[Progress] = None

    def create_progress_bar(self) -> Progress:
        """创建Rich进度条

        Returns:
            配置好的Progress对象
        """
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            refresh_per_second=4,
        )

    def create_task(self, description: str, total: int = 100) -> str:
        """创建进度跟踪任务

        Args:
            description: 任务描述
            total: 任务总量

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {
            "description": description,
            "total": total,
            "completed": 0,
            "created": True,
        }
        return task_id

    def update_progress(self, task_id: str, completed: int) -> None:
        """更新任务进度

        Args:
            task_id: 任务ID
            completed: 已完成数量
        """
        if task_id not in self._tasks:
            return

        task = self._tasks[task_id]
        task["completed"] = completed

        # 如果有进度回调，调用它
        if self.progress_callback:
            progress_info = DownloadProgress(
                filename=task["description"],
                downloaded=completed,
                total=task["total"],
            )
            self.progress_callback(progress_info)

    def get_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务进度信息

        Args:
            task_id: 任务ID

        Returns:
            进度信息字典，如果任务不存在返回None
        """
        return self._tasks.get(task_id)

    def complete_task(self, task_id: str) -> None:
        """完成任务

        Args:
            task_id: 任务ID
        """
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task["completed"] = task["total"]
            task["finished"] = True

    def remove_task(self, task_id: str) -> None:
        """移除任务

        Args:
            task_id: 任务ID
        """
        self._tasks.pop(task_id, None)

    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务

        Returns:
            所有任务的字典
        """
        return self._tasks.copy()

    def clear_all_tasks(self) -> None:
        """清除所有任务"""
        self._tasks.clear()

    class RichProgressContext:
        """Rich进度条上下文管理器"""

        def __init__(self, manager: "ProgressManager", description: str, total: int):
            self.manager = manager
            self.description = description
            self.total = total
            self.progress: Optional[Progress] = None
            self.task_id: Optional[Any] = None

        def __enter__(self):
            self.progress = self.manager.create_progress_bar()
            self.progress.__enter__()
            self.task_id = self.progress.add_task(self.description, total=self.total)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.progress:
                self.progress.__exit__(exc_type, exc_val, exc_tb)

        def update(self, completed: int) -> None:
            """更新进度

            Args:
                completed: 已完成数量
            """
            if self.progress and self.task_id is not None:
                self.progress.update(self.task_id, completed=completed)

            # 同时调用进度回调
            if self.manager.progress_callback:
                progress_info = DownloadProgress(
                    filename=self.description,
                    downloaded=completed,
                    total=self.total,
                )
                self.manager.progress_callback(progress_info)

    def create_rich_progress_context(
        self, description: str, total: int
    ) -> RichProgressContext:
        """创建Rich进度条上下文管理器

        Args:
            description: 任务描述
            total: 任务总量

        Returns:
            进度条上下文管理器
        """
        return self.RichProgressContext(self, description, total)


class SimpleProgressManager:
    """简单进度管理器

    用于不需要Rich进度条的场景，只提供基本的进度跟踪功能。
    """

    def __init__(
        self, progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ):
        """初始化简单进度管理器

        Args:
            progress_callback: 可选的进度回调函数
        """
        self.progress_callback = progress_callback

    def track_progress(self, filename: str, downloaded: int, total: int) -> None:
        """跟踪进度

        Args:
            filename: 文件名
            downloaded: 已下载字节数
            total: 总字节数
        """
        if self.progress_callback:
            progress_info = DownloadProgress(
                filename=filename,
                downloaded=downloaded,
                total=total,
            )
            self.progress_callback(progress_info)

    def create_progress_tracker(self, filename: str, total: int):
        """创建进度跟踪器

        Args:
            filename: 文件名
            total: 总字节数

        Returns:
            进度跟踪函数
        """

        def track(downloaded: int):
            self.track_progress(filename, downloaded, total)

        return track
