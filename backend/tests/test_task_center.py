import json
from datetime import datetime

import pytest

from app.gateway.models.task_center import TaskRecord, TaskStatus
from app.gateway.services.task_center_service import (
    TaskCenterService,
    get_task_center_service,
    reset_task_center_service,
)


def _make_task(**overrides) -> TaskRecord:
    defaults = {
        "task_id": "task_001",
        "thread_id": "thread_001",
        "task_type": "manual",
        "name": "Test Task",
    }
    defaults.update(overrides)
    return TaskRecord(**defaults)


class TestTaskStatus:
    def test_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.SUCCESS == "success"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.PAUSED == "paused"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_status_is_str(self):
        assert isinstance(TaskStatus.PENDING, str)


class TestTaskRecord:
    def test_create_minimal(self):
        task = _make_task()
        assert task.task_id == "task_001"
        assert task.status == TaskStatus.PENDING
        assert task.description == ""
        assert task.created_by == "default"
        assert task.parent_task_id is None
        assert task.log_ids == []

    def test_create_with_all_fields(self):
        now = datetime.now()
        task = TaskRecord(
            task_id="task_002",
            thread_id="thread_002",
            task_type="schedule",
            name="Scheduled Task",
            description="A test task",
            status=TaskStatus.RUNNING,
            created_at=now,
            started_at=now,
            finished_at=None,
            duration=None,
            result={"key": "value"},
            error=None,
            log_ids=["log_1"],
            created_by="user_1",
            parent_task_id="task_001",
        )
        assert task.task_type == "schedule"
        assert task.result == {"key": "value"}
        assert task.parent_task_id == "task_001"

    def test_to_storage_dict_json_serializable(self):
        task = _make_task(result={"nested": {"key": 123}})
        data = task.to_storage_dict()
        serialized = json.dumps(data)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["task_id"] == "task_001"
        assert parsed["result"]["nested"]["key"] == 123

    def test_from_storage_dict_roundtrip(self):
        task = _make_task(result={"x": 1}, status=TaskStatus.RUNNING)
        data = task.to_storage_dict()
        restored = TaskRecord.from_storage_dict(data)
        assert restored.task_id == task.task_id
        assert restored.status == task.status
        assert restored.result == task.result

    def test_to_storage_dict_datetime_serializable(self):
        task = _make_task(started_at=datetime(2025, 1, 15, 10, 30, 0))
        data = task.to_storage_dict()
        serialized = json.dumps(data)
        assert isinstance(serialized, str)


class TestTaskCenterServiceCreateTask:
    @pytest.mark.asyncio
    async def test_create_task(self):
        svc = TaskCenterService()
        task = _make_task()
        result = await svc.create_task(task)
        assert result.task_id == "task_001"
        detail = await svc.get_task_detail("task_001")
        assert detail is not None
        assert detail.name == "Test Task"


class TestTaskCenterServiceListTasks:
    @pytest.mark.asyncio
    async def test_list_tasks_no_filter(self):
        svc = TaskCenterService()
        for i in range(5):
            await svc.create_task(_make_task(task_id=f"task_{i}", name=f"Task {i}"))
        tasks = await svc.list_tasks()
        assert len(tasks) == 5

    @pytest.mark.asyncio
    async def test_list_tasks_status_filter(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(task_id="t1", status=TaskStatus.PENDING))
        await svc.create_task(_make_task(task_id="t2", status=TaskStatus.RUNNING))
        await svc.create_task(_make_task(task_id="t3", status=TaskStatus.FAILED))
        tasks = await svc.list_tasks(status_filter="failed")
        assert len(tasks) == 1
        assert tasks[0].task_id == "t3"

    @pytest.mark.asyncio
    async def test_list_tasks_type_filter(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(task_id="t1", task_type="manual"))
        await svc.create_task(_make_task(task_id="t2", task_type="schedule"))
        tasks = await svc.list_tasks(task_type="schedule")
        assert len(tasks) == 1
        assert tasks[0].task_type == "schedule"

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self):
        svc = TaskCenterService()
        for i in range(10):
            await svc.create_task(_make_task(task_id=f"task_{i:02d}"))
        page1 = await svc.list_tasks(page=1, page_size=3)
        page2 = await svc.list_tasks(page=2, page_size=3)
        assert len(page1) == 3
        assert len(page2) == 3
        ids_p1 = {t.task_id for t in page1}
        ids_p2 = {t.task_id for t in page2}
        assert ids_p1.isdisjoint(ids_p2)

    @pytest.mark.asyncio
    async def test_list_tasks_sorted_by_created_at_desc(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(task_id="old"))
        await svc.create_task(_make_task(task_id="new"))
        tasks = await svc.list_tasks()
        assert tasks[0].task_id == "new"
        assert tasks[1].task_id == "old"


class TestTaskCenterServiceGetDetail:
    @pytest.mark.asyncio
    async def test_get_existing_task(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task())
        detail = await svc.get_task_detail("task_001")
        assert detail is not None
        assert detail.task_id == "task_001"

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self):
        svc = TaskCenterService()
        detail = await svc.get_task_detail("nonexistent")
        assert detail is None


class TestTaskCenterServiceUpdateStatus:
    @pytest.mark.asyncio
    async def test_update_status(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task())
        result = await svc.update_task_status("task_001", TaskStatus.RUNNING, started_at=datetime.now().isoformat())
        assert result is not None
        assert result.status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_status_nonexistent(self):
        svc = TaskCenterService()
        result = await svc.update_task_status("nonexistent", TaskStatus.RUNNING)
        assert result is None


class TestTaskCenterServiceRetryTask:
    @pytest.mark.asyncio
    async def test_retry_failed_task(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(status=TaskStatus.FAILED, error="boom"))
        result = await svc.retry_task("task_001")
        assert result.status == TaskStatus.PENDING
        assert result.error is None
        assert result.started_at is None
        assert result.finished_at is None

    @pytest.mark.asyncio
    async def test_retry_non_failed_task_raises(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(status=TaskStatus.RUNNING))
        with pytest.raises(ValueError, match="只能重试失败任务"):
            await svc.retry_task("task_001")

    @pytest.mark.asyncio
    async def test_retry_nonexistent_task_raises(self):
        svc = TaskCenterService()
        with pytest.raises(ValueError, match="not found"):
            await svc.retry_task("nonexistent")


class TestTaskCenterServiceRerunTask:
    @pytest.mark.asyncio
    async def test_rerun_same_thread(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task())
        new_task = await svc.rerun_task("task_001", use_new_thread=False)
        assert new_task.task_id != "task_001"
        assert new_task.thread_id == "thread_001"
        assert new_task.parent_task_id == "task_001"
        assert new_task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_rerun_new_thread(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task())
        new_task = await svc.rerun_task("task_001", use_new_thread=True)
        assert new_task.thread_id == ""
        assert new_task.parent_task_id == "task_001"

    @pytest.mark.asyncio
    async def test_rerun_nonexistent_raises(self):
        svc = TaskCenterService()
        with pytest.raises(ValueError, match="not found"):
            await svc.rerun_task("nonexistent")


class TestTaskCenterServiceCancelTask:
    @pytest.mark.asyncio
    async def test_cancel_running_task(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(status=TaskStatus.RUNNING))
        result = await svc.cancel_task("task_001")
        assert result.status == TaskStatus.CANCELLED
        assert result.finished_at is not None

    @pytest.mark.asyncio
    async def test_cancel_pending_task(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(status=TaskStatus.PENDING))
        result = await svc.cancel_task("task_001")
        assert result.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_success_task_raises(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(status=TaskStatus.SUCCESS))
        with pytest.raises(ValueError, match="只能取消运行中或等待中的任务"):
            await svc.cancel_task("task_001")

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_raises(self):
        svc = TaskCenterService()
        with pytest.raises(ValueError, match="not found"):
            await svc.cancel_task("nonexistent")


class TestTaskCenterServiceExportAudit:
    @pytest.mark.asyncio
    async def test_export_audit_json_format(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task(result={"output": "done"}))
        await svc.append_log("task_001", "step 1 completed")
        report_str = await svc.export_task_audit("task_001")
        report = json.loads(report_str)
        assert report["task_id"] == "task_001"
        assert report["name"] == "Test Task"
        assert report["status"] == "pending"
        assert "timeline" in report
        assert "created" in report["timeline"]
        assert report["result"] == {"output": "done"}
        assert len(report["logs"]) == 1
        assert "step 1 completed" in report["logs"][0]

    @pytest.mark.asyncio
    async def test_export_audit_nonexistent_raises(self):
        svc = TaskCenterService()
        with pytest.raises(ValueError, match="not found"):
            await svc.export_task_audit("nonexistent")


class TestTaskCenterServiceLogs:
    @pytest.mark.asyncio
    async def test_append_and_get_logs(self):
        svc = TaskCenterService()
        await svc.create_task(_make_task())
        await svc.append_log("task_001", "started")
        await svc.append_log("task_001", "finished")
        logs = await svc.get_task_logs("task_001")
        assert len(logs) == 2
        assert "started" in logs[0]
        assert "finished" in logs[1]

    @pytest.mark.asyncio
    async def test_get_logs_nonexistent_task(self):
        svc = TaskCenterService()
        logs = await svc.get_task_logs("nonexistent")
        assert logs == []

    @pytest.mark.asyncio
    async def test_log_truncation(self):
        svc = TaskCenterService(max_logs_per_task=5)
        await svc.create_task(_make_task())
        for i in range(10):
            await svc.append_log("task_001", f"entry {i}")
        logs = await svc.get_task_logs("task_001")
        assert len(logs) == 5
        assert "entry 5" in logs[0]
        assert "entry 9" in logs[4]


class TestTaskCenterServiceLRUEviction:
    @pytest.mark.asyncio
    async def test_evict_oldest_when_exceeds_max(self):
        svc = TaskCenterService(max_tasks=3)
        for i in range(5):
            await svc.create_task(_make_task(task_id=f"task_{i}"))
        assert len(svc._tasks) == 3
        detail = await svc.get_task_detail("task_0")
        assert detail is None
        detail = await svc.get_task_detail("task_1")
        assert detail is None
        detail = await svc.get_task_detail("task_4")
        assert detail is not None

    @pytest.mark.asyncio
    async def test_eviction_removes_logs(self):
        svc = TaskCenterService(max_tasks=2)
        await svc.create_task(_make_task(task_id="t1"))
        await svc.append_log("t1", "log entry")
        await svc.create_task(_make_task(task_id="t2"))
        await svc.create_task(_make_task(task_id="t3"))
        assert "t1" not in svc._logs


class TestTaskCenterServiceSingleton:
    def setup_method(self):
        reset_task_center_service()

    def teardown_method(self):
        reset_task_center_service()

    def test_get_singleton(self):
        svc1 = get_task_center_service()
        svc2 = get_task_center_service()
        assert svc1 is svc2

    def test_reset_singleton(self):
        svc1 = get_task_center_service()
        reset_task_center_service()
        svc2 = get_task_center_service()
        assert svc1 is not svc2
