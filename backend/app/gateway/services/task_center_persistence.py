from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.gateway.models.task_center import TaskRecord, TaskStatus
from app.gateway.models.task_center_db import TaskLogRow, TaskRow
from deerflow.persistence.engine import get_session_factory

logger = logging.getLogger(__name__)


class TaskCenterPersistence:

    async def save_task(self, task: TaskRecord) -> None:
        sf = get_session_factory()
        if sf is None:
            return
        async with sf() as session:
            data = task.to_storage_dict()
            row = TaskRow(
                task_id=data["task_id"],
                thread_id=data["thread_id"],
                task_type=data["task_type"],
                name=data["name"],
                description=data.get("description", ""),
                status=data["status"],
                created_at=data.get("created_at"),
                started_at=data.get("started_at"),
                finished_at=data.get("finished_at"),
                duration=data.get("duration"),
                result=json.dumps(data["result"], ensure_ascii=False) if data.get("result") else None,
                error=data.get("error"),
                created_by=data.get("created_by", "default"),
                parent_task_id=data.get("parent_task_id"),
            )
            await session.merge(row)
            await session.commit()

    async def load_task(self, task_id: str) -> TaskRecord | None:
        sf = get_session_factory()
        if sf is None:
            return None
        async with sf() as session:
            row = await session.get(TaskRow, task_id)
            if row is None:
                return None
            return self._row_to_record(row)

    async def load_all_tasks(self) -> list[TaskRecord]:
        sf = get_session_factory()
        if sf is None:
            return []
        async with sf() as session:
            stmt = select(TaskRow).order_by(TaskRow.created_at.desc())
            result = await session.execute(stmt)
            return [self._row_to_record(row) for row in result.scalars()]

    async def delete_task(self, task_id: str) -> None:
        sf = get_session_factory()
        if sf is None:
            return
        async with sf() as session:
            row = await session.get(TaskRow, task_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def save_log(self, task_id: str, entry: str) -> None:
        sf = get_session_factory()
        if sf is None:
            return
        async with sf() as session:
            log_row = TaskLogRow(task_id=task_id, entry=entry)
            session.add(log_row)
            await session.commit()

    async def load_logs(self, task_id: str) -> list[str]:
        sf = get_session_factory()
        if sf is None:
            return []
        async with sf() as session:
            stmt = select(TaskLogRow).where(TaskLogRow.task_id == task_id).order_by(TaskLogRow.created_at)
            result = await session.execute(stmt)
            return [row.entry for row in result.scalars()]

    @staticmethod
    def _row_to_record(row: TaskRow) -> TaskRecord:
        result_data = json.loads(row.result) if row.result else None
        return TaskRecord(
            task_id=row.task_id,
            thread_id=row.thread_id,
            task_type=row.task_type,
            name=row.name,
            description=row.description,
            status=TaskStatus(row.status),
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            duration=row.duration,
            result=result_data,
            error=row.error,
            created_by=row.created_by,
            parent_task_id=row.parent_task_id,
        )
