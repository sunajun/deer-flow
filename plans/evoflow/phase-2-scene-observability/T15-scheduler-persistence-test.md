# T15 - 定时任务持久化与完整测试

## 元信息
- **任务ID**: T15
- **阶段**: 第2期 - 场景与观测
- **优先级**: P3
- **预估工期**: 2 天
- **依赖任务**: T14
- **关联差距**: 差距4 - 定时任务

## 目标
实现定时任务和执行记录的数据库持久化，完成调度服务完整测试套件，更新配置。使用 SQLAlchemy ORM 和现有 `get_session_factory()`，新增 `SchedulerConfig` Pydantic 配置类到 `AppConfig`。

## 详细实现步骤

### 步骤1: 创建 SchedulerConfig 配置类
- **文件**: `backend/packages/harness/deerflow/config/scheduler_config.py`
- **操作**: 新建
- **内容**: Pydantic 配置类，遵循现有配置模式
```python
from pydantic import BaseModel, ConfigDict, Field


class SchedulerConfig(BaseModel):
    """Configuration for the scheduler service."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Enable the scheduler service")
    tick_interval: int = Field(default=60, description="Tick interval in seconds")
    max_concurrent_runs: int = Field(default=5, description="Maximum concurrent scheduled runs")
    default_timeout: int = Field(default=3600, description="Default timeout in seconds for scheduled runs")
    persist_to_db: bool = Field(default=True, description="Persist scheduled tasks to database")
```

- **文件**: `backend/packages/harness/deerflow/config/app_config.py`
- **操作**: 改造
- **内容**: 在 AppConfig 中新增 scheduler 字段
```python
from deerflow.config.scheduler_config import SchedulerConfig

class AppConfig(BaseModel):
    # ... 现有字段 ...
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig, description="Scheduler service configuration")
    # ... model_config = ConfigDict(extra="allow") 保持不变 ...
```
- **关键约束**: AppConfig 使用 `model_config = ConfigDict(extra="allow")`，新增配置类必须作为显式字段添加，不能仅依赖 `extra="allow"` 来承载。遵循现有模式（如 `LoopDetectionConfig`、`MemoryConfig` 等）。
- **验收**: 配置项可被正确解析

### 步骤2: 设计数据库表（SQLAlchemy ORM）
- **文件**: `backend/packages/harness/deerflow/scheduler/db_models.py`
- **操作**: 新建
- **内容**: 使用 SQLAlchemy ORM 定义表结构
```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class ScheduledTaskRow(Base):
    __tablename__ = "scheduled_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text)
    trigger_config: Mapped[str] = mapped_column(Text)
    notification_config: Mapped[str] = mapped_column(Text, default="{}")
    use_orchestration: Mapped[bool] = mapped_column(Boolean, default=False)
    reuse_thread: Mapped[bool] = mapped_column(Boolean, default=False)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fired_cron_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ScheduleRunRow(Base):
    __tablename__ = "schedule_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
```
- **验收**: 表创建成功

### 步骤3: 实现持久化层
- **文件**: `backend/packages/harness/deerflow/scheduler/persistence.py`
- **操作**: 新建
- **内容**: 使用现有 `get_session_factory()` 进行数据库读写
```python
from __future__ import annotations

import json
import logging
from datetime import datetime

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
```
- **关键约束**: 使用 `get_session_factory()` 从 `deerflow.persistence.engine` 获取 session factory。当 backend=memory 时返回 None，此时持久化层为空操作。
- **验收**: 数据可持久化和读取

### 步骤4: 集成持久化到 SchedulerService
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 改造
- **内容**: 内存+数据库双写，启动时从数据库加载
```python
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

    async def create_task(self, task: ScheduledTask) -> ScheduledTask:
        self.tasks[task.task_id] = task
        if self.persistence:
            await self.persistence.save_task(task)
        logger.info("Created scheduled task %s", task.task_id)
        return task
```
- **验收**: 重启后任务不丢失

### 步骤5: 完整测试套件
- **文件**: `backend/tests/test_scheduler.py`
- **操作**: 续写
- **内容**: 扩展测试
```python
def test_execute_creates_thread():
    """执行创建线程"""


def test_execute_reuse_thread():
    """复用线程"""


def test_wait_and_notify_success():
    """等待完成+推送"""


def test_wait_and_notify_timeout():
    """超时处理"""


def test_notification_channel_service():
    """通过 get_channel_service() 推送"""


def test_notification_channel_unavailable():
    """ChannelService 不可用时跳过推送"""


def test_persistence_save_load():
    """持久化读写"""


def test_persistence_restart_recovery():
    """重启恢复"""


def test_concurrent_execution_limit():
    """并发上限"""


def test_cron_timezone_shanghai():
    """上海时区"""


def test_manual_trigger():
    """手动触发"""


def test_pause_resume_flow():
    """暂停/恢复流程"""


def test_scheduler_config_in_app_config():
    """SchedulerConfig 作为 AppConfig 字段可解析"""


def test_backend_memory_persistence():
    """backend=memory 时 get_session_factory() 返回 None，持久化为空操作"""
```
- **验收**: 所有测试通过

### 步骤6: 更新配置
- **文件**: `config.example.yaml`
- **操作**: 改造
- **内容**: 新增 scheduler 配置段
```yaml
scheduler:
  enabled: true
  tick_interval: 60
  max_concurrent_runs: 5
  default_timeout: 3600
  persist_to_db: true
```
- **验收**: 配置项可被正确解析

## 验收标准
- [ ] SchedulerConfig Pydantic 配置类添加到 AppConfig
- [ ] SQLAlchemy ORM 表定义完成（ScheduledTaskRow, ScheduleRunRow）
- [ ] SchedulePersistence 使用 `get_session_factory()` 实现完整
- [ ] SchedulerService 集成持久化
- [ ] 重启后任务可恢复
- [ ] 完整测试套件通过
- [ ] 配置示例更新

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | 持久化保存/加载 | 数据一致 |
| 单元测试 | 重启恢复 | 任务不丢失 |
| 单元测试 | 并发上限 | 超限拒绝 |
| 单元测试 | SchedulerConfig 解析 | enabled/tick_interval 正确 |
| 单元测试 | backend=memory 持久化 | get_session_factory() 返回 None，空操作 |
| 集成测试 | 完整调度周期 | 创建→触发→执行→推送 |
| 集成测试 | 暂停→恢复 | 状态正确切换 |
| 集成测试 | 手动触发 | 立即执行 |
| 集成测试 | 超时处理 | 标记失败 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 数据库迁移与现有 schema 冲突 | 低 | 使用独立表 |
| 持久化写入性能 | 低 | 异步批量写入 |
| SchedulerConfig 未在 AppConfig 中注册 | 低 | 作为显式字段添加 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第4节
- SQLAlchemy session factory: `backend/packages/harness/deerflow/persistence/engine.py`（`get_session_factory()`）
- AppConfig 配置模式: `backend/packages/harness/deerflow/config/app_config.py`
- 现有配置类示例: `backend/packages/harness/deerflow/config/loop_detection_config.py`
