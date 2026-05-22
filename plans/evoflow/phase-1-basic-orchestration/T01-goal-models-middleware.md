# T01 - 目标快照数据模型与中间件

## 元信息
- **任务ID**: T01
- **阶段**: 第1期 - 基础编排增强
- **优先级**: P1
- **预估工期**: 2 天
- **依赖任务**: 无
- **关联差距**: 差距5 - 核心目标/子问题状态

## 目标
建立 GoalSnapshot 核心数据模型与 GoalTrackerMiddleware 中间件，实现目标/子问题结构化追踪与 system prompt 注入能力。

## 详细实现步骤

### 步骤1: 创建目标数据模型
- **文件**: `backend/packages/harness/deerflow/goal/__init__.py`
- **操作**: 新建
- **内容**: 模块入口，导出核心类
```python
from deerflow.goal.models import GoalSnapshot, SubProblem, ProblemStatus
```

- **文件**: `backend/packages/harness/deerflow/goal/models.py`
- **操作**: 新建
- **内容**:
```python
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProblemStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    DROPPED = "dropped"


class SubProblem(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: ProblemStatus = ProblemStatus.OPEN
    assigned_to: str | None = None
    result_summary: str | None = None
    blockers: list[str] = Field(default_factory=list)


class GoalSnapshot(BaseModel):
    goal_id: str
    core_goal: str
    non_goals: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    sub_problems: list[SubProblem] = Field(default_factory=list)
    current_focus: str | None = None
    alignment_version: int = 1
    last_aligned_at: datetime = Field(default_factory=datetime.now)
    direction_changes: list[dict] = Field(default_factory=list)
```
- **验收**: 模型可实例化，字段类型校验通过

### 步骤2: 扩展 ThreadState
- **文件**: `backend/packages/harness/deerflow/agents/thread_state.py`
- **操作**: 改造
- **内容**: 在现有 `ThreadState` 中新增字段。**注意**: `ThreadState` 是 `TypedDict`，LangGraph 要求所有 state 字段必须 JSON 可序列化，**不能**直接使用 Pydantic 模型类型。必须使用 `dict` 类型，在中间件/服务层内部做 dict ↔ Pydantic 模型转换。
```python
from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState


class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]


class ThreadDataState(TypedDict):
    workspace_path: NotRequired[str | None]
    uploads_path: NotRequired[str | None]
    outputs_path: NotRequired[str | None]


class ViewedImageData(TypedDict):
    base64: str
    mime_type: str


def merge_artifacts(existing: list[str] | None, new: list[str] | None) -> list[str]:
    if existing is None:
        return new or []
    if new is None:
        return existing
    return list(dict.fromkeys(existing + new))


def merge_viewed_images(existing: dict[str, ViewedImageData] | None, new: dict[str, ViewedImageData] | None) -> dict[str, ViewedImageData]:
    if existing is None:
        return new or {}
    if new is None:
        return existing
    if len(new) == 0:
        return {}
    return {**existing, **new}


class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
    goal_snapshot: NotRequired[dict | None]
```
- **验收**: `ThreadState` 新增 `goal_snapshot: NotRequired[dict | None]` 字段，不破坏现有代码。中间件内部使用 `GoalSnapshot.model_validate(state["goal_snapshot"])` 反序列化，使用 `snapshot.model_dump()` 序列化回 dict。

### 步骤3: 创建 GoalTrackerMiddleware
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py`
- **操作**: 新建
- **内容**: 中间件必须继承 `AgentMiddleware[ThreadState]`，使用标准钩子方法。`on_plan_created` / `on_subtask_completed` / `on_direction_change` 是**公开业务方法**，供 `PlanEngine` 直接调用，**不是**中间件钩子。`inject_to_prompt` 在 `before_agent` 中调用（与 `DynamicContextMiddleware` 类似，在模型调用前注入上下文）。
```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest, ToolCallResult
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import ThreadState
from deerflow.goal.models import GoalSnapshot, ProblemStatus, SubProblem

logger = logging.getLogger(__name__)


class GoalTrackerMiddleware(AgentMiddleware[ThreadState]):
    """目标追踪中间件：在 system prompt 中注入目标摘要，追踪子问题状态。"""

    def _get_snapshot(self, state: ThreadState) -> GoalSnapshot | None:
        raw = state.get("goal_snapshot")
        if raw is None:
            return None
        return GoalSnapshot.model_validate(raw)

    def _put_snapshot(self, snapshot: GoalSnapshot) -> dict:
        return {"goal_snapshot": snapshot.model_dump()}

    def on_plan_created(self, state: ThreadState, plan: dict) -> dict:
        """Plan 创建时，从 Plan 生成 GoalSnapshot。由 PlanEngine 直接调用。"""
        snapshot = GoalSnapshot(
            goal_id=f"goal_{plan.get('plan_id', 'unknown')}",
            core_goal=plan.get("goal", ""),
            non_goals=[],
            acceptance_criteria=plan.get("acceptance_criteria", []),
            sub_problems=[
                SubProblem(
                    id=f"sub_{node_id}",
                    title=node_data.get("title", ""),
                    description=node_data.get("description", ""),
                    acceptance_criteria=node_data.get("acceptance_criteria", []),
                    assigned_to=node_data.get("assignee"),
                )
                for node_id, node_data in plan.get("nodes", {}).items()
            ],
        )
        return self._put_snapshot(snapshot)

    def on_subtask_completed(self, state: ThreadState, node_id: str, result: str) -> dict:
        """子任务完成时，更新子问题状态。由 PlanEngine 直接调用。"""
        snapshot = self._get_snapshot(state)
        if snapshot is None:
            return {}
        for sub in snapshot.sub_problems:
            if sub.id == f"sub_{node_id}":
                sub.status = ProblemStatus.RESOLVED
                sub.result_summary = str(result)[:500]
                break
        return self._put_snapshot(snapshot)

    def on_direction_change(self, state: ThreadState, new_direction: str) -> dict:
        """方向变更时触发再对齐。由 PlanEngine 直接调用。"""
        snapshot = self._get_snapshot(state)
        if snapshot is None:
            return {}
        snapshot.direction_changes.append({
            "from": snapshot.core_goal,
            "to": new_direction,
            "at": datetime.now().isoformat(),
        })
        snapshot.core_goal = new_direction
        snapshot.alignment_version += 1
        snapshot.last_aligned_at = datetime.now()
        for sub in snapshot.sub_problems:
            if sub.status not in (ProblemStatus.RESOLVED, ProblemStatus.DROPPED):
                sub.status = ProblemStatus.OPEN
        return self._put_snapshot(snapshot)

    def inject_to_prompt(self, state: ThreadState) -> str:
        """生成注入 system prompt 的目标摘要文本。"""
        snapshot = self._get_snapshot(state)
        if snapshot is None:
            return ""
        lines = [
            f"【核心目标】{snapshot.core_goal}",
            f"【验收标准】{'; '.join(snapshot.acceptance_criteria)}",
            "【子问题】",
        ]
        for sub in snapshot.sub_problems:
            lines.append(f"  - [{sub.status.value}] {sub.title}: {sub.description}")
            if sub.result_summary:
                lines.append(f"    结果: {sub.result_summary}")
        if snapshot.non_goals:
            lines.append(f"【非目标】{'; '.join(snapshot.non_goals)}")
        lines.append(f"【对齐版本】v{snapshot.alignment_version}")
        return "\n".join(lines)

    @override
    def before_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        """在 agent 执行前注入目标摘要到消息列表。"""
        prompt_text = self.inject_to_prompt(state)
        if not prompt_text:
            return None
        messages = list(state.get("messages", []))
        if not messages:
            return None
        reminder = HumanMessage(
            content=f"<system-reminder>\n{prompt_text}\n</system-reminder>",
            additional_kwargs={"hide_from_ui": True, "goal_tracker_reminder": True},
        )
        return {"messages": [reminder]}

    @override
    async def abefore_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self.before_agent(state, runtime)
```
- **验收**: 中间件继承 `AgentMiddleware[ThreadState]`，标准钩子 `before_agent` 正确注入目标摘要，公开业务方法 `on_plan_created`/`on_subtask_completed`/`on_direction_change` 可被 PlanEngine 直接调用

### 步骤4: 实现 inject_to_prompt 输出格式
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py`
- **操作**: 续写（已在步骤3中实现）
- **验收**: 输出格式正确，包含所有字段；无快照时返回空字符串

### 步骤5: 注册中间件到中间件链
- **文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
- **操作**: 改造
- **内容**: 在 `_build_middlewares()` 函数中，通过 `custom_middlewares` 参数注入。**不要**直接修改 `_build_middlewares` 内部逻辑，而是在调用处（如 `client.py`）传入 `GoalTrackerMiddleware` 实例。
```python
from deerflow.agents.middlewares.goal_middleware import GoalTrackerMiddleware

goal_middleware = GoalTrackerMiddleware()
middlewares = _build_middlewares(
    config,
    model_name=model_name,
    agent_name=agent_name,
    custom_middlewares=[goal_middleware],
    app_config=resolved_app_config,
)
```
- **验收**: 中间件在 agent 初始化时通过 `custom_middlewares` 参数被加载，位于 `ClarificationMiddleware` 之前

## 验收标准
- [ ] GoalSnapshot / SubProblem / ProblemStatus 模型定义完成，pydantic 校验通过
- [ ] ThreadState 新增 `goal_snapshot: NotRequired[dict | None]` 字段，不破坏现有代码
- [ ] GoalTrackerMiddleware 继承 `AgentMiddleware[ThreadState]`，`before_agent` 钩子正确注入目标摘要
- [ ] `on_plan_created` / `on_subtask_completed` / `on_direction_change` 作为公开业务方法可被 PlanEngine 直接调用
- [ ] `inject_to_prompt` 输出结构化中文摘要
- [ ] 目标快照可被序列化/反序列化（dict ↔ GoalSnapshot）
- [ ] 中间件通过 `custom_middlewares` 参数注册到 `_build_middlewares()`

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | GoalSnapshot 实例化 | 所有字段正确填充 |
| 单元测试 | SubProblem 状态默认值 | status=OPEN |
| 单元测试 | inject_to_prompt 无快照 | 返回空字符串 |
| 单元测试 | inject_to_prompt 有快照 | 包含核心目标、验收标准、子问题 |
| 单元测试 | inject_to_prompt 有非目标 | 包含非目标段落 |
| 单元测试 | before_agent 注入消息 | 返回包含 `<system-reminder>` 的 HumanMessage |
| 单元测试 | before_agent 无快照 | 返回 None |
| 单元测试 | dict ↔ GoalSnapshot 序列化 | model_validate / model_dump 往返一致 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| ThreadState 改造影响现有代码 | 低 | `NotRequired[dict \| None]` 保证可选字段，默认 None |
| inject_to_prompt 输出过长 | 中 | 限制子问题摘要长度，截断 result_summary |
| Pydantic 模型误放入 TypedDict 字段 | 中 | 代码审查强制使用 dict 类型，中间件内部转换 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第5节
- `backend/packages/harness/deerflow/agents/thread_state.py` - ThreadState 定义
- `backend/packages/harness/deerflow/agents/middlewares/dynamic_context_middleware.py` - before_agent 注入模式参考
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py` - _build_middlewares 和 custom_middlewares 参数
