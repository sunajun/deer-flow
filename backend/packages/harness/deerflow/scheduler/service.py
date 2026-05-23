from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from croniter import croniter

from deerflow.scheduler.models import ScheduledTask, ScheduleRun, ScheduleStatus

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.runs: list[ScheduleRun] = []
        self._running = False
        self._tick_interval = 60

    async def start(self) -> None:
        self._running = True
        logger.info("SchedulerService started")
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self._tick_interval)

    async def stop(self) -> None:
        self._running = False
        logger.info("SchedulerService stopped")

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        for task in list(self.tasks.values()):
            if task.status != ScheduleStatus.ACTIVE:
                continue
            if self._should_trigger(task, now):
                await self._execute(task)

    def _should_trigger(self, task: ScheduledTask, now: datetime) -> bool:
        if task.trigger.cron:
            try:
                tz = self._resolve_timezone(task.trigger.timezone)
                local_now = now.astimezone(tz)
                if not croniter.match(task.trigger.cron, local_now):
                    return False
                if task.last_fired_cron_time is not None:
                    last_local = task.last_fired_cron_time.astimezone(tz)
                    if (local_now.year == last_local.year
                            and local_now.month == last_local.month
                            and local_now.day == last_local.day
                            and local_now.hour == last_local.hour
                            and local_now.minute == last_local.minute):
                        return False
                return True
            except (ValueError, KeyError) as e:
                logger.warning("Invalid cron expression '%s': %s", task.trigger.cron, e)
                return False
        elif task.trigger.interval_seconds:
            if task.last_run_at is None:
                return True
            elapsed = (now - task.last_run_at).total_seconds()
            return elapsed >= task.trigger.interval_seconds
        return False

    @staticmethod
    def _resolve_timezone(tz_name: str):
        from zoneinfo import ZoneInfo
        try:
            return ZoneInfo(tz_name)
        except (KeyError, Exception):
            logger.warning("Unknown timezone %s, falling back to UTC", tz_name)
            return UTC

    async def _execute(self, task: ScheduledTask) -> None:
        now = datetime.now(UTC)
        task.last_run_at = now
        task.run_count += 1
        if task.trigger.cron:
            task.last_fired_cron_time = now
        task.updated_at = now
        logger.info("Executing scheduled task %s (run #%d)", task.task_id, task.run_count)

    async def create_task(self, task: ScheduledTask) -> ScheduledTask:
        self.tasks[task.task_id] = task
        logger.info("Created scheduled task %s", task.task_id)
        return task

    async def update_task(self, task_id: str, updates: dict) -> ScheduledTask:
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        task = self.tasks[task_id]
        update_data = task.model_dump()
        update_data.update(updates)
        update_data["updated_at"] = datetime.now(UTC).isoformat()
        self.tasks[task_id] = ScheduledTask.model_validate(update_data)
        return self.tasks[task_id]

    async def delete_task(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)

    async def pause_task(self, task_id: str) -> None:
        await self.update_task(task_id, {"status": ScheduleStatus.PAUSED.value})

    async def resume_task(self, task_id: str) -> None:
        await self.update_task(task_id, {"status": ScheduleStatus.ACTIVE.value})

    async def list_tasks(self) -> list[ScheduledTask]:
        return list(self.tasks.values())

    async def get_runs(self, task_id: str) -> list[ScheduleRun]:
        return [r for r in self.runs if r.task_id == task_id]
