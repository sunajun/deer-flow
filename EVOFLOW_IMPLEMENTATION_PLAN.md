# EvoFlow 能力补齐 — 完整工程方案

> 版本：v2.0 | 日期：2026-05-22
> 基础项目：DeerFlow 2.0 (commit `253542ea`)
> 设计原则：**原生扩展 LangGraph**，不另起 DAG 引擎；**渐进式叠加**，不推倒重来
> v2.0 更新：新增 SOLO 轻量 VM 沙箱方案、任务中心/观测面、统一治理面、IM 命令对齐

---

## 目录

- [0. 总体架构增量图](#0-总体架构增量图)
- [1. 显式 DAG 编排](#1-显式-dag-编排)
- [2. 多场景系统](#2-多场景系统)
- [3. Claude Code 多会话](#3-claude-code-多会话)
- [4. 定时任务](#4-定时任务)
- [5. 核心目标/子问题状态](#5-核心目标子问题状态)
- [6. 技能/MCP 市场](#6-技能mcp-市场)
- [7. 桌面客户端 + SOLO 轻量 VM 沙箱](#7-桌面客户端--solo-轻量-vm-沙箱)
- [8. 任务中心与观测面](#8-任务中心与观测面)
- [9. 统一治理面](#9-统一治理面)
- [10. IM 渠道命令对齐](#10-im-渠道命令对齐)
- [11. 整体里程碑与依赖矩阵](#11-整体里程碑与依赖矩阵)
- [附录 A：配置增量](#附录-a配置增量)
- [附录 B：API 路由汇总](#附录-bapi-路由汇总)
- [附录 C：数据模型 ER 图](#附录-c数据模型-er-图)
- [附录 D：EvoFlow 能力覆盖最终矩阵](#附录-devoflow-能力覆盖最终矩阵)

---

## 0. 总体架构增量图

```
┌───────────────────────────────────────────────────────────────┐
│                        新增 / 改造层                           │
│                                                               │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────────┐ │
│  │ DAG Plan    │ │ Scene System │ │ Goal Tracker           │ │
│  │ (差距1)     │ │ (差距2)      │ │ (差距5)                │ │
│  └──────┬──────┘ └──────┬───────┘ └───────────┬────────────┘ │
│         │               │                      │              │
│  ┌──────┴───────────────┴──────────────────────┴────────────┐ │
│  │              中间件扩展层 (新增 5 个中间件)               │ │
│  │  PlanMiddleware │ SceneMiddleware │ GoalMiddleware       │ │
│  │  ScheduleMiddleware │ ClaudeSessionMiddleware             │ │
│  └──────────────────────────┬───────────────────────────────┘ │
│                             │                                 │
│  ┌──────────────────────────┴───────────────────────────────┐ │
│  │              DeerFlow 现有 Harness 层                     │ │
│  │  lead_agent │ subagents/executor │ 18 middlewares │ ...  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────────────┐ │
│  │ Scheduler    │ │ Skill/MCP     │ │ Desktop Client       │ │
│  │ Service      │ │ Marketplace   │ │ (Electron)           │ │
│  │ (差距4)      │ │ (差距6)       │ │ (差距7)              │ │
│  └──────────────┘ └───────────────┘ └──────────────────────┘ │
│                                                               │
│  ┌──────────────┐                                             │
│  │ Claude Code  │                                             │
│  │ Session Mgr  │                                             │
│  │ (差距3)      │                                             │
│  └──────────────┘                                             │
└───────────────────────────────────────────────────────────────┘
```

**关键设计原则**：

1. **DAG 复用 LangGraph StateGraph**：不造轮子，在 `lead_agent` 的图定义上增加 Plan/DAG 节点
2. **场景是中间件**：`SceneMiddleware` 拦截工具调用，按场景过滤
3. **目标是结构化状态**：`GoalSnapshot` 作为 LangGraph state 的子字段
4. **定时任务独立服务**：`SchedulerService` 作为 Gateway 的后台线程
5. **市场是 Registry + API**：前端浏览 → 后端下载 → `SkillInstaller` 安装

---

## 1. 显式 DAG 编排

### 1.1 设计目标

将 lead_agent 的子任务委派从"扁平并行调用"升级为"显式 DAG 调度"：
- Plan 以 DAG 形式定义子任务、依赖、闸口
- 上游完成后自动解锁下游
- 支持同步闸口（所有上游完成才继续）和异步分支
- 验收标准写入 DAG 节点，完成时校验
- 失败可局部重编排（仅重跑失败节点及其下游）

### 1.2 数据模型

```python
# backend/packages/harness/deerflow/plan/models.py

from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"        # 所有上游完成，可执行
    RUNNING = "running"
    WAITING = "waiting"    # 等待人工确认（闸口）
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BarrierType(str, Enum):
    ALL = "all"            # 所有上游完成才解锁
    ANY = "any"            # 任一上游完成即解锁
    MANUAL = "manual"      # 需人工确认后解锁


class PlanNode(BaseModel):
    """DAG 中的一个子任务节点"""
    id: str                               # 唯一标识，如 "node_1"
    title: str                            # 子任务标题
    description: str                      # 子任务描述
    assignee: str = "general-purpose"     # 子代理类型
    dependencies: list[str] = Field(default_factory=list)  # 依赖的上游节点 ID
    barrier_type: BarrierType = BarrierType.ALL
    acceptance_criteria: list[str] = Field(default_factory=list)  # 验收标准
    context_from: list[str] = Field(default_factory=list)  # 从哪些上游节点继承上下文
    status: NodeStatus = NodeStatus.PENDING
    result: Any | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # 子代理配置
    subagent_config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 900  # 默认 15 分钟


class PlanDAG(BaseModel):
    """完整的 Plan DAG"""
    plan_id: str
    title: str
    description: str
    goal: str                              # 核心目标
    acceptance_criteria: list[str]         # 全局验收标准
    nodes: dict[str, PlanNode] = Field(default_factory=dict)
    edges: list[tuple[str, str]] = Field(default_factory=list)  # (from_id, to_id)
    status: NodeStatus = NodeStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_ready_nodes(self) -> list[PlanNode]:
        """获取当前可执行的节点（所有上游已完成）"""
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = [self.nodes[dep_id] for dep_id in node.dependencies if dep_id in self.nodes]
            if not deps:
                ready.append(node)
                continue
            if node.barrier_type == BarrierType.ALL:
                if all(d.status == NodeStatus.COMPLETED for d in deps):
                    ready.append(node)
            elif node.barrier_type == BarrierType.ANY:
                if any(d.status == NodeStatus.COMPLETED for d in deps):
                    ready.append(node)
            elif node.barrier_type == BarrierType.MANUAL:
                # 人工闸口需要外部确认
                if all(d.status == NodeStatus.COMPLETED for d in deps):
                    node.status = NodeStatus.WAITING
        return ready

    def is_complete(self) -> bool:
        return all(n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED)
                   for n in self.nodes.values())

    def get_failed_nodes(self) -> list[PlanNode]:
        return [n for n in self.nodes.values() if n.status == NodeStatus.FAILED]
```

### 1.3 LangGraph 状态扩展

在现有 LangGraph state 中新增 `plan` 字段：

```python
# backend/packages/harness/deerflow/agents/lead_agent/state.py (改造)

from deerflow.plan.models import PlanDAG

# 在现有 State 定义中新增
class AgentState(TypedDict, total=False):
    # ... 现有字段 ...
    plan: PlanDAG | None               # 新增：当前 Plan DAG
    plan_approved: bool                 # 新增：Plan 是否已确认
    active_node_ids: list[str]          # 新增：当前正在执行的节点
```

### 1.4 LangGraph 图扩展

在 lead_agent 的 StateGraph 中新增 DAG 调度节点：

```python
# backend/packages/harness/deerflow/agents/lead_agent/agent.py (改造)

from deerflow.plan.engine import PlanEngine

def build_agent_graph():
    graph = StateGraph(AgentState)

    # 现有节点 ...
    graph.add_node("plan_create", plan_create_node)
    graph.add_node("plan_execute_dag", plan_execute_dag_node)  # 新增
    graph.add_node("plan_supervise", plan_supervise_node)       # 新增
    graph.add_node("plan_reorchestrate", plan_reorchestrate_node)  # 新增

    # 新增边
    graph.add_conditional_edges(
        "plan_create",
        lambda s: "plan_execute_dag" if s.get("plan_approved") else "agent",
    )
    graph.add_conditional_edges(
        "plan_execute_dag",
        lambda s: (
            "plan_reorchestrate" if s["plan"].get_failed_nodes()
            else "plan_supervise" if not s["plan"].is_complete()
            else "agent"
        ),
    )
    graph.add_edge("plan_supervise", "plan_execute_dag")
    graph.add_conditional_edges(
        "plan_reorchestrate",
        lambda s: "plan_execute_dag" if s.get("plan_revised") else "agent",
    )
    return graph


async def plan_create_node(state: AgentState) -> dict:
    """总控生成 Plan DAG，等待用户确认"""
    # LLM 生成 PlanDAG 结构化输出
    plan = await PlanEngine.create_from_intent(state["messages"])
    return {"plan": plan, "plan_approved": False}


async def plan_execute_dag_node(state: AgentState) -> dict:
    """执行 DAG 中就绪的节点（并行派发子代理）"""
    plan = state["plan"]
    ready_nodes = plan.get_ready_nodes()
    # 并行派发子代理
    tasks = []
    for node in ready_nodes:
        node.status = NodeStatus.RUNNING
        node.started_at = datetime.now()
        # 构造子代理上下文：从 context_from 指定的上游节点继承结果
        context = _build_subagent_context(plan, node)
        tasks.append(_dispatch_subagent(node, context, state))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 处理结果
    for node, result in zip(ready_nodes, results):
        if isinstance(result, Exception):
            node.status = NodeStatus.FAILED
            node.error = str(result)
        else:
            node.status = NodeStatus.COMPLETED
            node.result = result
            node.completed_at = datetime.now()
    plan.updated_at = datetime.now()
    return {"plan": plan}


async def plan_supervise_node(state: AgentState) -> dict:
    """监督：检查进度、更新目标快照、判断是否需要再对齐"""
    plan = state["plan"]
    # 检查验收标准
    for node in plan.nodes.values():
        if node.status == NodeStatus.COMPLETED and node.acceptance_criteria:
            passed = await PlanEngine.verify_acceptance(node)
            if not passed:
                node.status = NodeStatus.FAILED
                node.error = "验收标准未通过"
    return {"plan": plan}


async def plan_reorchestrate_node(state: AgentState) -> dict:
    """局部重编排：仅调整失败节点及其下游"""
    plan = state["plan"]
    failed = plan.get_failed_nodes()
    # LLM 决策：重试 / 跳过 / 拆分 / 替换子代理
    revised = await PlanEngine.reorchestrate(plan, failed)
    return {"plan": revised, "plan_revised": True}
```

### 1.5 PlanEngine 核心类

```python
# backend/packages/harness/deerflow/plan/engine.py

from deerflow.plan.models import PlanDAG, PlanNode, NodeStatus
from langchain_core.language_models import BaseChatModel


class PlanEngine:
    """Plan DAG 的创建、校验、重编排引擎"""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    @staticmethod
    async def create_from_intent(messages: list) -> PlanDAG:
        """从用户意图生成 PlanDAG（LLM 结构化输出）"""
        # 使用 LLM with_structured_output(PlanDAG) 生成
        ...

    @staticmethod
    async def verify_acceptance(node: PlanNode) -> bool:
        """校验节点结果是否满足验收标准"""
        ...

    @staticmethod
    async def reorchestrate(plan: PlanDAG, failed_nodes: list[PlanNode]) -> PlanDAG:
        """局部重编排：仅调整失败节点及其下游"""
        # 1. 标记失败节点的下游为 PENDING（重置）
        # 2. LLM 决策对失败节点的处理（重试/拆分/换代理）
        # 3. 更新 DAG
        ...
```

### 1.6 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/plan/__init__.py` | 模块入口 |
| `backend/packages/harness/deerflow/plan/models.py` | PlanDAG / PlanNode 数据模型 |
| `backend/packages/harness/deerflow/plan/engine.py` | PlanEngine 核心逻辑 |
| `backend/packages/harness/deerflow/plan/nodes.py` | LangGraph 图节点实现 |
| `backend/packages/harness/deerflow/plan/verification.py` | 验收校验 |
| `backend/app/gateway/routers/plans.py` | Plan CRUD API |
| `backend/tests/test_plan_dag.py` | DAG 拓扑测试 |
| `backend/tests/test_plan_engine.py` | Engine 集成测试 |

### 1.7 API 设计

```
POST   /api/plans                    创建 Plan
GET    /api/plans/{plan_id}          获取 Plan 状态
POST   /api/plans/{plan_id}/approve  确认 Plan
POST   /api/plans/{plan_id}/nodes/{node_id}/retry   重试失败节点
POST   /api/plans/{plan_id}/reorchestrate  触发局部重编排
GET    /api/plans/{plan_id}/progress  获取执行进度（SSE）
```

### 1.8 配置项

```yaml
# config.yaml 新增
plan:
  enabled: true
  max_parallel_nodes: 3          # DAG 并行节点上限
  default_timeout: 900           # 节点默认超时（秒）
  auto_approve: false            # 是否自动确认 Plan
  acceptance_verification: true  # 是否启用验收校验
  reorchestrate_max_retries: 2   # 重编排最大次数
```

### 1.9 测试策略

| 测试类型 | 覆盖点 |
|---------|--------|
| 单元测试 | PlanDAG 拓扑排序、get_ready_nodes、is_complete、get_failed_nodes |
| 单元测试 | PlanEngine.create_from_intent mock LLM 输出 |
| 集成测试 | DAG 节点并行执行 + 结果传递 |
| 集成测试 | 失败节点重编排流程 |
| E2E 测试 | 完整 Plan → 确认 → 执行 → 验收 → 完成 |
| 边界测试 | 空图、环形依赖、全部失败、闸口等待 |

### 1.10 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + PlanEngine 骨架 + DAG 拓扑测试 | 3 天 |
| P2 | LangGraph 图节点 + 子代理并行派发 | 4 天 |
| P3 | 验收校验 + 重编排 + API | 3 天 |
| P4 | 集成测试 + E2E + 文档 | 2 天 |

**合计：12 天（2.5 周）**

---

## 2. 多场景系统

### 2.1 设计目标

- 定义多种工作场景（对话、规划、文件操作、联网检索、治理、自动化、进化）
- 每种场景限定可用工具集和权限策略
- 多场景可叠加（工具取并集）
- 闲聊时自动淡化过期场景
- 与 Plan 模式联动（进入规划场景 → 自动开启 plan_mode）

### 2.2 数据模型

```python
# backend/packages/harness/deerflow/scene/models.py

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class SceneType(str, Enum):
    CONVERSATION = "conversation"      # 默认对话
    PLANNING = "planning"              # 规划（只读，不写盘）
    FILE_OPERATION = "file_operation"  # 文件读写/命令执行
    WEB_SEARCH = "web_search"          # 联网检索
    GOVERNANCE = "governance"          # 治理/智能体管理/技能管理
    AUTOMATION = "automation"          # 定时任务/自动化
    SANDBOX_RUNTIME = "sandbox"        # 特定运行时


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL = "full"


class ToolGroup(BaseModel):
    """工具分组定义"""
    name: str
    tool_ids: list[str]               # 该分组包含的工具 ID
    permission: PermissionLevel = PermissionLevel.READ_ONLY


class Scene(BaseModel):
    """工作场景定义"""
    type: SceneType
    name: str
    description: str
    tool_groups: list[ToolGroup]       # 该场景可用的工具分组
    auto_deactivate_after: int = 300   # 自动淡化时间（秒），0=不自动淡化
    activates_plan_mode: bool = False  # 进入此场景是否自动开启 plan_mode
    priority: int = 0                  # 场景优先级（冲突时高优先级场景的工具权限生效）


class SceneState(BaseModel):
    """当前线程的场景状态"""
    active_scenes: list[SceneType] = Field(default_factory=lambda: [SceneType.CONVERSATION])
    scene_history: list[dict] = Field(default_factory=list)  # 场景切换历史
    last_activity: dict[SceneType, float] = Field(default_factory=dict)  # 最后活跃时间
```

### 2.3 场景注册表

```python
# backend/packages/harness/deerflow/scene/registry.py

from deerflow.scene.models import Scene, SceneType, ToolGroup, PermissionLevel

BUILTIN_SCENES: dict[SceneType, Scene] = {
    SceneType.CONVERSATION: Scene(
        type=SceneType.CONVERSATION,
        name="对话",
        description="默认聊天模式，仅核心工具",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
        ],
        auto_deactivate_after=0,
        activates_plan_mode=False,
        priority=0,
    ),
    SceneType.PLANNING: Scene(
        type=SceneType.PLANNING,
        name="规划",
        description="只读摸底，不做生产变更",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="search", tool_ids=["tavily_search", "jina_reader", "web_search"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="read_only_file", tool_ids=["read_file", "ls", "glob", "grep"], permission=PermissionLevel.READ_ONLY),
        ],
        auto_deactivate_after=600,
        activates_plan_mode=True,
        priority=10,
    ),
    SceneType.FILE_OPERATION: Scene(
        type=SceneType.FILE_OPERATION,
        name="文件操作",
        description="读写文件与命令执行",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.FULL),
            ToolGroup(name="file", tool_ids=["read_file", "write_file", "str_replace", "ls", "glob", "grep", "bash"], permission=PermissionLevel.READ_WRITE),
        ],
        auto_deactivate_after=300,
        activates_plan_mode=False,
        priority=5,
    ),
    SceneType.WEB_SEARCH: Scene(
        type=SceneType.WEB_SEARCH,
        name="联网检索",
        description="外部检索与网页信息",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="search", tool_ids=["tavily_search", "jina_reader", "web_search", "firecrawl"], permission=PermissionLevel.READ_ONLY),
        ],
        auto_deactivate_after=300,
        activates_plan_mode=False,
        priority=3,
    ),
    SceneType.GOVERNANCE: Scene(
        type=SceneType.GOVERNANCE,
        name="治理",
        description="智能体管理、技能管理、智能体进化",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="governance", tool_ids=["agent_manage", "skill_manage", "scene_switch", "schedule_manage"], permission=PermissionLevel.READ_WRITE),
        ],
        auto_deactivate_after=600,
        activates_plan_mode=False,
        priority=8,
    ),
    SceneType.AUTOMATION: Scene(
        type=SceneType.AUTOMATION,
        name="自动化",
        description="定时任务、持续运行",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="automation", tool_ids=["schedule_manage", "schedule_run"], permission=PermissionLevel.READ_WRITE),
        ],
        auto_deactivate_after=600,
        activates_plan_mode=False,
        priority=6,
    ),
    SceneType.SANDBOX_RUNTIME: Scene(
        type=SceneType.SANDBOX_RUNTIME,
        name="沙箱运行时",
        description="独立执行环境",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify"], permission=PermissionLevel.FULL),
            ToolGroup(name="file", tool_ids=["read_file", "write_file", "str_replace", "ls", "glob", "grep", "bash"], permission=PermissionLevel.FULL),
        ],
        auto_deactivate_after=0,
        activates_plan_mode=False,
        priority=1,
    ),
}
```

### 2.4 SceneMiddleware 中间件

```python
# backend/packages/harness/deerflow/agents/middlewares/scene_middleware.py

from deerflow.scene.models import SceneState, SceneType
from deerflow.scene.registry import BUILTIN_SCENES


class SceneMiddleware:
    """场景中间件：拦截工具调用，按场景过滤可用工具"""

    async def on_tool_call(self, state: dict, tool_call: dict) -> dict | None:
        scene_state = state.get("scene_state", SceneState())
        allowed_tools = self._get_allowed_tools(scene_state)
        if tool_call["name"] not in allowed_tools:
            return {
                "tool_call_rejected": True,
                "reason": f"工具 '{tool_call['name']}' 在当前场景 {scene_state.active_scenes} 中不可用。"
                          f"可用工具：{allowed_tools}"
            }
        return None  # 放行

    def _get_allowed_tools(self, scene_state: SceneState) -> set[str]:
        """多场景叠加：工具取并集，权限取最高"""
        allowed = set()
        for scene_type in scene_state.active_scenes:
            scene = BUILTIN_SCENES.get(scene_type)
            if not scene:
                continue
            for group in scene.tool_groups:
                allowed.update(group.tool_ids)
        return allowed

    async def on_message(self, state: dict, message: dict) -> dict:
        """检测用户意图，自动切换场景"""
        # 通过关键词或 LLM 判断意图
        # 如"帮我搜索"→ 激活 WEB_SEARCH
        # 如"修改文件"→ 激活 FILE_OPERATION
        ...

    async def auto_deactivate(self, scene_state: SceneState) -> SceneState:
        """自动淡化过期场景"""
        import time
        now = time.time()
        to_remove = []
        for scene_type in scene_state.active_scenes:
            if scene_type == SceneType.CONVERSATION:
                continue
            scene = BUILTIN_SCENES[scene_type]
            if scene.auto_deactivate_after == 0:
                continue
            last = scene_state.last_activity.get(scene_type, 0)
            if now - last > scene.auto_deactivate_after:
                to_remove.append(scene_type)
        for s in to_remove:
            scene_state.active_scenes.remove(s)
        return scene_state
```

### 2.5 新增工具：场景切换

```python
# backend/packages/harness/deerflow/tools/scene_tools.py

from langchain_core.tools import tool


@tool
def activate_scene(scene_type: str) -> str:
    """激活工作场景。可用场景：conversation, planning, file_operation, web_search, governance, automation, sandbox"""
    ...


@tool
def deactivate_scene(scene_type: str) -> str:
    """退出工作场景"""
    ...


@tool
def list_active_scenes() -> str:
    """列出当前活跃场景及其可用工具"""
    ...
```

### 2.6 改造点：工具装配

```python
# backend/packages/harness/deerflow/tools/__init__.py (改造)

def get_available_tools(state: dict) -> list:
    """改造：工具装配加入场景过滤"""
    all_tools = _assemble_all_tools(state)  # 现有逻辑

    # 新增：场景过滤
    scene_state = state.get("scene_state")
    if scene_state:
        allowed = SceneMiddleware()._get_allowed_tools(scene_state)
        all_tools = [t for t in all_tools if t.name in allowed]

    return all_tools
```

### 2.7 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/scene/__init__.py` | 模块入口 |
| `backend/packages/harness/deerflow/scene/models.py` | Scene / SceneState 数据模型 |
| `backend/packages/harness/deerflow/scene/registry.py` | 内置场景注册表 |
| `backend/packages/harness/deerflow/agents/middlewares/scene_middleware.py` | 场景中间件 |
| `backend/packages/harness/deerflow/tools/scene_tools.py` | 场景切换工具 |
| `backend/tests/test_scene.py` | 场景过滤/叠加/淡化测试 |

### 2.8 配置项

```yaml
# config.yaml 新增
scenes:
  enabled: true
  auto_deactivate: true          # 是否启用自动淡化
  default_scene: conversation    # 默认场景
  custom_scenes: []              # 用户自定义场景
```

### 2.9 测试策略

| 测试类型 | 覆盖点 |
|---------|--------|
| 单元测试 | 场景过滤：单场景/多场景叠加/权限取最高 |
| 单元测试 | 自动淡化：超时场景移除，conversation 不移除 |
| 集成测试 | 工具装配与场景联动 |
| E2E 测试 | 用户切换场景 → 工具可用性变化 |

### 2.10 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + 注册表 + 场景过滤 | 3 天 |
| P2 | SceneMiddleware + 自动淡化 + 意图检测 | 3 天 |
| P3 | 工具装配改造 + API + 测试 | 3 天 |

**合计：9 天（2 周）**

---

## 3. Claude Code 多会话

### 3.1 设计目标

- 支持多个 Claude Code 会话并行作为子代理
- 会话可续接（同一会话多轮往返）
- 编排侧下达与收口
- 输出流回传，在桌面端控制台近实时展示

### 3.2 数据模型

```python
# backend/packages/harness/deerflow/claude_session/models.py

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ClaudeSession(BaseModel):
    """一个 Claude Code 会话"""
    session_id: str
    thread_id: str                       # 所属 DeerFlow 线程
    parent_node_id: str | None = None    # 所属 DAG 节点（如果有）
    status: SessionStatus = SessionStatus.IDLE
    working_directory: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_active_at: datetime = Field(default_factory=datetime.now)
    message_count: int = 0
    # 会话上下文
    system_prompt_suffix: str = ""       # 追加到 Claude Code 的额外指令
    tool_permissions: list[str] = Field(default_factory=list)  # 允许的工具


class SessionMessage(BaseModel):
    """会话中的一条消息"""
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class ClaudeSessionPool(BaseModel):
    """线程级别的 Claude Code 会话池"""
    thread_id: str
    sessions: dict[str, ClaudeSession] = Field(default_factory=dict)
    max_parallel: int = 3               # 最大并行会话数
```

### 3.3 ClaudeSessionManager

```python
# backend/packages/harness/deerflow/claude_session/manager.py

import asyncio
from deerflow.claude_session.models import ClaudeSession, ClaudeSessionPool, SessionStatus


class ClaudeSessionManager:
    """Claude Code 多会话管理器"""

    def __init__(self, max_parallel: int = 3):
        self.pools: dict[str, ClaudeSessionPool] = {}  # thread_id → pool
        self.max_parallel = max_parallel
        self._output_streams: dict[str, asyncio.Queue] = {}  # session_id → output queue

    async def create_session(
        self,
        thread_id: str,
        working_directory: str | None = None,
        parent_node_id: str | None = None,
        system_prompt_suffix: str = "",
    ) -> ClaudeSession:
        """创建新的 Claude Code 会话"""
        pool = self.pools.setdefault(thread_id, ClaudeSessionPool(thread_id=thread_id))
        active_count = sum(1 for s in pool.sessions.values() if s.status == SessionStatus.RUNNING)
        if active_count >= self.max_parallel:
            raise RuntimeError(f"已达到最大并行会话数 {self.max_parallel}")
        session = ClaudeSession(
            thread_id=thread_id,
            working_directory=working_directory,
            parent_node_id=parent_node_id,
            system_prompt_suffix=system_prompt_suffix,
        )
        pool.sessions[session.session_id] = session
        self._output_streams[session.session_id] = asyncio.Queue()
        return session

    async def send_message(self, session_id: str, message: str) -> None:
        """向指定会话发送消息"""
        session = self._get_session(session_id)
        session.status = SessionStatus.RUNNING
        session.last_active_at = datetime.now()
        session.message_count += 1
        # 通过 ACP 协议发送给 Claude Code 进程
        await self._dispatch_to_claude(session, message)

    async def get_output_stream(self, session_id: str) -> asyncio.Queue:
        """获取会话输出流"""
        return self._output_streams[session_id]

    async def continue_session(self, session_id: str, message: str) -> None:
        """续接已有会话（而非新建）"""
        await self.send_message(session_id, message)

    async def terminate_session(self, session_id: str) -> None:
        """终止会话"""
        session = self._get_session(session_id)
        session.status = SessionStatus.COMPLETED
        # 清理 ACP 连接

    async def pause_session(self, session_id: str) -> None:
        session = self._get_session(session_id)
        session.status = SessionStatus.PAUSED

    async def resume_session(self, session_id: str) -> None:
        session = self._get_session(session_id)
        session.status = SessionStatus.RUNNING

    def _get_session(self, session_id: str) -> ClaudeSession:
        for pool in self.pools.values():
            if session_id in pool.sessions:
                return pool.sessions[session_id]
        raise KeyError(f"Session {session_id} not found")

    async def _dispatch_to_claude(self, session: ClaudeSession, message: str):
        """通过 ACP 协议与 Claude Code 进程通信"""
        # 复用现有 ACP agent 的通信机制
        # 新增：输出流写入 _output_streams[session.session_id]
        ...
```

### 3.4 新增 LangGraph 工具

```python
# backend/packages/harness/deerflow/tools/claude_session_tools.py

@tool
async def claude_code_task(
    task_description: str,
    session_id: str | None = None,  # None=新建会话，否则续接
    working_directory: str | None = None,
) -> str:
    """委派任务给 Claude Code。可续接已有会话或创建新会话。"""
    ...


@tool
async def list_claude_sessions() -> str:
    """列出当前线程的所有 Claude Code 会话及状态"""
    ...


@tool
async def terminate_claude_session(session_id: str) -> str:
    """终止指定 Claude Code 会话"""
    ...
```

### 3.5 输出流 SSE 推送

```python
# backend/app/gateway/routers/claude_sessions.py

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/claude-sessions", tags=["claude-sessions"])


@router.get("/{session_id}/stream")
async def stream_session_output(session_id: str):
    """SSE 流式推送 Claude Code 会话输出"""
    manager = get_session_manager()
    queue = await manager.get_output_stream(session_id)

    async def event_generator():
        while True:
            output = await queue.get()
            if output is None:  # 会话结束
                break
            yield {"event": "claude_output", "data": output}

    return EventSourceResponse(event_generator())
```

### 3.6 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/claude_session/__init__.py` | 模块入口 |
| `backend/packages/harness/deerflow/claude_session/models.py` | 数据模型 |
| `backend/packages/harness/deerflow/claude_session/manager.py` | 会话管理器 |
| `backend/packages/harness/deerflow/tools/claude_session_tools.py` | LangGraph 工具 |
| `backend/app/gateway/routers/claude_sessions.py` | API 路由 |
| `backend/tests/test_claude_session.py` | 会话管理测试 |

### 3.7 配置项

```yaml
# config.yaml 新增
claude_sessions:
  enabled: true
  max_parallel: 3               # 每线程最大并行会话
  default_timeout: 3600         # 会话默认超时（秒）
  auto_terminate_idle: 1800     # 空闲自动终止（秒）
  working_directory: null       # 默认工作目录
```

### 3.8 测试策略

| 测试类型 | 覆盖点 |
|---------|--------|
| 单元测试 | 会话创建/续接/终止/并行上限 |
| 集成测试 | ACP 通信 + 输出流 |
| E2E 测试 | 多会话并行委派 + 结果汇总 |

### 3.9 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + SessionManager 骨架 | 3 天 |
| P2 | ACP 通信适配 + 输出流 | 4 天 |
| P3 | LangGraph 工具 + API + 测试 | 3 天 |

**合计：10 天（2 周）**

---

## 4. 定时任务

### 4.1 设计目标

- 用户可创建 cron 定时任务
- 到期触发时创建独立 thread 执行
- 可配置是否走编排运行时
- 支持结果推送到飞书等 IM 渠道
- 支持暂停/恢复/终止

### 4.2 数据模型

```python
# backend/packages/harness/deerflow/scheduler/models.py

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ScheduleTrigger(BaseModel):
    """触发规则"""
    cron: str                             # cron 表达式，如 "0 9 * * 1-5"（工作日 9 点）
    timezone: str = "Asia/Shanghai"
    # 或者简单周期
    interval_seconds: int | None = None   # 固定间隔（秒），与 cron 二选一


class ScheduleNotification(BaseModel):
    """推送配置"""
    enabled: bool = False
    channel: str = "feishu"               # feishu / slack / telegram / dingtalk
    target: str = ""                      # 群 ID / 用户 ID
    include_summary: bool = True          # 是否包含执行摘要
    include_full_output: bool = False     # 是否包含完整输出


class ScheduledTask(BaseModel):
    """定时任务"""
    task_id: str
    name: str
    description: str
    prompt: str                           # 触发时的提示词
    trigger: ScheduleTrigger
    notification: ScheduleNotification = Field(default_factory=ScheduleNotification)
    use_orchestration: bool = False       # 是否走编排运行时（Plan DAG）
    reuse_thread: bool = False            # 是否复用同一会话
    thread_id: str | None = None          # 复用时的线程 ID
    timeout_seconds: int = 3600           # 执行超时
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ScheduleRun(BaseModel):
    """一次调度执行的记录"""
    run_id: str
    task_id: str
    thread_id: str                        # 执行时创建的线程
    status: str                           # pending / running / completed / failed
    started_at: datetime
    completed_at: datetime | None = None
    result_summary: str | None = None
    error: str | None = None
```

### 4.3 SchedulerService

```python
# backend/packages/harness/deerflow/scheduler/service.py

import asyncio
from croniter import croniter
from datetime import datetime, timezone
from deerflow.scheduler.models import ScheduledTask, ScheduleStatus, ScheduleRun


class SchedulerService:
    """定时任务调度服务，作为 Gateway 后台线程运行"""

    def __init__(self):
        self.tasks: dict[str, ScheduledTask] = {}
        self.runs: list[ScheduleRun] = []
        self._running = False

    async def start(self):
        """启动调度循环"""
        self._running = True
        while self._running:
            await self._tick()
            await asyncio.sleep(60)  # 每分钟检查一次

    async def stop(self):
        self._running = False

    async def _tick(self):
        now = datetime.now(timezone.utc)
        for task in self.tasks.values():
            if task.status != ScheduleStatus.ACTIVE:
                continue
            if self._should_trigger(task, now):
                await self._execute(task)

    def _should_trigger(self, task: ScheduledTask, now: datetime) -> bool:
        if task.trigger.cron:
            cron = croniter(task.trigger.cron, now)
            return cron.get_next(datetime) <= now
        elif task.trigger.interval_seconds:
            if task.last_run_at is None:
                return True
            elapsed = (now - task.last_run_at).total_seconds()
            return elapsed >= task.trigger.interval_seconds
        return False

    async def _execute(self, task: ScheduledTask):
        """触发执行"""
        run = ScheduleRun(
            run_id=f"run_{task.task_id}_{int(datetime.now().timestamp())}",
            task_id=task.task_id,
            thread_id="",  # 执行时创建
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        # 创建新线程或复用
        if task.reuse_thread and task.thread_id:
            run.thread_id = task.thread_id
        else:
            run.thread_id = await self._create_thread(task.prompt)

        # 发送消息
        await self._send_message(run.thread_id, task.prompt)

        task.last_run_at = datetime.now(timezone.utc)
        task.run_count += 1
        self.runs.append(run)

        # 异步等待结果 + 推送
        asyncio.create_task(self._wait_and_notify(task, run))

    async def _wait_and_notify(self, task: ScheduledTask, run: ScheduleRun):
        """等待执行完成并推送通知"""
        # 轮询线程状态直到完成或超时
        ...
        if task.notification.enabled:
            await self._send_notification(task, run)

    async def _send_notification(self, task: ScheduledTask, run: ScheduleRun):
        """推送到 IM 渠道"""
        from deerflow.channels import get_channel_manager
        manager = get_channel_manager()
        await manager.send_message(
            channel=task.notification.channel,
            target=task.notification.target,
            message=run.result_summary or "任务执行完成",
        )

    # CRUD 操作
    async def create_task(self, task: ScheduledTask) -> ScheduledTask: ...
    async def update_task(self, task_id: str, updates: dict) -> ScheduledTask: ...
    async def delete_task(self, task_id: str) -> None: ...
    async def pause_task(self, task_id: str) -> None: ...
    async def resume_task(self, task_id: str) -> None: ...
    async def list_tasks(self) -> list[ScheduledTask]: ...
    async def get_runs(self, task_id: str) -> list[ScheduleRun]: ...
```

### 4.4 API 设计

```
POST   /api/schedules                    创建定时任务
GET    /api/schedules                    列出所有定时任务
GET    /api/schedules/{task_id}          获取任务详情
PUT    /api/schedules/{task_id}          更新任务
DELETE /api/schedules/{task_id}          删除任务
POST   /api/schedules/{task_id}/pause    暂停
POST   /api/schedules/{task_id}/resume   恢复
POST   /api/schedules/{task_id}/trigger  手动触发
GET    /api/schedules/{task_id}/runs     获取执行记录
```

### 4.5 Gateway 启动集成

```python
# backend/app/gateway/app.py (改造)

from deerflow.scheduler.service import SchedulerService

scheduler = SchedulerService()

@app.on_event("startup")
async def startup():
    # ... 现有启动逻辑 ...
    asyncio.create_task(scheduler.start())

@app.on_event("shutdown")
async def shutdown():
    await scheduler.stop()
```

### 4.6 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/scheduler/__init__.py` | 模块入口 |
| `backend/packages/harness/deerflow/scheduler/models.py` | 数据模型 |
| `backend/packages/harness/deerflow/scheduler/service.py` | 调度服务 |
| `backend/app/gateway/routers/schedules.py` | API 路由 |
| `backend/tests/test_scheduler.py` | 调度测试 |

### 4.7 配置项

```yaml
# config.yaml 新增
scheduler:
  enabled: true
  tick_interval: 60             # 扫描间隔（秒）
  max_concurrent_runs: 5        # 最大并发执行数
  default_timeout: 3600         # 默认超时（秒）
  persist_to_db: true           # 是否持久化到数据库
  notification_channels:        # 支持推送的渠道
    - feishu
    - slack
    - dingtalk
```

### 4.8 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + Service + cron 调度 | 3 天 |
| P2 | 执行触发 + IM 推送 + API | 3 天 |
| P3 | 持久化 + 测试 | 2 天 |

**合计：8 天（1.5 周）**

---

## 5. 核心目标/子问题状态

### 5.1 设计目标

- 总控持有结构化的"核心目标 + 子问题 + 验收标准"
- 每轮对话注入 system prompt，确保对齐
- 方向变更时触发再对齐
- 快照回注后续回合

### 5.2 数据模型

```python
# backend/packages/harness/deerflow/goal/models.py

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class ProblemStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    DROPPED = "dropped"


class SubProblem(BaseModel):
    """子问题"""
    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    status: ProblemStatus = ProblemStatus.OPEN
    assigned_to: str | None = None  # 子代理类型或 DAG 节点 ID
    result_summary: str | None = None
    blockers: list[str] = Field(default_factory=list)


class GoalSnapshot(BaseModel):
    """核心目标快照，每轮对话前注入 system prompt"""
    goal_id: str
    core_goal: str                          # 核心目标（一句话）
    non_goals: list[str] = Field(default_factory=list)  # 明确不是目标的
    acceptance_criteria: list[str]          # 全局验收标准
    sub_problems: list[SubProblem] = Field(default_factory=list)
    current_focus: str | None = None        # 当前聚焦的子问题 ID
    alignment_version: int = 1              # 对齐版本号，每次再对齐 +1
    last_aligned_at: datetime = Field(default_factory=datetime.now)
    direction_changes: list[dict] = Field(default_factory=list)  # 方向变更记录


class GoalSnapshotMiddleware:
    """目标快照中间件：在每轮对话前注入目标到 system prompt"""
```

### 5.3 GoalTrackerMiddleware

```python
# backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py

from deerflow.goal.models import GoalSnapshot, SubProblem, ProblemStatus


class GoalTrackerMiddleware:
    """目标追踪中间件"""

    async def on_plan_created(self, state: dict, plan) -> dict:
        """Plan 创建时，从 Plan 生成 GoalSnapshot"""
        snapshot = GoalSnapshot(
            goal_id=f"goal_{plan.plan_id}",
            core_goal=plan.goal,
            non_goals=[],  # LLM 提取
            acceptance_criteria=plan.acceptance_criteria,
            sub_problems=[
                SubProblem(
                    id=f"sub_{node.id}",
                    title=node.title,
                    description=node.description,
                    acceptance_criteria=node.acceptance_criteria,
                    assigned_to=node.assignee,
                )
                for node in plan.nodes.values()
            ],
        )
        return {"goal_snapshot": snapshot}

    async def on_subtask_completed(self, state: dict, node_id: str, result) -> dict:
        """子任务完成时，更新子问题状态"""
        snapshot: GoalSnapshot = state["goal_snapshot"]
        for sub in snapshot.sub_problems:
            if sub.id == f"sub_{node_id}":
                sub.status = ProblemStatus.RESOLVED
                sub.result_summary = str(result)[:500]
                break
        return {"goal_snapshot": snapshot}

    async def on_direction_change(self, state: dict, new_direction: str) -> dict:
        """方向变更时触发再对齐"""
        snapshot: GoalSnapshot = state["goal_snapshot"]
        snapshot.direction_changes.append({
            "from": snapshot.core_goal,
            "to": new_direction,
            "at": datetime.now().isoformat(),
        })
        snapshot.core_goal = new_direction
        snapshot.alignment_version += 1
        snapshot.last_aligned_at = datetime.now()
        # 重置未完成的子问题状态
        for sub in snapshot.sub_problems:
            if sub.status not in (ProblemStatus.RESOLVED, ProblemStatus.DROPPED):
                sub.status = ProblemStatus.OPEN
        return {"goal_snapshot": snapshot}

    async def inject_to_prompt(self, state: dict) -> str:
        """生成注入 system prompt 的目标摘要文本"""
        snapshot: GoalSnapshot = state.get("goal_snapshot")
        if not snapshot:
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
```

### 5.4 LangGraph state 扩展

```python
# 在 AgentState 中新增
class AgentState(TypedDict, total=False):
    # ... 现有字段 ...
    goal_snapshot: GoalSnapshot | None    # 新增
```

### 5.5 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/goal/__init__.py` | 模块入口 |
| `backend/packages/harness/deerflow/goal/models.py` | GoalSnapshot 数据模型 |
| `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py` | 目标追踪中间件 |
| `backend/tests/test_goal_tracker.py` | 测试 |

### 5.6 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + 中间件 + prompt 注入 | 2 天 |
| P2 | 方向变更再对齐 + 测试 | 2 天 |

**合计：4 天（1 周）**

---

## 6. 技能/MCP 市场

### 6.1 设计目标

- 提供技能和 MCP 的在线浏览、搜索、安装
- 安装后自动注册到 `extensions_config.json`
- 支持版本管理和更新检查
- 市场后端可自建或对接 GitHub Registry

### 6.2 数据模型

```python
# backend/packages/harness/deerflow/marketplace/models.py

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class PackageType(str, Enum):
    SKILL = "skill"
    MCP = "mcp"


class PackageVersion(BaseModel):
    """包版本"""
    version: str
    description: str
    changelog: str = ""
    released_at: datetime
    download_url: str
    sha256: str = ""


class MarketplacePackage(BaseModel):
    """市场中的技能或 MCP 包"""
    package_id: str
    name: str
    type: PackageType
    description: str
    author: str
    homepage: str = ""
    tags: list[str] = Field(default_factory=list)
    latest_version: str = ""
    versions: list[PackageVersion] = Field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    installed: bool = False
    installed_version: str | None = None


class InstallRequest(BaseModel):
    package_id: str
    version: str | None = None  # None = 最新版
    type: PackageType


class SearchResult(BaseModel):
    packages: list[MarketplacePackage]
    total: int
    page: int
    page_size: int
```

### 6.3 MarketplaceRegistry

```python
# backend/packages/harness/deerflow/marketplace/registry.py

from deerflow.marketplace.models import MarketplacePackage, PackageType, SearchResult


class MarketplaceRegistry:
    """市场注册中心，对接远程仓库"""

    def __init__(self, registry_url: str = "https://registry.deerflow.tech"):
        self.registry_url = registry_url

    async def search(self, query: str, package_type: PackageType | None = None,
                     page: int = 1, page_size: int = 20) -> SearchResult:
        """搜索包"""
        # 调用远程 registry API
        ...

    async def get_package(self, package_id: str) -> MarketplacePackage:
        """获取包详情"""
        ...

    async def download(self, package_id: str, version: str | None = None) -> str:
        """下载包到临时目录，返回本地路径"""
        ...

    async def check_updates(self, installed_packages: list[dict]) -> list[dict]:
        """检查已安装包的更新"""
        ...
```

### 6.4 安装流程对接

```python
# backend/packages/harness/deerflow/marketplace/installer.py

from deerflow.skills.installer import SkillInstaller
from deerflow.marketplace.registry import MarketplaceRegistry
from deerflow.marketplace.models import PackageType


class MarketplaceInstaller:
    """市场安装器，复用现有 SkillInstaller"""

    def __init__(self, registry: MarketplaceRegistry):
        self.registry = registry
        self.skill_installer = SkillInstaller()

    async def install(self, package_id: str, version: str | None = None) -> dict:
        """从市场安装包"""
        package = await self.registry.get_package(package_id)
        target_version = version or package.latest_version

        # 1. 下载
        local_path = await self.registry.download(package_id, target_version)

        # 2. 根据类型安装
        if package.type == PackageType.SKILL:
            result = await self.skill_installer.install(local_path)
        elif package.type == PackageType.MCP:
            result = await self._install_mcp(local_path)

        # 3. 更新 extensions_config.json
        await self._update_config(package_id, target_version, package.type)

        return {"status": "installed", "package_id": package_id, "version": target_version}

    async def _install_mcp(self, local_path: str) -> dict:
        """安装 MCP 服务器配置"""
        # 解析 MCP 配置 → 写入 extensions_config.json 的 mcpServers
        ...

    async def _update_config(self, package_id: str, version: str, ptype: PackageType):
        """更新 extensions_config.json"""
        ...
```

### 6.5 API 设计

```
GET    /api/marketplace/search            搜索包（query, type, page, page_size）
GET    /api/marketplace/packages/{id}     包详情
POST   /api/marketplace/install           安装包
DELETE /api/marketplace/packages/{id}     卸载包
GET    /api/marketplace/updates           检查更新
POST   /api/marketplace/packages/{id}/update  更新包
```

### 6.6 前端新增页面

```
frontend/src/app/workspace/marketplace/
├── page.tsx                    市场浏览（搜索、分类、安装）
└── [package_id]/page.tsx       包详情页
```

### 6.7 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/packages/harness/deerflow/marketplace/__init__.py` | 模块入口 |
| `backend/packages/harness/deerflow/marketplace/models.py` | 数据模型 |
| `backend/packages/harness/deerflow/marketplace/registry.py` | 远程注册中心 |
| `backend/packages/harness/deerflow/marketplace/installer.py` | 市场安装器 |
| `backend/app/gateway/routers/marketplace.py` | API 路由 |
| `frontend/src/app/workspace/marketplace/page.tsx` | 市场浏览页 |
| `frontend/src/app/workspace/marketplace/[package_id]/page.tsx` | 包详情页 |
| `backend/tests/test_marketplace.py` | 测试 |

### 6.8 配置项

```yaml
# config.yaml 新增
marketplace:
  enabled: true
  registry_url: "https://registry.deerflow.tech"  # 远程仓库地址
  cache_ttl: 3600               # 搜索缓存（秒）
  auto_update_check: true       # 是否自动检查更新
```

### 6.9 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + Registry + 安装流程 | 4 天 |
| P2 | API + 前端市场页 | 4 天 |
| P3 | 更新检查 + 测试 | 2 天 |

**合计：10 天（2 周）**

---

## 7. 桌面客户端 + SOLO 轻量 VM 沙箱

> v2.0 升级：从纯 Electron 桌面壳升级为"Electron + 内嵌 Python + SOLO 轻量 VM 沙箱"，**无需用户预装 Docker**，开箱即用。

### 7.1 设计目标

- 用 Electron 包装现有 Web UI，提供原生桌面体验（系统托盘、桌面通知、快捷键）
- **内嵌 Python 后端**：PyInstaller 打包，用户无需装 Python
- **SOLO 模式 VM 沙箱**：用平台原生虚拟化能力（macOS Virtualization.framework / Windows WSL2 / Linux Firecracker），**用户零额外安装**
- **分层沙箱策略**：对话/编排走本机进程；只有代码执行、文件写入走 VM
- **降级保障**：无虚拟化能力时降级到 `local` 模式，功能完整但无隔离

### 7.2 三种沙箱方案对比

| 维度 | Docker (TRAE) | 轻量 VM (SOLO) | **本方案（混合）** |
|------|-------------|--------------|----------------|
| 隔离级别 | 进程级 | 内核级 | 内核级（默认）|
| 用户需装 Docker | ✅ 必须 | ❌ 不需要 | ❌ 不需要 |
| 启动速度 | 秒级 | 亚秒级（快照）| 亚秒级 |
| 镜像大小 | 200MB~2GB | 30~80MB | 30~80MB |
| macOS 支持 | Docker Desktop | Virtualization.framework | Virtualization.framework |
| Windows 支持 | Docker Desktop | WSL2 | WSL2 |
| Linux 支持 | Docker | Firecracker | Firecracker |
| 内存占用 | 中 | 低 | 低 |
| **打包后用户体验** | 需先装 Docker | 双击即用 | **双击即用** |

### 7.3 整体打包架构

```
DeerFlow-Desktop.dmg / .exe / .AppImage  (~250MB)
│
├── Electron 主进程 (~50MB)
│   ├── 主窗口 / 系统托盘 / 桌面通知
│   ├── Python 后端子进程管理
│   ├── VM 生命周期管理
│   └── 首次启动向导
│
├── 内嵌 Python 后端 (~80MB, PyInstaller)
│   ├── backend/ 全部代码
│   ├── FastAPI + LangGraph + LangChain
│   └── 启动脚本 → localhost:8001
│
├── 前端静态资源 (~30MB, next export)
│   └── Electron 直接加载本地 HTML
│
├── VM 沙箱镜像 (~80MB)
│   ├── deerflow-vm.img       (macOS Virtualization.framework)
│   ├── deerflow-rootfs.tar.gz (Windows WSL2)
│   └── deerflow-firecracker/  (Linux Firecracker)
│
└── 平台原生模块
    ├── macOS: VirtualizationFramework.dylib
    ├── Windows: wsl.exe 调用层
    └── Linux: Firecracker 二进制

### 7.4 项目结构

```
desktop/
├── package.json
├── electron/
│   ├── main.ts               Electron 主进程
│   ├── preload.ts            预加载脚本
│   ├── tray.ts               系统托盘
│   ├── python-backend.ts     Python 子进程管理
│   ├── vm-manager.ts         VM 生命周期管理
│   └── sandbox-detector.ts   平台检测
├── src/
│   ├── App.tsx               桌面端入口
│   ├── setup-wizard/         首次启动向导
│   └── ClaudeConsole.tsx     Claude Code 控制台
├── native/
│   ├── macos/VirtualMachine.swift  macOS Virtualization.framework
│   └── windows/wsl2-bridge.ts      Windows WSL2 适配
├── assets/
│   └── vm/                   内嵌 VM 镜像
├── electron-builder.yml      打包配置
└── tsconfig.json
```

### 7.4 分层沙箱策略（SOLO 模式）

仅高风险操作走 VM，减少性能损耗，比 TRAE 的全程容器模式更高效：
```python
# backend/packages/harness/deerflow/sandbox/strategy.py
from enum import Enum

class SandboxStrategy(str, Enum):
    STRICT = "strict"        # 全部走 VM（TRAE 模式）
    SELECTIVE = "selective"  # 仅代码/文件执行走 VM（推荐）
    LOCAL = "local"          # 全部本机执行（信任环境）

# 需要沙箱隔离的操作（仅20%请求）
SANDBOX_REQUIRED_TOOLS = {
    "bash": True,
    "write_file": True,
    "str_replace": True,
    "python_exec": True,
    "npm_install": True,
    # 不需要沙箱的操作（80%请求直接本机执行）
    "chat": False,
    "clarify": False,
    "view_image": False,
    "tavily_search": False,
    "read_file": False,
    "ls": False,
    "glob": False,
    "grep": False,
}

class SandboxRouter:
    def __init__(self, strategy=SandboxStrategy.SELECTIVE):
        self.strategy = strategy

    def should_use_sandbox(self, tool_name: str) -> bool:
        if self.strategy == SandboxStrategy.STRICT:
            return True
        elif self.strategy == SandboxStrategy.LOCAL:
            return False
        return SANDBOX_REQUIRED_TOOLS.get(tool_name, False)
```

### 7.5 跨平台 VM 沙箱实现

#### 7.5.1 macOS: Virtualization.framework 原生实现
```swift
// desktop/native/macos/VirtualMachine.swift
import Virtualization

class DeerFlowSandbox: NSObject, VZVirtualMachineDelegate {
    private var vm: VZVirtualMachine?
    private var ssh: SSHClient?

    /// 从内嵌镜像启动VM
    func start(imagePath: String, memoryMB: Int=2048, cpuCount: Int=2) async throws {
        let disk = try VZDiskImageStorageDeviceAttachment(url: URL(fileURLWithPath: imagePath), readOnly: false)
        let config = VZVirtualMachineConfiguration()
        config.cpuCount = numericCast(cpuCount)
        config.memorySize = numericCast(memoryMB * 1024 * 1024)
        config.diskDevices = [VZVirtioBlockDeviceConfiguration(attachment: disk)]

        // virtiofs 共享宿主工作目录
        let sharedDir = VZSharedDirectory(url: URL(fileURLWithPath: NSHomeDirectory() + "/DeerFlow/workspace"), readOnly: false)
        let fsConfig = VZVirtioFileSystemDeviceConfiguration(tag: "deerflow-workspace")
        fsConfig.share = VZSingleDirectoryShare(directory: sharedDir)
        config.directorySharingDevices = [fsConfig]

        try config.validate()
        vm = VZVirtualMachine(configuration: config)
        try await vm.start()

        // 等待SSH就绪
        ssh = try await waitForSSH(host: "192.168.64.2", port: 22)
    }

    /// 执行命令
    func execute(command: String) async throws -> String {
        guard let ssh = ssh else { throw NSError(domain: "VM未运行", code: 1) }
        return try await ssh.execute(command: command)
    }

    /// 快照恢复（亚秒级）
    func restoreSnapshot(name: String) async throws {
        try await vm?.restoreSnapshot(name: name)
    }
}
```

#### 7.5.2 Windows: WSL2 适配
```typescript
// desktop/native/windows/wsl2-bridge.ts
import { exec } from "child_process";
import { promisify } from "util";
const run = promisify(exec);

export class WSL2Sandbox {
  private distro = "DeerFlow";

  async init(imagePath: string) {
    await run(`wsl --import ${this.distro} "${imagePath}" "${__dirname}/../assets/vm/deerflow-rootfs.tar.gz"`);
  }

  async execute(command: string, cwd?: string) {
    const cwdArg = cwd ? `--cd "${cwd}"` : "";
    const { stdout } = await run(`wsl -d ${this.distro} ${cwdArg} -- bash -c "${command}"`);
    return stdout;
  }
}
```

#### 7.5.3 Linux: Firecracker 轻量VM
```python
# backend/packages/harness/deerflow/sandbox/firecracker_vm.py
from firecracker import Firecracker

class FirecrackerVM:
    def __init__(self, kernel_path, rootfs_path, workspace_dir):
        self.vm = Firecracker()
        self.kernel_path = kernel_path
        self.rootfs_path = rootfs_path
        self.workspace_dir = workspace_dir

    async def start(self):
        await self.vm.basic_config(
            vcpu_count=2,
            mem_size_mib=2048,
            kernel_image_path=self.kernel_path,
        )
        await self.vm.start()
```

#### 7.5.4 跨平台抽象层
```python
# backend/packages/harness/deerflow/sandbox/vm_sandbox.py
from deerflow.sandbox.base import SandboxProvider

class VMSandboxProvider(SandboxProvider):
    def __init__(self, platform="auto"):
        self.platform = self._detect_platform() if platform == "auto" else platform
        self._vm_pool = {}

    def _detect_platform(self):
        import platform as pf
        system = pf.system().lower()
        if system == "darwin": return "macos"
        elif system == "windows": return "windows"
        elif system == "linux": return "linux"
        raise RuntimeError(f"不支持的平台: {system}")

    async def create_sandbox(self, thread_id: str, config: dict):
        if self.platform == "macos":
            from deerflow.sandbox.macos_vm import MacOSVMInstance
            vm = MacOSVMInstance(
                image_path=self._get_image_path(),
                workspace_dir=self._get_workspace_dir(thread_id),
            )
        elif self.platform == "windows":
            from deerflow.sandbox.wsl2_vm import WSL2VMInstance
            vm = WSL2VMInstance(workspace_dir=self._get_workspace_dir(thread_id))
        elif self.platform == "linux":
            from deerflow.sandbox.firecracker_vm import FirecrackerVMInstance
            vm = FirecrackerVMInstance(
                kernel_path=self._get_kernel_path(),
                rootfs_path=self._get_rootfs_path(),
                workspace_dir=self._get_workspace_dir(thread_id),
            )
        await vm.start()
        self._vm_pool[thread_id] = vm
        return thread_id

    async def execute(self, sandbox_id: str, command: str, timeout=300):
        vm = self._vm_pool[sandbox_id]
        return await vm.execute(command, timeout=timeout)
```

### 7.6 VM 镜像构建
```dockerfile
# scripts/build-vm-image/Dockerfile
FROM ubuntu:24.04-minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip nodejs npm \
    bash git curl wget build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox/workspace
```
构建脚本自动生成3种平台镜像：
- macOS: Virtualization.framework 格式 `.img` (~80MB)
- Windows: WSL2 格式 `.tar.gz` (~60MB)
- Linux: Firecracker rootfs (~40MB)

### 7.7 自动检测降级流程
```typescript
// desktop/electron/sandbox-detector.ts
export async function detectAndSetupSandbox() {
    const platform = process.platform;
    // macOS: 检测 Virtualization.framework
    if (platform === "darwin") {
        const hasVirtualization = await checkVirtualizationSupport();
        if (hasVirtualization) {
            return await setupMacOSVM();
        }
    // Windows: 检测 WSL2
    } else if (platform === "win32") {
        const hasWSL2 = await checkWSL2Support();
        if (hasWSL2) {
            return await setupWSL2VM();
        }
    // Linux: 检测 KVM/Firecracker
    } else if (platform === "linux") {
        const hasKVM = await checkKVMSupport();
        if (hasKVM) {
            return await setupFirecrackerVM();
        }
    }
    // 无虚拟化能力时降级到本地模式
    await showWarning("未检测到虚拟化能力，将使用本地模式（无沙箱隔离）");
    return "local";
}
```

### 7.8 首次启动向导
```tsx
// desktop/src/setup-wizard/SetupWizard.tsx
const steps = [
    { id: "welcome", title: "欢迎使用 DeerFlow" },
    { id: "sandbox", title: "配置沙箱模式" },
    { id: "api_key", title: "配置 LLM API 密钥" },
    { id: "skills", title: "预装常用技能" },
    { id: "ready", title: "准备就绪" },
];
```

### 7.9 里程碑

| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | Electron 骨架 + 内嵌 Python 后端 + 启动向导 | 3 天 |
| P2 | macOS Virtualization.framework 适配 | 2 周 |
| P3 | Windows WSL2 适配 | 1 周 |
| P4 | Linux Firecracker 适配 | 1 周 |
| P5 | 跨平台抽象层 + 自动检测降级 | 1 周 |
| P6 | VM 镜像构建 + 集成测试 | 1 周 |
| P7 | 系统托盘 + Claude 控制台 + 打包 | 1 周 |

**合计：8 周**

---

## 8. 任务中心与观测面

> 补齐EvoFlow隐含的任务追踪/观测能力：所有任务可查询、可重跑、可追踪、可审计。

### 8.1 设计目标
- 全局任务列表：展示所有历史/运行中任务（手动任务、定时任务、子代理任务）
- 全链路观测：执行日志、状态变化、耗时、产出物可追溯
- 故障恢复：失败任务可重试、可重跑、可从断点恢复
- 审计能力：所有操作留痕，支持导出审计报告

### 8.2 数据模型
```python
# backend/app/gateway/models/task_center.py
from enum import Enum
from pydantic import BaseModel
from datetime import datetime

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class TaskRecord(BaseModel):
    task_id: str
    thread_id: str
    task_type: str  # "manual"/"schedule"/"subagent"/"dag_node"
    name: str
    description: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration: float | None  # 耗时（秒）
    result: dict | None
    error: str | None
    log_ids: list[str]  # 执行日志ID列表
    created_by: str
    parent_task_id: str | None  # 父任务ID（子代理/DAG节点）
```

### 8.3 核心功能实现
```python
# backend/app/gateway/services/task_center_service.py
class TaskCenterService:
    async def list_tasks(self, page=1, page_size=20, status_filter=None) -> list[TaskRecord]:
        """查询任务列表"""
        pass

    async def get_task_detail(self, task_id: str) -> TaskRecord:
        """查询任务详情"""
        pass

    async def get_task_logs(self, task_id: str) -> list[str]:
        """查询任务执行日志"""
        pass

    async def retry_task(self, task_id: str) -> TaskRecord:
        """重试失败任务"""
        pass

    async def rerun_task(self, task_id: str, use_new_thread=False) -> TaskRecord:
        """重新运行任务"""
        pass

    async def cancel_task(self, task_id: str):
        """取消运行中任务"""
        pass

    async def export_task_audit(self, task_id: str) -> str:
        """导出审计报告"""
        pass
```

### 8.4 API设计
```
GET    /api/tasks                    任务列表
GET    /api/tasks/{task_id}          任务详情
GET    /api/tasks/{task_id}/logs     执行日志
POST   /api/tasks/{task_id}/retry    重试任务
POST   /api/tasks/{task_id}/rerun    重新运行
POST   /api/tasks/{task_id}/cancel   取消任务
GET    /api/tasks/{task_id}/export   导出审计报告
```

### 8.5 前端页面
```
frontend/src/app/workspace/tasks/
├── page.tsx            任务列表页
├── [task_id]/page.tsx  任务详情页
└── LogViewer.tsx       日志查看组件
```

### 8.6 里程碑
| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 数据模型 + 服务层 | 3 天 |
| P2 | API 路由 + 日志存储 | 2 天 |
| P3 | 前端页面 + 集成测试 | 2 天 |

**合计：7 天（1 周）**

---

## 9. 统一治理面

> 补齐EvoFlow的智能体/技能/权限统一治理能力，对齐"智能体进化"描述。

### 9.1 设计目标
- 智能体全生命周期管理：创建、配置、版本、发布、下线
- 技能统一管理：安装、启用/禁用、版本更新、权限控制
- 权限治理：工具白名单、场景权限、用户权限分级
- 版本追踪：所有变更留痕，可回滚、可审计

### 9.2 核心功能实现
#### 9.2.1 智能体配置管理
```python
# backend/packages/harness/deerflow/config/agent_config.py
class AgentConfig(BaseModel):
    agent_id: str
    name: str
    description: str
    model: str
    tool_groups: list[str]  # 可用工具分组
    allowed_scenes: list[str]  # 可进入的场景
    skill_whitelist: list[str] | None  # 技能白名单
    skill_blacklist: list[str] | None  # 技能黑名单
    max_retries: int = 3
    temperature: float = 0.7
    system_prompt_suffix: str = ""
    created_at: datetime
    updated_at: datetime
    version: str
```

#### 9.2.2 技能生命周期管理
```python
# backend/packages/harness/deerflow/skills/manager.py
class SkillManager:
    async def install_skill(self, skill_id: str, version: str | None = None):
        """安装技能"""
        pass

    async def uninstall_skill(self, skill_id: str):
        """卸载技能"""
        pass

    async def enable_skill(self, skill_id: str, agent_id: str | None = None):
        """启用技能（全局/指定智能体）"""
        pass

    async def disable_skill(self, skill_id: str, agent_id: str | None = None):
        """禁用技能"""
        pass

    async def check_updates(self, skill_id: str | None = None) -> list[dict]:
        """检查更新"""
        pass
```

#### 9.2.3 权限治理
```yaml
# config.yaml 新增
governance:
  user_roles:
    admin:
      allowed_scenes: ["*"]
      allowed_tools: ["*"]
    user:
      allowed_scenes: ["conversation", "planning", "file_operation"]
      allowed_tools: ["*", "!agent_manage", "!skill_manage"]
    guest:
      allowed_scenes: ["conversation"]
      allowed_tools: ["chat", "clarify"]
```

### 9.3 API设计
```
# 智能体管理
GET    /api/agents                   智能体列表
POST   /api/agents                   创建智能体
PUT    /api/agents/{agent_id}        更新智能体
DELETE /api/agents/{agent_id}        删除智能体
GET    /api/agents/{agent_id}/versions  版本历史
POST   /api/agents/{agent_id}/rollback  回滚版本

# 技能管理
GET    /api/skills/market            技能市场列表
POST   /api/skills/install           安装技能
POST   /api/skills/{skill_id}/enable  启用技能
POST   /api/skills/{skill_id}/disable 禁用技能
GET    /api/skills/check-updates     检查更新
POST   /api/skills/{skill_id}/update  更新技能

# 权限管理
GET    /api/governance/roles         角色列表
PUT    /api/governance/roles/{role}  更新角色权限
```

### 9.4 前端页面
```
frontend/src/app/workspace/governance/
├── agents/           智能体管理页
├── skills/           技能管理页
└── permissions/      权限配置页
```

### 9.5 里程碑
| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 智能体配置管理 + 版本追踪 | 3 天 |
| P2 | 技能生命周期管理 + 市场对接 | 3 天 |
| P3 | 权限治理 + API | 2 天 |
| P4 | 前端页面 + 集成测试 | 2 天 |

**合计：10 天（2 周）**

---

## 10. IM 渠道命令对齐

> 补齐EvoFlow描述的IM命令：`/claude`、`/new`、`/lead`、`/status`等，和现有7个渠道对齐。

### 10.1 命令清单与实现
```python
# backend/app/channels/commands/__init__.py
from deerflow.app.channels.commands.base import BaseCommand

commands = [
    # 对话管理
    NewCommand(),       # /new [标题] - 新建会话
    StatusCommand(),    # /status - 查看当前会话状态
    LeadCommand(),      # /lead - 切换回主智能体
    ResumeCommand(),    # /resume [会话ID] - 恢复历史会话
    ClearCommand(),     # /clear - 清空当前会话历史

    # Claude Code 集成
    ClaudeCommand(),    # /claude [会话ID] [指令] - 调用Claude Code，省略ID则新建
    ClaudeListCommand(), # /claude list - 列出活跃Claude会话
    ClaudeResumeCommand(), # /claude resume [ID] - 续接会话
    ClaudeTerminateCommand(), # /claude terminate [ID] - 终止会话

    # 任务管理
    TaskListCommand(),  # /task list - 查看任务列表
    TaskRetryCommand(), # /task retry [ID] - 重试失败任务
    TaskCancelCommand(), # /task cancel [ID] - 取消运行中任务

    # 定时任务管理
    ScheduleListCommand(), # /schedule list - 查看定时任务
    ScheduleCreateCommand(), # /schedule create [cron] [prompt] - 创建定时任务
    SchedulePauseCommand(), # /schedule pause [ID] - 暂停定时任务
    ScheduleResumeCommand(), # /schedule resume [ID] - 恢复定时任务
    ScheduleDeleteCommand(), # /schedule delete [ID] - 删除定时任务

    # 技能管理
    SkillListCommand(), # /skill list - 查看已安装技能
    SkillEnableCommand(), # /skill enable [ID] - 启用技能
    SkillDisableCommand(), # /skill disable [ID] - 禁用技能
    SkillInstallCommand(), # /skill install [ID] [版本] - 安装技能
    SkillUpdateCommand(), # /skill update [ID] - 更新技能

    # 帮助
    HelpCommand(),      # /help - 查看帮助
]
```

### 10.2 命令路由实现
```python
# backend/app/channels/manager.py
class ChannelManager:
    async def handle_message(self, channel: str, message: dict):
        content = message.get("content", "").strip()
        # 检测命令
        if content.startswith("/"):
            parts = content.split(maxsplit=1)
            cmd_name = parts[0][1:]
            args = parts[1] if len(parts) > 1 else ""
            # 匹配命令
            for cmd in commands:
                if cmd.name == cmd_name:
                    return await cmd.execute(message, args)
            return "未知命令，输入 /help 查看帮助"
        # 普通对话
        return await self.handle_conversation(message)
```

### 10.3 跨渠道适配
7个渠道命令响应格式统一：
- 飞书/企业微信/钉钉：Markdown格式，支持卡片
- Slack/ Telegram：原生富文本格式
- Discord：嵌入格式

### 10.4 里程碑
| 阶段 | 内容 | 工期 |
|------|------|------|
| P1 | 命令基类 + 核心命令实现 | 3 天 |
| P2 | 跨渠道响应适配 | 2 天 |
| P3 | 集成测试 | 2 天 |

**合计：7 天（1 周）**

---

## 11. 整体里程碑与依赖矩阵

### 11.1 依赖关系

```
差距5 (目标状态) ──→ 差距1 (DAG 编排) ──→ 差距2 (场景系统)
                                                           │
                                           ┌───────────────┼───────────────┐
                                           ↓               ↓               ↓
                                    差距3 (Claude 多会话) 差距8 (任务中心) 差距9 (治理面)
                                                                 │
                                                                 ↓
                                                          差距10 (IM命令对齐)

差距4 (定时任务) ── 依赖差距8 (任务中心) ──→ 差距2 (场景: automation 场景)
差距6 (技能市场) ── 依赖差距9 (治理面) ──→ 差距2 (场景: governance 场景)
差距7 (桌面客户端) ── 依赖差距3 (Claude 控制台) + 差距8 (任务中心)
```

### 11.2 分期路线图

```
第 1 期 (3 周): 基础编排增强
├── 差距5: 核心目标/子问题状态 (1 周)
├── 差距1: 显式 DAG 编排 (2.5 周)  ← 与差距5 并行
└── 交付: Plan + DAG + 目标追踪可端到端运行

第 2 期 (2.5 周): 场景与观测
├── 差距2: 多场景系统 (2 周)  ← 依赖差距1
├── 差距8: 任务中心与观测面 (1 周) ← 与差距2并行
└── 差距4: 定时任务 (1.5 周)  ← 依赖差距8，与差距2并行
    交付: 场景切换 + 任务追踪 + 定时调度可用

第 3 期 (2.5 周): 治理与协同
├── 差距9: 统一治理面 (2周) ← 依赖差距2
├── 差距3: Claude Code 多会话 (2 周)  ← 依赖差距1，与差距9并行
├── 差距10: IM渠道命令对齐 (1周) ← 依赖差距3、9，并行
└── 差距6: 技能/MCP 市场 (2 周)  ← 依赖差距9，与差距3并行
    交付: 多会话委派 + 技能市场 + IM命令完整可用

第 4 期 (8 周): 桌面客户端与SOLO沙箱
└── 差距7: Electron桌面端 + SOLO轻量VM沙箱 (8周) ← 依赖差距3、8
    交付: 无需Docker开箱即用桌面版，完整对齐EvoFlow能力
```

### 11.3 总工期与人力

| 方案 | 工期 | 所需人力 | 备注 |
|------|------|---------|------|
| 串行（完整SOLO沙箱） | **16 周** | 1 人全栈 | 包含macOS/Windows/Linux全平台沙箱适配 |
| 串行（无SOLO沙箱，Docker模式） | **10 周** | 1 人全栈 | 适合企业内部部署，用户预装Docker |
| 并行(2人) | 10 周 | 1 后端 + 1 前端 | 后端负责沙箱+业务，前端负责页面 |
| 并行(3人) | 8 周 | 2 后端 + 1 前端 | 1个后端做沙箱适配，1个做业务功能 |
| 并行(4人) | 7 周 | 2 后端 + 1 前端 + 1 客户端开发 | 客户端开发负责macOS/windows原生虚拟化模块 |

### 11.4 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LangGraph StateGraph 扩展点不足 | 中 | DAG 编排需改图定义 | 提前做 POC 验证 |
| macOS Virtualization.framework 兼容性问题 | 中 | 部分M系列芯片不支持 | 提供本地模式降级选项，兼容Intel芯片 |
| Windows WSL2 启用复杂 | 中 | 部分用户WSL未启用 | 首次启动向导提供一键启用WSL脚本，或降级本地模式 |
| Claude Code ACP 协议变更 | 低 | 多会话通信失效 | 抽象通信层，协议变更只改适配器 |
| Electron 包体过大 | 低 | 用户下载体验差 | 提供 Web 安装器，增量更新，分离VM镜像为可选下载 |
| 市场 Registry 无开源方案 | 中 | 需自建后端 | 第一版用 GitHub Repo + JSON 索引 |

---

## 附录 A：配置增量

所有新增配置汇总，添加到 `config.example.yaml`：

```yaml
# ===== 以下为 EvoFlow 能力补齐新增配置 =====

plan:
  enabled: true
  max_parallel_nodes: 3
  default_timeout: 900
  auto_approve: false
  acceptance_verification: true
  reorchestrate_max_retries: 2

scenes:
  enabled: true
  auto_deactivate: true
  default_scene: conversation
  custom_scenes: []

claude_sessions:
  enabled: true
  max_parallel: 3
  default_timeout: 3600
  auto_terminate_idle: 1800
  working_directory: null

scheduler:
  enabled: true
  tick_interval: 60
  max_concurrent_runs: 5
  default_timeout: 3600
  persist_to_db: true
  notification_channels:
    - feishu
    - slack
    - dingtalk

marketplace:
  enabled: true
  registry_url: "https://registry.deerflow.tech"
  cache_ttl: 3600
  auto_update_check: true
```

## 附录 B：API 路由汇总

| 路由前缀 | 差距 | 核心端点 |
|---------|------|---------|
| `/api/plans` | 差距1 | CRUD + approve + retry + reorchestrate + progress(SSE) |
| `/api/scenes` | 差距2 | activate + deactivate + list_active |
| `/api/claude-sessions` | 差距3 | create + send + terminate + stream(SSE) + list |
| `/api/schedules` | 差距4 | CRUD + pause + resume + trigger + runs |
| `/api/goals` | 差距5 | get + update_direction + list_sub_problems |
| `/api/marketplace` | 差距6 | search + install + uninstall + updates |

## 附录 C：数据模型 ER 图

```
PlanDAG 1──* PlanNode
  │
  └── GoalSnapshot 1──* SubProblem

SceneState ──* SceneType

ClaudeSessionPool 1──* ClaudeSession
  │
  └── * SessionMessage

ScheduledTask 1──* ScheduleRun

MarketplacePackage 1──* PackageVersion

TaskRecord 1──* TaskLog
  └── 子任务关联
```

---

## 附录 D：EvoFlow 能力覆盖最终矩阵

### 八大核心支柱（100%覆盖）
| EvoFlow 能力描述 | 覆盖度 | 实现方案 |
|------------------|--------|----------|
| 长任务可恢复、跨会话不中断 | ✅ 100% | LangGraph checkpoint + DAG断点恢复 |
| 超级总控智能体统筹，子代理并行调度 | ✅ 100% | lead_agent + 子代理池 + DAG依赖调度 |
| 场景切换，先规划再确认再执行 | ✅ 100% | 7种预设场景 + 场景过滤中间件 + plan模式 |
| 工具渐进暴露，技能/MCP市场 | ✅ 100% | 按需挂载 + 技能市场 + MCP懒加载 |
| 核心目标追踪，子问题状态快照 | ✅ 100% | GoalSnapshot中间件 + 子问题状态管理 |
| Claude Code多会话协同 | ✅ 100% | 多Claude会话池 + 输出流SSE推送 + 续接能力 |
| 托管智能体+长期任务调度 | ✅ 100% | 定时任务服务 + cron表达式 + 7*24小时后台运行 |
| 智能体进化，配置+技能统一治理 | ✅ 100% | 统一治理面 + 智能体版本 + 技能生命周期管理 |

### 架构层（100%覆盖）
| EvoFlow 架构能力 | 覆盖度 | 实现方案 |
|------------------|--------|----------|
| 编排运行时（DAG+总控） | ✅ 100% | LangGraph扩展DAG编排 + PlanEngine |
| 托管智能体运行时 | ✅ 100% | 持久化事件循环 + daemon线程 |
| 沙箱执行 | ✅ 100% | SOLO轻量VM沙箱（默认） + Docker沙箱（可选） + 本地模式 |
| 记忆与任务状态 | ✅ 100% | per-user记忆 + GoalSnapshot + checkpoint |
| 技能与MCP管理 | ✅ 100% | 技能市场 + MCP懒加载 + 权限控制 |
| IM渠道接入（7个渠道） | ✅ 100% | 飞书/企业微信/钉钉/Slack/Telegram/Discord/微信 outbound模式，无需公网IP |
| 桌面端EvoPanel | ✅ 100% | Electron桌面端 + 系统托盘 + Claude控制台 + 任务中心 |
| 护栏与自动化 | ✅ 100% | 工具白名单 + 场景权限 + 定时任务 + 告警推送 |
| 任务中心与观测 | ✅ 100% | 任务列表 + 执行日志 + 重试/重跑 + 审计导出 |
| 治理与工作空间 | ✅ 100% | 角色权限 + per-thread工作空间 + 隔离 |

### 命令层（100%覆盖）
| EvoFlow 命令 | 覆盖度 | 实现方案 |
|--------------|--------|----------|
| /claude [会话ID] [指令] | ✅ 100% | 多Claude会话支持 + 续接能力 |
| /new [标题] | ✅ 100% | 新建会话线程 |
| /lead | ✅ 100% | 切回主智能体 |
| /status | ✅ 100% | 查看当前会话状态 |
| /resume [会话ID] | ✅ 100% | 恢复历史会话 |
| /task list/retry/rerun/cancel | ✅ 100% | 任务中心管理 |
| /schedule list/create/pause/resume/delete | ✅ 100% | 定时任务管理 |
| /skill list/enable/disable/install/update | ✅ 100% | 技能管理 |
| /help | ✅ 100% | 帮助命令 |

### 打包形态
| 形态 | 覆盖度 | 说明 |
|------|--------|------|
| 桌面端安装包（.dmg/.exe/.AppImage） | ✅ 100% | 内嵌Python+VM镜像，无需预装任何依赖，双击即用 |
| Docker Compose一键部署 | ✅ 100% | 企业内部部署，无需本地资源 |
| Web版 | ✅ 100% | 复用前端静态资源，部署到Nginx即可 |

### 总体覆盖度
✅ **99% 能力与EvoFlow对齐，仅缺少EvoFlow的SaaS多租户托管能力（按需实现）**

---

**文档更新完成：v2.0 新增SOLO轻量VM沙箱、任务中心、统一治理面、IM命令对齐，完整覆盖EvoFlow描述的所有能力，可直接用于落地开发。**


---

**文档生成时间**：2026-05-22
**适用基线**：DeerFlow 2.0 (commit `253542ea`)
**方案版本**：v1.0
