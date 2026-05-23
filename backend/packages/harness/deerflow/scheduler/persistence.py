from __future__ import annotations

import logging

from sqlalchemy import select

from deerflow.persistence.engine import get_session_factory
from deerflow.scheduler.db_models import ScheduleRunRow, ScheduledTaskRow
from deerflow.scheduler.models import ScheduleNotification, ScheduleRun, ScheduleTrigger, ScheduledTask

logger = logging.getLogger(__name__)


class SchedulePersistence:
    """定时任务持久化层，使用现有 SQLAlchemy session factory。"""

    async def save_task(self, task: ScheduledTask) -> None:
        sf = get_session_factory()
        if sf is None:
            return
        async with sf() as session:
            row = ScheduledTaskRow(
                task_id=task.task_id,
                name=task.name,
                description=task.description,
                prompt=task.prompt,
                trigger_config=task.trigger.model_dump_json(),
                notification_config=task.notification.model_dump_json(),
                use_orchestration=task.use_orchestration,
                reuse_thread=task.reuse_thread,
                thread_id=task.thread_id,
                timeout_seconds=task.timeout_seconds,
                status=task.status.value,
                last_run_at=task.last_run_at,
                next_run_at=task.next_run_at,
                run_count=task.run_count,
                last_fired_cron_time=task.last_fired_cron_time,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            await session.merge(row)
            await session.commit()

    async def load_task(self, task_id: str) -> ScheduledTask | None:
        sf = get_session_factory()
        if sf is None:
            return None
        async with sf() as session:
            row = await session.get(ScheduledTaskRow, task_id)
            if row is None:
                return None
            return self._row_to_task(row)

    async def load_all_tasks(self) -> list[ScheduledTask]:
        sf = get_session_factory()
        if sf is None:
            return []
        async with sf() as session:
            stmt = select(ScheduledTaskRow)
            result = await session.execute(stmt)
            return [self._row_to_task(row) for row in result.scalars()]

    async def delete_task(self, task_id: str) -> None:
        sf = get_session_factory()
        if sf is None:
            return
        async with sf() as session:
            row = await session.get(ScheduledTaskRow, task_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def save_run(self, run: ScheduleRun) -> None:
        sf = get_session_factory()
        if sf is None:
            return
        async with sf() as session:
            row = ScheduleRunRow(
                run_id=run.run_id,
                task_id=run.task_id,
                thread_id=run.thread_id,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                result_summary=run.result_summary,
                error=run.error,
            )
            await session.merge(row)
            await session.commit()

    async def load_runs(self, task_id: str) -> list[ScheduleRun]:
        sf = get_session_factory()
        if sf is None:
            return []
        async with sf() as session:
            stmt = select(ScheduleRunRow).where(ScheduleRunRow.task_id == task_id).order_by(ScheduleRunRow.started_at)
            result = await session.execute(stmt)
            return [self._row_to_run(row) for row in result.scalars()]

    @staticmethod
    def _row_to_task(row: ScheduledTaskRow) -> ScheduledTask:
        trigger = ScheduleTrigger.model_validate_json(row.trigger_config)
        notification = ScheduleNotification.model_validate_json(row.notification_config)
        return ScheduledTask(
            task_id=row.task_id,
            name=row.name,
            description=row.description,
            prompt=row.prompt,
            trigger=trigger,
            notification=notification,
            use_orchestration=row.use_orchestration,
            reuse_thread=row.reuse_thread,
            thread_id=row.thread_id,
            timeout_seconds=row.timeout_seconds,
            status=row.status,
            last_run_at=row.last_run_at,
            next_run_at=row.next_run_at,
            run_count=row.run_count,
            last_fired_cron_time=row.last_fired_cron_time,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _row_to_run(row: ScheduleRunRow) -> ScheduleRun:
        return ScheduleRun(
            run_id=row.run_id,
            task_id=row.task_id,
            thread_id=row.thread_id,
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            result_summary=row.result_summary,
            error=row.error,
        )
