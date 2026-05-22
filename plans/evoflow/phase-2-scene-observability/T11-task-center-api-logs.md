# T11 - 任务中心 API 路由与日志存储

## 元信息
- **任务ID**: T11
- **阶段**: 第2期 - 场景与观测
- **优先级**: P2
- **预估工期**: 2 天
- **依赖任务**: T10
- **关联差距**: 差距8 - 任务中心与观测面

## 目标
创建任务中心 REST API，实现任务日志存储和检索，导出审计报告。路由在 `create_app()` 中注册，持久化使用现有 SQLAlchemy session factory。

## 详细实现步骤

### 步骤1: 创建任务 API 路由
- **文件**: `backend/app/gateway/routers/tasks.py`
- **操作**: 新建
- **内容**: 7 个 API 端点
```python
from fastapi import APIRouter, Query, Response

from app.gateway.models.task_center import TaskRecord, TaskStatus
from app.gateway.services.task_center_service import get_task_center_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/")
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    task_type: str | None = None,
):
    service = get_task_center_service()
    tasks = await service.list_tasks(page, page_size, status, task_type)
    return {
        "tasks": [t.model_dump(mode="json") for t in tasks],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{task_id}")
async def get_task_detail(task_id: str):
    service = get_task_center_service()
    task = await service.get_task_detail(task_id)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    return task.model_dump(mode="json")


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    service = get_task_center_service()
    logs = await service.get_task_logs(task_id)
    return {"task_id": task_id, "logs": logs}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    service = get_task_center_service()
    try:
        task = await service.retry_task(task_id)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.post("/{task_id}/rerun")
async def rerun_task(task_id: str, use_new_thread: bool = False):
    service = get_task_center_service()
    try:
        task = await service.rerun_task(task_id, use_new_thread=use_new_thread)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    service = get_task_center_service()
    try:
        task = await service.cancel_task(task_id)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.get("/{task_id}/export")
async def export_audit(task_id: str):
    service = get_task_center_service()
    try:
        report = await service.export_task_audit(task_id)
        return Response(content=report, media_type="application/json")
    except ValueError as e:
        return {"error": str(e)}
```
- **验收**: 所有端点可访问

### 步骤2: 集成到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 函数中注册 tasks router
```python
from app.gateway.routers import (
    agents,
    artifacts,
    assistants_compat,
    auth,
    channels,
    feedback,
    mcp,
    memory,
    models,
    runs,
    scenes,
    skills,
    suggestions,
    tasks,
    thread_runs,
    threads,
    uploads,
)

def create_app() -> FastAPI:
    # ... 现有逻辑 ...

    # Tasks API is mounted at /api/tasks
    app.include_router(tasks.router)

    # ... 后续路由注册 ...
```
- **验收**: API 在 Gateway 启动后可访问

### 步骤3: 实现日志存储
- **文件**: `backend/app/gateway/services/task_center_service.py`
- **操作**: 续写（已在 T10 中实现 append_log 和 get_task_logs）
- **验收**: 日志可追加和检索

### 步骤4: 持久化层（SQLAlchemy）
- **文件**: `backend/app/gateway/models/task_center_db.py`
- **操作**: 新建
- **内容**: 使用现有 SQLAlchemy session factory 进行持久化
```python
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class TaskRow(Base):
    __tablename__ = "task_records"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration: Mapped[float | None] = mapped_column(nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="default")
    parent_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TaskLogRow(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    entry: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

- **文件**: `backend/app/gateway/services/task_center_persistence.py`
- **操作**: 新建
- **内容**: 使用现有 session factory 进行数据库读写
```python
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select

from app.gateway.models.task_center import TaskRecord, TaskStatus
from app.gateway.models.task_center_db import TaskLogRow, TaskRow
from deerflow.persistence.engine import get_session_factory

logger = logging.getLogger(__name__)


class TaskCenterPersistence:
    """任务中心持久化层，使用现有 SQLAlchemy session factory。"""

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
```
- **关键约束**: 使用 `get_session_factory()` 从 `deerflow.persistence.engine` 获取 session factory。当 backend=memory 时返回 None，此时持久化层为空操作。
- **验收**: 数据可持久化和读取

### 步骤5: 集成到任务执行流程
- **文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`（或相关运行时文件）
- **操作**: 改造
- **内容**: 在子代理执行前后调用 TaskCenterService 记录状态变化和日志
- **验收**: 任务执行过程被自动追踪

## 验收标准
- [ ] 7 个 API 端点全部可访问
- [ ] tasks router 在 `create_app()` 中注册
- [ ] 任务列表支持分页和状态/类型过滤
- [ ] 日志存储和检索正常
- [ ] 审计报告导出 JSON 格式正确
- [ ] SQLAlchemy 持久化层使用现有 `get_session_factory()`
- [ ] 任务执行流程自动记录日志

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 集成测试 | GET /api/tasks | 返回任务列表 |
| 集成测试 | GET /api/tasks?status=failed | 仅失败任务 |
| 集成测试 | GET /api/tasks/{id} | 返回任务详情 |
| 集成测试 | POST /api/tasks/{id}/retry | 状态→PENDING |
| 集成测试 | POST /api/tasks/{id}/cancel | 状态→CANCELLED |
| 集成测试 | GET /api/tasks/{id}/logs | 返回日志列表 |
| 集成测试 | GET /api/tasks/{id}/export | 返回审计 JSON |
| 单元测试 | TaskCenterPersistence.save_task | 数据写入 DB |
| 单元测试 | TaskCenterPersistence.load_task | 数据从 DB 读取 |
| 单元测试 | backend=memory 时持久化 | get_session_factory() 返回 None，持久化为空操作 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 日志量过大 | 中 | 限制单任务最大日志条数 |
| API 与现有 LangGraph API 冲突 | 低 | 独立前缀 /api/tasks |
| 持久化层与 backend=memory 不兼容 | 低 | get_session_factory() 返回 None 时跳过 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第8节
- SQLAlchemy session factory: `backend/packages/harness/deerflow/persistence/engine.py`
- create_app 路由注册: `backend/app/gateway/app.py`
