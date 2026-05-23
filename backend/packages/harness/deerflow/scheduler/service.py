from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

import httpx
from croniter import croniter

from deerflow.scheduler.models import ScheduledTask, ScheduleRun, ScheduleStatus
from deerflow.scheduler.persistence import SchedulePersistence

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, persistence: SchedulePersistence | None = None) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.runs: list[ScheduleRun] = []
        self._running = False
        self._tick_interval = 60
        self.persistence = persistence

    async def start(self) -> None:
        if self.persistence:
            tasks = await self.persistence.load_all_tasks()
            self.tasks = {t.task_id: t for t in tasks}
            logger.info("Loaded %d scheduled tasks from database", len(tasks))
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
        run = ScheduleRun(
            run_id=f"run_{task.task_id}_{int(now.timestamp())}",
            task_id=task.task_id,
            thread_id="",
            status="running",
            started_at=now,
        )

        if task.reuse_thread and task.thread_id:
            run.thread_id = task.thread_id
        else:
            run.thread_id = await self._create_thread(task.prompt)

        await self._send_message(run.thread_id, task.prompt)

        task.last_run_at = now
        task.last_fired_cron_time = now
        task.run_count += 1
        task.updated_at = now
        self.runs.append(run)

        if self.persistence:
            await self.persistence.save_task(task)
            await self.persistence.save_run(run)

        asyncio.create_task(self._wait_and_notify(task, run))

    async def _create_thread(self, prompt: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/api/threads",
                json={},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("thread_id", "")

    async def _send_message(self, thread_id: str, prompt: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://localhost:8000/api/threads/{thread_id}/runs",
                json={"input": {"messages": [{"type": "human", "content": prompt}]}},
            )
            resp.raise_for_status()

    async def _wait_and_notify(self, task: ScheduledTask, run: ScheduleRun) -> None:
        timeout = task.timeout_seconds
        start = time.time()
        while time.time() - start < timeout:
            status = await self._check_thread_status(run.thread_id)
            if status in ("completed", "failed", "cancelled"):
                run.status = status
                run.completed_at = datetime.now(UTC)
                break
            await asyncio.sleep(10)
        else:
            run.status = "failed"
            run.error = "执行超时"

        if self.persistence:
            await self.persistence.save_run(run)

        if task.notification.enabled:
            await self._send_notification(task, run)

    async def _check_thread_status(self, thread_id: str) -> str:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"http://localhost:8000/api/threads/{thread_id}/runs",
                )
                resp.raise_for_status()
                runs = resp.json()
                if runs:
                    return runs[-1].get("status", "running")
            except Exception:
                pass
        return "running"

    async def _send_notification(self, task: ScheduledTask, run: ScheduleRun) -> None:
        from app.channels.message_bus import OutboundMessage
        from app.channels.service import get_channel_service

        channel_service = get_channel_service()
        if channel_service is None:
            logger.warning("ChannelService not available, skipping notification for task %s", task.task_id)
            return

        channel = channel_service.get_channel(task.notification.channel)
        if channel is None:
            logger.warning("Channel %s not available", task.notification.channel)
            return

        message = run.result_summary or "任务执行完成"
        if task.notification.include_summary and run.result_summary:
            message = f"【定时任务】{task.name}\n状态: {run.status}\n摘要: {run.result_summary}"

        try:
            outbound = OutboundMessage(
                channel_name=task.notification.channel,
                chat_id=task.notification.target,
                thread_id=run.thread_id,
                text=message,
            )
            await channel_service.bus.publish_outbound(outbound)
        except Exception:
            logger.exception("Failed to send notification via %s", task.notification.channel)

    async def create_task(self, task: ScheduledTask) -> ScheduledTask:
        self.tasks[task.task_id] = task
        if self.persistence:
            await self.persistence.save_task(task)
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
        if self.persistence:
            await self.persistence.save_task(self.tasks[task_id])
        return self.tasks[task_id]

    async def delete_task(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)
        if self.persistence:
            await self.persistence.delete_task(task_id)

    async def pause_task(self, task_id: str) -> None:
        await self.update_task(task_id, {"status": ScheduleStatus.PAUSED.value})

    async def resume_task(self, task_id: str) -> None:
        await self.update_task(task_id, {"status": ScheduleStatus.ACTIVE.value})

    async def list_tasks(self) -> list[ScheduledTask]:
        return list(self.tasks.values())

    async def get_runs(self, task_id: str) -> list[ScheduleRun]:
        return [r for r in self.runs if r.task_id == task_id]


_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service


def reset_scheduler_service() -> None:
    global _scheduler_service
    _scheduler_service = None
