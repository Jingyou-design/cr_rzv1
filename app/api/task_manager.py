"""内存任务管理器，跟踪后台任务状态"""

import threading
from datetime import datetime

from app.api.schemas import TaskStatus


class TaskInfo:
    def __init__(self, task_id: str, filename: str):
        self.task_id = task_id
        self.filename = filename
        self.status = TaskStatus.PENDING
        self.stage = "queued"
        self.error: str | None = None
        self.output_zip: str | None = None
        self.created_at = datetime.now()


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}
        self._lock = threading.Lock()

    def create(self, task_id: str, filename: str) -> TaskInfo:
        with self._lock:
            task = TaskInfo(task_id, filename)
            self._tasks[task_id] = task
            return task

    def get(self, task_id: str) -> TaskInfo | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
        output_zip: str | None = None,
        stage: str | None = None,
    ):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                if stage is not None:
                    task.stage = stage
                if error is not None:
                    task.error = error
                if output_zip is not None:
                    task.output_zip = output_zip


task_manager = TaskManager()
