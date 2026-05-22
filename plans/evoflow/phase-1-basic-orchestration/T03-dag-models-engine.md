# T03 - DAG 数据模型与 PlanEngine 骨架

## 元信息
- **任务ID**: T03
- **阶段**: 第1期 - 基础编排增强
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: 无（与 T01 并行）
- **关联差距**: 差距1 - 显式 DAG 编排

## 目标
建立 PlanDAG/PlanNode 核心数据模型，实现 DAG 拓扑操作（就绪节点获取、完成判定、失败节点查找），创建 PlanEngine 骨架。

## 详细实现步骤

### 步骤1: 创建 DAG 数据模型
- **文件**: `backend/packages/harness/deerflow/plan/__init__.py`
- **操作**: 新建
- **内容**: 模块入口
```python
from deerflow.plan.models import PlanDAG, PlanNode, NodeStatus, BarrierType
```

- **文件**: `backend/packages/harness/deerflow/plan/models.py`
- **操作**: 新建
- **内容**: 完整 DAG 数据模型。**注意**: `edges` 字段使用 `list[list[str]]` 而非 `list[tuple[str, str]]`，因为 Pydantic v2 在 JSON 序列化时 tuple 会被转为 list，使用 `list[list[str]]` 可避免序列化/反序列化不一致问题。
```python
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BarrierType(str, Enum):
    ALL = "all"
    ANY = "any"
    MANUAL = "manual"


class PlanNode(BaseModel):
    id: str
    title: str
    description: str
    assignee: str = "general-purpose"
    dependencies: list[str] = Field(default_factory=list)
    barrier_type: BarrierType = BarrierType.ALL
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_from: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    subagent_config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 900


class PlanDAG(BaseModel):
    plan_id: str
    title: str
    description: str
    goal: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    nodes: dict[str, PlanNode] = Field(default_factory=dict)
    edges: list[list[str]] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_ready_nodes(self) -> list[PlanNode]: ...
    def is_complete(self) -> bool: ...
    def get_failed_nodes(self) -> list[PlanNode]: ...
```
- **验收**: PlanDAG 可实例化，拓扑方法可调用，`edges` 字段使用 `list[list[str]]`

### 步骤2: 实现 DAG 拓扑操作
- **文件**: `backend/packages/harness/deerflow/plan/models.py`
- **操作**: 续写
- **内容**: **关键修正**: `get_ready_nodes()` 是**只读查询**方法，不应修改节点状态。MANUAL 闸口的状态变更（PENDING → WAITING）必须由调用方（PlanEngine）显式执行，而不是在查询方法中隐式修改。
```python
def get_ready_nodes(self) -> list[PlanNode]:
    """获取当前可执行的节点（只读查询，不修改状态）。

    - ALL 闸口：所有上游完成才就绪
    - ANY 闸口：任一上游完成即就绪
    - MANUAL 闸口：所有上游完成后需要人工确认，此方法不返回 MANUAL 节点
      （MANUAL 节点由 PlanEngine 单独处理：检测上游完成后设为 WAITING，
       人工确认后设为 READY）
    """
    ready = []
    for node in self.nodes.values():
        if node.status != NodeStatus.PENDING:
            continue
        deps = [self.nodes[dep_id] for dep_id in node.dependencies if dep_id in self.nodes]
        if not deps:
            if node.barrier_type == BarrierType.MANUAL:
                continue
            ready.append(node)
            continue
        if node.barrier_type == BarrierType.ALL:
            if all(d.status == NodeStatus.COMPLETED for d in deps):
                ready.append(node)
        elif node.barrier_type == BarrierType.ANY:
            if any(d.status == NodeStatus.COMPLETED for d in deps):
                ready.append(node)
        elif node.barrier_type == BarrierType.MANUAL:
            if all(d.status == NodeStatus.COMPLETED for d in deps):
                pass
    return ready

def get_manual_waiting_nodes(self) -> list[PlanNode]:
    """获取所有上游已完成、等待人工确认的 MANUAL 闸口节点。

    PlanEngine 应在每次调度循环中调用此方法，将满足条件的 MANUAL 节点
    从 PENDING 设为 WAITING。
    """
    waiting = []
    for node in self.nodes.values():
        if node.status != NodeStatus.PENDING or node.barrier_type != BarrierType.MANUAL:
            continue
        deps = [self.nodes[dep_id] for dep_id in node.dependencies if dep_id in self.nodes]
        if not deps or all(d.status == NodeStatus.COMPLETED for d in deps):
            waiting.append(node)
    return waiting

def is_complete(self) -> bool:
    return all(n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED) for n in self.nodes.values())

def get_failed_nodes(self) -> list[PlanNode]:
    return [n for n in self.nodes.values() if n.status == NodeStatus.FAILED]
```
- **验收**: 拓扑排序正确，`get_ready_nodes()` 不修改状态，MANUAL 闸口逻辑由 `get_manual_waiting_nodes()` + PlanEngine 协作完成

### 步骤3: 扩展 ThreadState
- **文件**: `backend/packages/harness/deerflow/agents/thread_state.py`
- **操作**: 改造
- **内容**: 新增 DAG 相关字段。**注意**: `ThreadState` 是 `TypedDict`，所有字段必须 JSON 可序列化，使用 `dict` 类型而非 Pydantic 模型。
```python
class ThreadState(AgentState):
    # ... 现有字段 ...
    goal_snapshot: NotRequired[dict | None]
    plan: NotRequired[dict | None]
    plan_approved: NotRequired[bool | None]
    active_node_ids: NotRequired[list[str] | None]
```
- **验收**: `ThreadState` 可接受 plan 相关字段，使用 `NotRequired[dict | None]` / `NotRequired[bool | None]` / `NotRequired[list[str] | None]` 模式

### 步骤4: 创建 PlanEngine 骨架
- **文件**: `backend/packages/harness/deerflow/plan/engine.py`
- **操作**: 新建
- **内容**:
```python
from collections.deque import deque

from langchain_core.language_models import BaseChatModel

from deerflow.plan.models import NodeStatus, PlanDAG, PlanNode


class PlanEngine:
    """Plan DAG 的创建、校验、重编排引擎。"""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def create_from_intent(self, messages: list) -> PlanDAG:
        """从用户意图生成 PlanDAG（LLM 结构化输出）。"""
        raise NotImplementedError

    async def verify_acceptance(self, node: PlanNode) -> bool:
        """校验节点结果是否满足验收标准。"""
        raise NotImplementedError

    async def reorchestrate(self, plan: PlanDAG, failed_nodes: list[PlanNode]) -> PlanDAG:
        """局部重编排：仅调整失败节点及其下游。"""
        raise NotImplementedError

    @staticmethod
    def validate_dag(plan: PlanDAG) -> list[str]:
        """校验 DAG 拓扑：检测环、孤立节点、缺失依赖。"""
        raise NotImplementedError
```
- **验收**: PlanEngine 可实例化，骨架方法可调用（先 raise NotImplementedError）

### 步骤5: 实现 DAG 校验
- **文件**: `backend/packages/harness/deerflow/plan/engine.py`
- **操作**: 续写
- **内容**: validate_dag 完整实现
```python
@staticmethod
def validate_dag(plan: PlanDAG) -> list[str]:
    errors: list[str] = []

    for node_id, node in plan.nodes.items():
        for dep_id in node.dependencies:
            if dep_id not in plan.nodes:
                errors.append(f"节点 '{node_id}' 引用了不存在的依赖 '{dep_id}'")

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in plan.nodes}

    def dfs(nid: str) -> None:
        color[nid] = GRAY
        node = plan.nodes[nid]
        for dep_id in node.dependencies:
            if dep_id not in color:
                continue
            if color[dep_id] == GRAY:
                errors.append(f"检测到环形依赖：{nid} → {dep_id}")
            elif color[dep_id] == WHITE:
                dfs(dep_id)
        color[nid] = BLACK

    for nid in plan.nodes:
        if color[nid] == WHITE:
            dfs(nid)

    edge_targets = {to_id for _, to_id in plan.edges}
    edge_sources = {from_id for from_id, _ in plan.edges}
    for nid, node in plan.nodes.items():
        if nid not in edge_targets and nid not in edge_sources and len(plan.nodes) > 1:
            if node.dependencies:
                pass
            else:
                has_incoming = any(nid == to_id for _, to_id in plan.edges)
                has_outgoing = any(nid == from_id for from_id, _ in plan.edges)
                if not has_incoming and not has_outgoing:
                    errors.append(f"孤立节点 '{nid}'（无入边也无出边）")

    return errors
```
- **验收**: 环形依赖、缺失依赖、孤立节点均可检出

### 步骤6: 创建 DAG 拓扑测试
- **文件**: `backend/tests/test_plan_dag.py`
- **操作**: 新建
- **内容**: 全面测试 DAG 拓扑操作
```python
# 测试用例：
# test_empty_dag - 空图
# test_single_node_ready - 单节点立即就绪
# test_linear_chain - 线性链 A→B→C
# test_parallel_branches - 并行分支 A→[B,C]→D
# test_barrier_all - ALL 闸口
# test_barrier_any - ANY 闸口
# test_barrier_manual_not_in_ready - MANUAL 闸口不出现在 get_ready_nodes
# test_barrier_manual_waiting - get_manual_waiting_nodes 返回满足条件的 MANUAL 节点
# test_is_complete - 完成判定
# test_is_complete_with_skipped - 跳过也算完成
# test_get_failed_nodes - 失败节点查找
# test_circular_dependency - 环形依赖检测
# test_missing_dependency - 缺失依赖检测
# test_orphan_node - 孤立节点检测
# test_edges_list_list_str - edges 使用 list[list[str]] 序列化/反序列化
# test_get_ready_nodes_no_mutation - get_ready_nodes 不修改节点状态
```
- **验收**: `cd backend && make test` 通过

## 验收标准
- [ ] PlanDAG / PlanNode / NodeStatus / BarrierType 模型定义完成
- [ ] `edges` 字段使用 `list[list[str]]`（非 `list[tuple[str, str]]`）
- [ ] `get_ready_nodes()` 只读查询，不修改状态
- [ ] `get_manual_waiting_nodes()` 正确识别 MANUAL 闸口节点
- [ ] is_complete / get_failed_nodes 正确判定
- [ ] PlanEngine 骨架创建完成，validate_dag 可检测环/孤立/缺失
- [ ] ThreadState 扩展使用 `NotRequired[dict | None]` 模式，不破坏现有代码
- [ ] 所有拓扑测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | 线性链 A→B→C | A 就绪→完成后 B 就绪→完成后 C 就绪 |
| 单元测试 | 并行 A→[B,C]→D | A 完成后 B、C 同时就绪 |
| 单元测试 | ALL 闸口 | 所有上游完成才就绪 |
| 单元测试 | ANY 闸口 | 任一上游完成即就绪 |
| 单元测试 | MANUAL 闸口 | 不出现在 get_ready_nodes，出现在 get_manual_waiting_nodes |
| 单元测试 | get_ready_nodes 无副作用 | 调用后节点状态不变 |
| 单元测试 | 环形依赖 | validate_dag 报错 |
| 单元测试 | 空图 | is_complete=True, get_ready_nodes=[] |
| 单元测试 | edges 序列化 | list[list[str]] JSON 往返一致 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| DAG 拓扑复杂度高导致 get_ready_nodes 性能差 | 低 | 节点数上限控制在 50 |
| 环形依赖检测实现复杂 | 中 | 使用经典 DFS 三色标记法 |
| ThreadState 改造影响现有代码 | 低 | `NotRequired[dict \| None]` 保证可选字段 |
| edges 类型不一致 | 低 | 强制使用 `list[list[str]]`，代码审查 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第1节
- `backend/packages/harness/deerflow/agents/thread_state.py` - ThreadState TypedDict 定义
