# T10 - 任务中心数据模型与服务层

## 元信息
- **任务ID**: T10
- **阶段**: 第2期 - 场景与观测
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: 无（与 T07 并行）
- **关联差距**: 差距8 - 任务中心与观测面

## 目标
建立 TaskRecord 数据模型与 TaskCenterService 服务层，实现全局任务追踪的核心逻辑。TaskRecord 使用 dict 表示以兼容 ThreadState 的 JSON 可序列化约束，内存存储带 LRU 限制。

## 详细实现步骤

### 步骤1: 创建任务中心数据模型
- **文件**: `backend/app/gateway/models/task_center.py`
- **操作**: 新建
- **内容**: 完整任务记录模型（Pydantic 用于 API 层，内部存储使用 dict）
```python
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TaskRecord(BaseModel):
    """任务记录模型。

    内部存储使用 model_dump() 转为 dict，确保与 ThreadState
    的 JSON 可序列化约束兼容。不直接将 Pydantic 模型放入
    ThreadState 字段。
    """
    task_id: str
    thread_id: str
    task_type: str  # "manual"/"schedule"/"subagent"/"dag_node"
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration: float | None = None
    result: dict | None = None
    error: str | None = None
    log_ids: list[str] = Field(default_factory=list)
    created_by: str = "default"
    parent_task_id: str | None = None

    def to_storage_dict(self) -> dict:
        """转为存储用 dict，所有字段 JSON 可序列化。"""
        data = self.model_dump(mode="json")
        return data

    @classmethod
    def from_storage_dict(cls, data: dict) -> TaskRecord:
        """从存储 dict 恢复。"""
        return cls.model_validate(data)
```
- **验收**: 模型可实例化，字段校验通过，to_storage_dict 输出 JSON 可序列化

### 步骤2: 创建 TaskCenterService
- **文件**: `backend/app/gateway/services/task_center_service.py`
- **操作**: 新建
- **内容**: 核心服务方法，内存存储带 LRU 限制
```python
from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.gateway.models.task_center import TaskRecord, TaskStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MAX_TASKS = 10000
_MAX_LOGS_PER_TASK = 1000


class TaskCenterService:
    """任务中心服务，管理全局任务追踪。

    内存存储带 LRU 限制：
    - 最多 _MAX_TASKS 条任务记录，超出时淘汰最早创建的
    - 每个任务最多 _MAX_LOGS_PER_TASK 条日志，超出时截断最早的
    """

    def __init__(self, max_tasks: int = _MAX_TASKS, max_logs_per_task: int = _MAX_LOGS_PER_TASK) -> None:
        self._tasks: OrderedDict[str, dict] = OrderedDict()
        self._logs: dict[str, list[str]] = {}
        self._max_tasks = max_tasks
        self._max_logs_per_task = max_logs_per_task

    def _evict_if_needed(self) -> None:
        """LRU 淘汰超出上限的最早任务。"""
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
        """查询任务列表，支持分页和过滤"""
        tasks = [TaskRecord.from_storage_dict(t) for t in self._tasks.values()]
        if status_filter:
            tasks = [t for t in tasks if t.status.value == status_filter]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        start = (page - 1) * page_size
        return tasks[start:start + page_size]

    async def get_task_detail(self, task_id: str) -> TaskRecord | None:
        """查询任务详情"""
        data = self._tasks.get(task_id)
        if data is None:
            return None
        return TaskRecord.from_storage_dict(data)

    async def get_task_logs(self, task_id: str) -> list[str]:
        """查询任务执行日志"""
        return self._logs.get(task_id, [])

    async def create_task(self, task: TaskRecord) -> TaskRecord:
        """创建任务记录"""
        self._tasks[task.task_id] = task.to_storage_dict()
        self._tasks.move_to_end(task.task_id)
        self._evict_if_needed()
        logger.info("Created task %s (%s)", task.task_id, task.task_type)
        return task

    async def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> TaskRecord | None:
        """更新任务状态"""
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
        """重试失败任务"""
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
        """重新运行任务"""
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
        """取消运行中任务"""
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
        """导出审计报告"""
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
        """追加日志条目，带 LRU 截断"""
        if task_id not in self._logs:
            self._logs[task_id] = []
        logs = self._logs[task_id]
        logs.append(f"[{datetime.now().isoformat()}] {log_entry}")
        if len(logs) > self._max_logs_per_task:
            self._logs[task_id] = logs[-self._max_logs_per_task:]


_task_center_service: TaskCenterService | None = None


def get_task_center_service() -> TaskCenterService:
    """获取全局 TaskCenterService 单例"""
    global _task_center_service
    if _task_center_service is None:
        _task_center_service = TaskCenterService()
    return _task_center_service


def reset_task_center_service() -> None:
    """重置单例（用于测试）"""
    global _task_center_service
    _task_center_service = None
```
- **验收**: 内存存储可用，LRU 限制生效

### 步骤3: 实现 list_tasks 分页和过滤
- **文件**: `backend/app/gateway/services/task_center_service.py`
- **操作**: 续写（已包含在步骤2中）
- **验收**: 分页和过滤正确

### 步骤4: 实现 retry_task 和 rerun_task
- **文件**: `backend/app/gateway/services/task_center_service.py`
- **操作**: 续写（已包含在步骤2中）
- **验收**: 重试和重跑逻辑正确

### 步骤5: 实现 export_task_audit
- **文件**: `backend/app/gateway/services/task_center_service.py`
- **操作**: 续写（已包含在步骤2中）
- **验收**: 审计报告 JSON 格式正确

## 验收标准
- [ ] TaskRecord / TaskStatus 模型定义完成，支持 to_storage_dict/from_storage_dict
- [ ] TaskCenterService 9 个核心方法实现
- [ ] 内存存储使用 OrderedDict 带 LRU 限制（max_tasks=10000）
- [ ] 日志存储带 LRU 截断（max_logs_per_task=1000）
- [ ] retry_task 仅允许失败任务重试
- [ ] rerun_task 支持新建/复用线程
- [ ] export_task_audit 输出完整审计报告

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | create_task | 任务创建成功 |
| 单元测试 | list_tasks 无过滤 | 返回所有任务 |
| 单元测试 | list_tasks 按状态过滤 | 仅返回指定状态 |
| 单元测试 | list_tasks 分页 | 正确分页 |
| 单元测试 | retry_task 非失败 | 抛出 ValueError |
| 单元测试 | retry_task 失败任务 | 状态→PENDING |
| 单元测试 | rerun_task 新线程 | 新 task_id |
| 单元测试 | export_audit | JSON 格式正确 |
| 单元测试 | LRU 淘汰 | 超出 max_tasks 时淘汰最早任务 |
| 单元测试 | 日志截断 | 超出 max_logs_per_task 时截断 |
| 单元测试 | to_storage_dict JSON 序列化 | dict 可被 json.dumps 序列化 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 内存存储不支持持久化 | 低 | 第一版内存，后续换 DB |
| 任务量过大内存溢出 | 中 | LRU 限制最大数量（10000） |
| 日志量过大 | 中 | 每任务最大日志条数（1000） |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第8节
- ThreadState TypedDict 约束: `backend/packages/harness/deerflow/agents/thread_state.py`
