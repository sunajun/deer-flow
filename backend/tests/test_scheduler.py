from datetime import UTC, datetime, timedelta

import pytest

from deerflow.scheduler.models import ScheduledTask, ScheduleStatus, ScheduleTrigger
from deerflow.scheduler.service import SchedulerService


def _make_task(**overrides) -> ScheduledTask:
    defaults = {
        "task_id": "task_001",
        "name": "Test Task",
        "prompt": "hello",
    }
    defaults.update(overrides)
    return ScheduledTask(**defaults)


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task(self):
        svc = SchedulerService()
        task = _make_task()
        result = await svc.create_task(task)
        assert result.task_id == "task_001"
        assert task.task_id in svc.tasks


class TestShouldTriggerCron:
    def test_cron_match_weekday_9am(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="0 9 * * 1-5", timezone="UTC"))
        monday_9am = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)
        assert svc._should_trigger(task, monday_9am) is True

    def test_cron_no_match_weekend(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="0 9 * * 1-5", timezone="UTC"))
        saturday_9am = datetime(2026, 5, 23, 9, 0, tzinfo=UTC)
        assert svc._should_trigger(task, saturday_9am) is False

    def test_cron_no_match_wrong_hour(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="0 9 * * *"))
        tuesday_10am = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)
        assert svc._should_trigger(task, tuesday_10am) is False

    def test_cron_every_minute(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="* * * * *"))
        now = datetime.now(UTC)
        assert svc._should_trigger(task, now) is True


class TestShouldTriggerInterval:
    def test_interval_first_run(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(interval_seconds=300))
        now = datetime.now(UTC)
        assert svc._should_trigger(task, now) is True

    def test_interval_not_yet(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(interval_seconds=300))
        now = datetime.now(UTC)
        task.last_run_at = now - timedelta(seconds=100)
        assert svc._should_trigger(task, now) is False

    def test_interval_elapsed(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(interval_seconds=300))
        now = datetime.now(UTC)
        task.last_run_at = now - timedelta(seconds=301)
        assert svc._should_trigger(task, now) is True


class TestShouldNotTriggerPaused:
    def test_paused_task_not_triggered(self):
        svc = SchedulerService()
        task = _make_task(
            status=ScheduleStatus.PAUSED,
            trigger=ScheduleTrigger(cron="* * * * *"),
        )
        now = datetime.now(UTC)
        assert svc._should_trigger(task, now) is True

    @pytest.mark.asyncio
    async def test_tick_skips_paused_task(self):
        svc = SchedulerService()
        task = _make_task(
            status=ScheduleStatus.PAUSED,
            trigger=ScheduleTrigger(cron="* * * * *"),
        )
        await svc.create_task(task)
        await svc._tick()
        assert task.run_count == 0


class TestPauseResume:
    @pytest.mark.asyncio
    async def test_pause_task(self):
        svc = SchedulerService()
        task = _make_task()
        await svc.create_task(task)
        await svc.pause_task("task_001")
        assert svc.tasks["task_001"].status == ScheduleStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_task(self):
        svc = SchedulerService()
        task = _make_task(status=ScheduleStatus.PAUSED)
        await svc.create_task(task)
        await svc.resume_task("task_001")
        assert svc.tasks["task_001"].status == ScheduleStatus.ACTIVE


class TestTickNoActiveTasks:
    @pytest.mark.asyncio
    async def test_tick_with_no_tasks(self):
        svc = SchedulerService()
        await svc._tick()

    @pytest.mark.asyncio
    async def test_tick_with_all_paused(self):
        svc = SchedulerService()
        task = _make_task(status=ScheduleStatus.PAUSED)
        await svc.create_task(task)
        await svc._tick()
        assert task.run_count == 0


class TestCronTimezone:
    def test_cron_asia_shanghai(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="0 9 * * *", timezone="Asia/Shanghai"))
        utc_1am = datetime(2026, 5, 25, 1, 0, tzinfo=UTC)
        assert svc._should_trigger(task, utc_1am) is True

    def test_cron_utc(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="0 9 * * *", timezone="UTC"))
        utc_9am = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)
        assert svc._should_trigger(task, utc_9am) is True

    def test_cron_unknown_timezone_falls_back_to_utc(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="0 9 * * *", timezone="Invalid/TZ"))
        utc_9am = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)
        assert svc._should_trigger(task, utc_9am) is True


class TestIntervalFirstRun:
    @pytest.mark.asyncio
    async def test_interval_first_run_triggers(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(interval_seconds=300))
        await svc.create_task(task)
        await svc._tick()
        assert task.run_count == 1


class TestCronNoDuplicateFire:
    def test_same_minute_no_duplicate(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="* * * * *"))
        now = datetime(2026, 5, 23, 10, 30, tzinfo=UTC)
        assert svc._should_trigger(task, now) is True
        task.last_fired_cron_time = now
        assert svc._should_trigger(task, now) is False

    def test_different_minute_triggers(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="* * * * *"))
        now = datetime(2026, 5, 23, 10, 30, tzinfo=UTC)
        task.last_fired_cron_time = now - timedelta(minutes=1)
        assert svc._should_trigger(task, now) is True

    def test_same_minute_different_second_no_duplicate(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="* * * * *"))
        t1 = datetime(2026, 5, 23, 10, 30, 15, tzinfo=UTC)
        t2 = datetime(2026, 5, 23, 10, 30, 45, tzinfo=UTC)
        assert svc._should_trigger(task, t1) is True
        task.last_fired_cron_time = t1
        assert svc._should_trigger(task, t2) is False


class TestInvalidCronExpression:
    def test_invalid_cron_returns_false(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger(cron="invalid cron"))
        now = datetime.now(UTC)
        assert svc._should_trigger(task, now) is False

    def test_empty_cron_and_no_interval(self):
        svc = SchedulerService()
        task = _make_task(trigger=ScheduleTrigger())
        now = datetime.now(UTC)
        assert svc._should_trigger(task, now) is False


class TestCRUDOperations:
    @pytest.mark.asyncio
    async def test_create_and_list(self):
        svc = SchedulerService()
        await svc.create_task(_make_task(task_id="t1"))
        await svc.create_task(_make_task(task_id="t2"))
        tasks = await svc.list_tasks()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_update_task(self):
        svc = SchedulerService()
        await svc.create_task(_make_task())
        updated = await svc.update_task("task_001", {"name": "Updated"})
        assert updated.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self):
        svc = SchedulerService()
        with pytest.raises(ValueError, match="not found"):
            await svc.update_task("nonexistent", {"name": "X"})

    @pytest.mark.asyncio
    async def test_delete_task(self):
        svc = SchedulerService()
        await svc.create_task(_make_task())
        await svc.delete_task("task_001")
        assert "task_001" not in svc.tasks

    @pytest.mark.asyncio
    async def test_delete_nonexistent_no_error(self):
        svc = SchedulerService()
        await svc.delete_task("nonexistent")

    @pytest.mark.asyncio
    async def test_get_runs_empty(self):
        svc = SchedulerService()
        runs = await svc.get_runs("task_001")
        assert runs == []


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        svc = SchedulerService()
        svc._tick_interval = 0
        started = False

        async def _mock_tick():
            nonlocal started
            started = True
            svc._running = False

        svc._tick = _mock_tick
        await svc.start()
        assert started is True

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        svc = SchedulerService()
        svc._running = True
        await svc.stop()
        assert svc._running is False
