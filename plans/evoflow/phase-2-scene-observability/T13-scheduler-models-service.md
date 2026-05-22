# T13 - 定时任务数据模型与调度服务

## 元信息
- **任务ID**: T13
- **阶段**: 第2期 - 场景与观测
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: T10（任务中心模型，定时任务为任务中心的一种 task_type）
- **关联差距**: 差距4 - 定时任务

## 目标
建立 ScheduledTask 数据模型与 SchedulerService 调度服务，实现 cron 和间隔两种调度模式。cron 触发使用 `croniter.match()` 精确匹配，SchedulerService 在 Gateway `lifespan` 上下文管理器中启动和停止。

## 详细实现步骤

### 步骤1: 创建定时任务数据模型
- **文件**: `backend/packages/harness/deerflow/scheduler/__init__.py`
- **操作**: 新建
- **内容**: 模块入口

- **文件**: `backend/packages/harness/deerflow/scheduler/models.py`
- **操作**: 新建
- **内容**: 完整数据模型
```python
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ScheduleTrigger(BaseModel):
    cron: str = ""
    timezone: str = "Asia/Shanghai"
    interval_seconds: int | None = None


class ScheduleNotification(BaseModel):
    enabled: bool = False
    channel: str = "feishu"
    target: str = ""
    include_summary: bool = True
    include_full_output: bool = False


class ScheduledTask(BaseModel):
    task_id: str
    name: str
    description: str = ""
    prompt: str
    trigger: ScheduleTrigger = Field(default_factory=ScheduleTrigger)
    notification: ScheduleNotification = Field(default_factory=ScheduleNotification)
    use_orchestration: bool = False
    reuse_thread: bool = False
    thread_id: str | None = None
    timeout_seconds: int = 3600
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0
    last_fired_cron_time: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ScheduleRun(BaseModel):
    run_id: str
    task_id: str
    thread_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    result_summary: str | None = None
    error: str | None = None
```
- **验收**: 模型可实例化

### 步骤2: 添加 croniter 依赖
- **文件**: `backend/pyproject.toml`
- **操作**: 改造
- **内容**: `uv add croniter`
- **验收**: croniter 可导入

### 步骤3: 创建 SchedulerService
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 新建
- **内容**: 调度服务核心
```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter

from deerflow.scheduler.models import ScheduleRun, ScheduleStatus, ScheduledTask

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.runs: list[ScheduleRun] = []
        self._running = False
        self._tick_interval = 60

    async def start(self) -> None:
        """启动调度循环"""
        self._running = True
        logger.info("SchedulerService started")
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self._tick_interval)

    async def stop(self) -> None:
        """停止调度循环"""
        self._running = False
        logger.info("SchedulerService stopped")
```
- **验收**: 服务可启动和停止

### 步骤4: 实现 _tick 和 _should_trigger
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**: 调度检查逻辑，cron 使用 `croniter.match()` 精确匹配
```python
    async def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        for task in list(self.tasks.values()):
            if task.status != ScheduleStatus.ACTIVE:
                continue
            if self._should_trigger(task, now):
                await self._execute(task)

    def _should_trigger(self, task: ScheduledTask, now: datetime) -> bool:
        """判断是否应该触发任务。

        cron 模式使用 croniter.match() 精确匹配当前时间点，
        并通过 last_fired_cron_time 避免同一分钟内重复触发。
        interval 模式基于 last_run_at 计算间隔。
        """
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
            return timezone.utc
```
- **关键修正**: 原方案使用 `now >= next_time and (now - next_time).total_seconds() < 60` 窗口检查，存在以下问题：
  1. 如果 tick 间隔 > 60s 可能错过触发窗口
  2. 如果 tick 在窗口边界附近可能重复触发
  3. `get_next(datetime)` 返回的是下一个触发时间，不是当前时间是否匹配

  修正方案使用 `croniter.match(cron, local_now)` 精确匹配当前时间点是否满足 cron 表达式，并通过 `last_fired_cron_time` 跟踪上次触发时间，避免同一分钟内重复触发。
- **验收**: cron 和 interval 两种模式触发正确

### 步骤5: 实现 CRUD 操作
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**:
```python
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
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
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
```
- **验收**: CRUD 操作正确

### 步骤6: 创建调度服务测试
- **文件**: `backend/tests/test_scheduler.py`
- **操作**: 新建
- **内容**: 调度核心测试
```python
from datetime import datetime, timezone

from deerflow.scheduler.models import ScheduleTrigger, ScheduleStatus, ScheduledTask
from deerflow.scheduler.service import SchedulerService


def test_create_task():
    """创建定时任务"""


def test_should_trigger_cron():
    """cron 触发 — 使用 croniter.match"""


def test_should_trigger_interval():
    """interval 触发"""


def test_should_not_trigger_paused():
    """暂停不触发"""


def test_pause_resume():
    """暂停/恢复"""


def test_tick_no_active_tasks():
    """无活跃任务"""


def test_cron_timezone():
    """时区处理"""


def test_interval_first_run():
    """首次立即触发"""


def test_cron_no_duplicate_fire():
    """同一分钟内不重复触发 — last_fired_cron_time 去重"""


def test_invalid_cron_expression():
    """无效 cron 表达式不触发"""
```
- **验收**: 所有测试通过

## 验收标准
- [ ] ScheduledTask / ScheduleTrigger / ScheduleRun 模型定义完成
- [ ] croniter 依赖添加
- [ ] SchedulerService 启动/停止/循环正确
- [ ] cron 使用 `croniter.match()` + `last_fired_cron_time` 去重
- [ ] interval 两种触发模式正确
- [ ] CRUD 操作实现
- [ ] 调度核心测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | cron 触发 "0 9 * * 1-5" | 工作日9点触发 |
| 单元测试 | interval 触发 300s | 间隔5分钟触发 |
| 单元测试 | 暂停任务不触发 | _should_trigger 返回 False |
| 单元测试 | 首次 interval 触发 | 无 last_run_at 时立即触发 |
| 单元测试 | CRUD | 创建/读取/更新/删除正确 |
| 单元测试 | cron 去重 | 同一分钟不重复触发 |
| 单元测试 | 无效 cron | 返回 False，不抛异常 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| croniter 与系统时区不一致 | 中 | 统一使用 UTC，显示层转换 |
| tick 间隔 60s 可能错过触发 | 低 | croniter.match 精确匹配，不依赖窗口 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第4节
- croniter.match() 文档: https://github.com/kiorky/croniter
