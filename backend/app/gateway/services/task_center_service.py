from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime
from uuid import uuid4

from app.gateway.models.task_center import TaskRecord, TaskStatus

logger = logging.getLogger(__name__)

_MAX_TASKS = 10000
_MAX_LOGS_PER_TASK = 1000


class TaskCenterService:
    def __init__(self, max_tasks: int = _MAX_TASKS, max_logs_per_task: int = _MAX_LOGS_PER_TASK) -> None:
        self._tasks: OrderedDict[str, dict] = OrderedDict()
        self._logs: dict[str, list[str]] = {}
        self._max_tasks = max_tasks
        self._max_logs_per_task = max_logs_per_task

    def _evict_if_needed(self) -> None:
        while len(self._tasks) > self._max_tasks:
            evicted_id, _ = self._tasks.popitem(last=False)
            self._logs.pop(evicted_id, None)
            logger.debug("Evicted task %s (LRU limit: %d)", evicted_id, self._max_tasks)

    async def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        task_type: str | None = None,
    ) -> list[TaskRecord]:
        tasks = [TaskRecord.from_storage_dict(t) for t in self._tasks.values()]
        if status_filter:
            tasks = [t for t in tasks if t.status.value == status_filter]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        start = (page - 1) * page_size
        return tasks[start : start + page_size]

    async def get_task_detail(self, task_id: str) -> TaskRecord | None:
        data = self._tasks.get(task_id)
        if data is None:
            return None
        return TaskRecord.from_storage_dict(data)

    async def get_task_logs(self, task_id: str) -> list[str]:
        return self._logs.get(task_id, [])

    async def create_task(self, task: TaskRecord) -> TaskRecord:
        self._tasks[task.task_id] = task.to_storage_dict()
        self._tasks.move_to_end(task.task_id)
        self._evict_if_needed()
        logger.info("Created task %s (%s)", task.task_id, task.task_type)
        return task

    async def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> TaskRecord | None:
        data = self._tasks.get(task_id)
        if data is None:
            return None
        data["status"] = status.value
        for key, value in kwargs.items():
            if key in data:
                data[key] = value
        self._tasks.move_to_end(task_id)
        return TaskRecord.from_storage_dict(data)

    async def retry_task(self, task_id: str) -> TaskRecord:
        data = self._tasks.get(task_id)
        if data is None:
            raise ValueError(f"Task {task_id} not found")
        task = TaskRecord.from_storage_dict(data)
        if task.status != TaskStatus.FAILED:
            raise ValueError("只能重试失败任务")
        data["status"] = TaskStatus.PENDING.value
        data["error"] = None
        data["started_at"] = None
        data["finished_at"] = None
        self._tasks.move_to_end(task_id)
        return TaskRecord.from_storage_dict(data)

    async def rerun_task(self, task_id: str, use_new_thread: bool = False) -> TaskRecord:
        data = self._tasks.get(task_id)
        if data is None:
            raise ValueError(f"Task {task_id} not found")
        old = TaskRecord.from_storage_dict(data)
        new_task = TaskRecord(
            task_id=f"task_{uuid4().hex[:8]}",
            thread_id="" if use_new_thread else old.thread_id,
            task_type=old.task_type,
            name=old.name,
            description=old.description,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            parent_task_id=old.task_id,
        )
        self._tasks[new_task.task_id] = new_task.to_storage_dict()
        self._evict_if_needed()
        return new_task

    async def cancel_task(self, task_id: str) -> TaskRecord:
        data = self._tasks.get(task_id)
        if data is None:
            raise ValueError(f"Task {task_id} not found")
        task = TaskRecord.from_storage_dict(data)
        if task.status not in (TaskStatus.RUNNING, TaskStatus.PENDING):
            raise ValueError("只能取消运行中或等待中的任务")
        data["status"] = TaskStatus.CANCELLED.value
        data["finished_at"] = datetime.now().isoformat()
        return TaskRecord.from_storage_dict(data)

    async def export_task_audit(self, task_id: str) -> str:
        data = self._tasks.get(task_id)
        if data is None:
            raise ValueError(f"Task {task_id} not found")
        logs = self._logs.get(task_id, [])
        report = {
            "task_id": data["task_id"],
            "name": data["name"],
            "status": data["status"],
            "timeline": {
                "created": data.get("created_at"),
                "started": data.get("started_at"),
                "finished": data.get("finished_at"),
                "duration_seconds": data.get("duration"),
            },
            "result": data.get("result"),
            "error": data.get("error"),
            "logs": logs,
            "parent_task_id": data.get("parent_task_id"),
        }
        return json.dumps(report, indent=2, ensure_ascii=False)

    async def append_log(self, task_id: str, log_entry: str) -> None:
        if task_id not in self._logs:
            self._logs[task_id] = []
        logs = self._logs[task_id]
        logs.append(f"[{datetime.now().isoformat()}] {log_entry}")
        if len(logs) > self._max_logs_per_task:
            self._logs[task_id] = logs[-self._max_logs_per_task :]


_task_center_service: TaskCenterService | None = None


def get_task_center_service() -> TaskCenterService:
    global _task_center_service
    if _task_center_service is None:
        _task_center_service = TaskCenterService()
    return _task_center_service


def reset_task_center_service() -> None:
    global _task_center_service
    _task_center_service = None
