# T04 - PlanGraph 独立 StateGraph 与 plan_tool

## 元信息
- **任务ID**: T04
- **阶段**: 第1期 - 基础编排增强
- **优先级**: P2
- **预估工期**: 4 天
- **依赖任务**: T03
- **关联差距**: 差距1 - 显式 DAG 编排

## 目标
创建独立的 PlanGraph（LangGraph StateGraph）实现 DAG 调度，通过 plan_tool 让 lead_agent 与 Plan 系统交互。**关键架构决策**: lead_agent 由 `create_agent()` 创建，是 ReAct 风格 agent，**不能**像 StateGraph 那样添加节点/边。DAG 编排必须作为独立的 LangGraph StateGraph 子图运行，lead_agent 通过工具（plan_tool）与之交互。

## 详细实现步骤

### 步骤1: 定义 PlanState（PlanGraph 的状态 schema）
- **文件**: `backend/packages/harness/deerflow/plan/graph_state.py`
- **操作**: 新建
- **内容**: PlanGraph 使用独立的 PlanState，与 ThreadState 解耦。PlanState 是 PlanGraph 内部使用的 TypedDict，不污染 lead_agent 的 ThreadState。
```python
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


def merge_dict(existing: dict | None, new: dict | None) -> dict:
    if existing is None:
        return new or {}
    if new is None:
        return existing
    return {**existing, **new}


class PlanState(TypedDict):
    """PlanGraph 内部状态，独立于 ThreadState。"""
    messages: Annotated[list, add_messages]
    plan: NotRequired[dict | None]
    plan_approved: NotRequired[bool | None]
    active_node_ids: NotRequired[list[str] | None]
    plan_revised: NotRequired[bool | None]
```
- **验收**: PlanState 定义完成，与 ThreadState 解耦

### 步骤2: 实现 plan_create_node
- **文件**: `backend/packages/harness/deerflow/plan/nodes.py`
- **操作**: 新建
- **内容**: 总控生成 Plan DAG，等待用户确认
```python
from datetime import datetime

from deerflow.plan.engine import PlanEngine
from deerflow.plan.graph_state import PlanState
from deerflow.plan.models import NodeStatus, PlanDAG


async def plan_create_node(state: PlanState) -> dict:
    """总控生成 Plan DAG，等待用户确认。"""
    plan_engine = PlanEngine.__new__(PlanEngine)
    plan = await plan_engine.create_from_intent(state["messages"])
    errors = PlanEngine.validate_dag(plan)
    if errors:
        return {
            "messages": [{"role": "assistant", "content": f"Plan 校验失败：{'; '.join(errors)}"}],
            "plan": None,
            "plan_approved": False,
        }
    return {
        "messages": [{"role": "assistant", "content": f"Plan 已生成，等待确认：\n{plan.title}"}],
        "plan": plan.model_dump(),
        "plan_approved": False,
    }
```
- **验收**: 调用 PlanEngine 生成 PlanDAG 并返回

### 步骤3: 实现 plan_execute_dag_node
- **文件**: `backend/packages/harness/deerflow/plan/nodes.py`
- **操作**: 续写
- **内容**: 执行 DAG 中就绪的节点，并行派发子代理。**关键**: 使用 `SubagentExecutor.execute_async()` 复用现有子代理派发机制。
```python
import asyncio

from deerflow.plan.graph_state import PlanState
from deerflow.plan.models import NodeStatus, PlanDAG, PlanNode


async def plan_execute_dag_node(state: PlanState) -> dict:
    """执行 DAG 中就绪的节点，并行派发子代理。"""
    plan_dict = state.get("plan")
    if plan_dict is None:
        return {"plan": None}
    plan = PlanDAG.model_validate(plan_dict)

    ready_nodes = plan.get_ready_nodes()
    if not ready_nodes:
        manual_waiting = plan.get_manual_waiting_nodes()
        if manual_waiting:
            for node in manual_waiting:
                node.status = NodeStatus.WAITING
            return {
                "messages": [{"role": "assistant", "content": f"等待人工确认节点：{', '.join(n.id for n in manual_waiting)}"}],
                "plan": plan.model_dump(),
            }
        return {"plan": plan.model_dump()}

    tasks = []
    for node in ready_nodes:
        node.status = NodeStatus.RUNNING
        node.started_at = datetime.now()
        context = _build_subagent_context(plan, node)
        tasks.append(_dispatch_subagent(node, context))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for node, result in zip(ready_nodes, results):
        if isinstance(result, Exception):
            node.status = NodeStatus.FAILED
            node.error = str(result)
        else:
            node.status = NodeStatus.COMPLETED
            node.result = result
            node.completed_at = datetime.now()

    plan.updated_at = datetime.now()
    return {
        "plan": plan.model_dump(),
        "active_node_ids": [n.id for n in ready_nodes if n.status == NodeStatus.RUNNING],
    }
```
- **验收**: 就绪节点并行执行，结果正确回写

### 步骤4: 实现 _build_subagent_context
- **文件**: `backend/packages/harness/deerflow/plan/nodes.py`
- **操作**: 续写
- **内容**: 从 context_from 指定的上游节点继承结果
```python
def _build_subagent_context(plan: PlanDAG, node: PlanNode) -> dict:
    context = {
        "task_description": node.description,
        "acceptance_criteria": node.acceptance_criteria,
    }
    for upstream_id in node.context_from:
        if upstream_id in plan.nodes and plan.nodes[upstream_id].result:
            context[f"upstream_{upstream_id}_result"] = plan.nodes[upstream_id].result
    return context
```
- **验收**: 子代理上下文包含上游节点结果

### 步骤5: 实现 _dispatch_subagent（复用 SubagentExecutor）
- **文件**: `backend/packages/harness/deerflow/plan/nodes.py`
- **操作**: 续写
- **内容**: **关键**: 复用现有 `SubagentExecutor` / `task_tool` 机制派发子代理，与 `task_tool` 的调用路径一致。
```python
import asyncio
from typing import Any

from deerflow.plan.models import PlanNode
from deerflow.subagents.executor import SubagentExecutor


async def _dispatch_subagent(node: PlanNode, context: dict) -> Any:
    """复用现有 SubagentExecutor 派发子代理执行任务。

    与 task_tool 的调用路径一致：
    1. 创建 SubagentExecutor 实例
    2. 调用 execute_async() 获取 task_id
    3. 轮询等待结果
    """
    from deerflow.config.subagents_config import get_subagent_config
    from deerflow.subagents.executor import get_background_task_result

    subagent_config = get_subagent_config(node.assignee)
    executor = SubagentExecutor(
        config=subagent_config,
        tools=None,
        thread_id=f"plan_{node.id}",
    )

    prompt_parts = [f"任务：{node.description}"]
    if node.acceptance_criteria:
        prompt_parts.append(f"验收标准：{'; '.join(node.acceptance_criteria)}")
    for key, value in context.items():
        if key.startswith("upstream_"):
            prompt_parts.append(f"上游结果 ({key})：{value}")
    prompt = "\n".join(prompt_parts)

    task_id = executor.execute_async(prompt)

    while True:
        result = get_background_task_result(task_id)
        if result.status.value in ("completed", "failed", "timeout"):
            if result.status.value == "failed":
                raise RuntimeError(f"子代理执行失败：{result.error}")
            if result.status.value == "timeout":
                raise TimeoutError(f"子代理执行超时：{node.timeout_seconds}s")
            return result.result
        await asyncio.sleep(1)
```
- **验收**: 子代理通过 SubagentExecutor 正确派发并返回结果

### 步骤6: 实现 plan_supervise_node 和 plan_reorchestrate_node
- **文件**: `backend/packages/harness/deerflow/plan/nodes.py`
- **操作**: 续写
- **内容**:
```python
from deerflow.plan.engine import PlanEngine
from deerflow.plan.graph_state import PlanState
from deerflow.plan.models import NodeStatus, PlanDAG


async def plan_supervise_node(state: PlanState) -> dict:
    """监督节点，检查验收标准。"""
    plan_dict = state.get("plan")
    if plan_dict is None:
        return {"plan": None}
    plan = PlanDAG.model_validate(plan_dict)
    plan_engine = PlanEngine.__new__(PlanEngine)
    for node in plan.nodes.values():
        if node.status == NodeStatus.COMPLETED and node.acceptance_criteria:
            passed = await plan_engine.verify_acceptance(node)
            if not passed:
                node.status = NodeStatus.FAILED
                node.error = "验收标准未通过"
    return {"plan": plan.model_dump()}


async def plan_reorchestrate_node(state: PlanState) -> dict:
    """局部重编排。"""
    plan_dict = state.get("plan")
    if plan_dict is None:
        return {"plan": None, "plan_revised": False}
    plan = PlanDAG.model_validate(plan_dict)
    failed = plan.get_failed_nodes()
    if not failed:
        return {"plan": plan.model_dump(), "plan_revised": False}
    plan_engine = PlanEngine.__new__(PlanEngine)
    revised = await plan_engine.reorchestrate(plan, failed)
    return {"plan": revised.model_dump(), "plan_revised": True}
```
- **验收**: 监督节点检查验收标准，重编排节点处理失败

### 步骤7: 构建 PlanGraph（独立 StateGraph）和 plan_tool
- **文件**: `backend/packages/harness/deerflow/plan/graph.py`
- **操作**: 新建
- **内容**: **这是最关键的步骤**。PlanGraph 是独立的 LangGraph StateGraph，**不是** lead_agent 的节点扩展。lead_agent 通过 `plan_tool` 与之交互，类似 `task_tool` 的模式。
```python
from langgraph.graph import END, StateGraph

from deerflow.plan.graph_state import PlanState
from deerflow.plan.nodes import (
    plan_create_node,
    plan_execute_dag_node,
    plan_reorchestrate_node,
    plan_supervise_node,
)


def _route_after_create(state: PlanState) -> str:
    if state.get("plan_approved"):
        return "plan_execute_dag"
    return END


def _route_after_execute(state: PlanState) -> str:
    plan_dict = state.get("plan")
    if plan_dict is None:
        return END
    from deerflow.plan.models import PlanDAG
    plan = PlanDAG.model_validate(plan_dict)
    if plan.get_failed_nodes():
        return "plan_reorchestrate"
    if not plan.is_complete():
        return "plan_supervise"
    return END


def _route_after_reorchestrate(state: PlanState) -> str:
    if state.get("plan_revised"):
        return "plan_execute_dag"
    return END


def _route_after_supervise(state: PlanState) -> str:
    plan_dict = state.get("plan")
    if plan_dict is None:
        return END
    from deerflow.plan.models import PlanDAG
    plan = PlanDAG.model_validate(plan_dict)
    if plan.get_failed_nodes():
        return "plan_reorchestrate"
    return "plan_execute_dag"


def build_plan_graph() -> StateGraph:
    """构建独立的 PlanGraph StateGraph。"""
    graph = StateGraph(PlanState)

    graph.add_node("plan_create", plan_create_node)
    graph.add_node("plan_execute_dag", plan_execute_dag_node)
    graph.add_node("plan_supervise", plan_supervise_node)
    graph.add_node("plan_reorchestrate", plan_reorchestrate_node)

    graph.set_entry_point("plan_create")

    graph.add_conditional_edges("plan_create", _route_after_create)
    graph.add_conditional_edges("plan_execute_dag", _route_after_execute)
    graph.add_conditional_edges("plan_reorchestrate", _route_after_reorchestrate)
    graph.add_conditional_edges("plan_supervise", _route_after_supervise)

    return graph


plan_graph = build_plan_graph().compile()
```

- **文件**: `backend/packages/harness/deerflow/plan/plan_tool.py`
- **操作**: 新建
- **内容**: 创建 `plan_tool`，让 lead_agent 可以通过工具调用与 PlanGraph 交互。这与 `task_tool` 的模式一致：lead_agent 调用工具 → 工具内部运行子图 → 返回结果。
```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from deerflow.plan.graph import plan_graph
from deerflow.plan.graph_state import PlanState


class PlanToolInput(BaseModel):
    prompt: str = Field(description="用户意图描述，用于生成 Plan DAG")
    auto_approve: bool = Field(default=False, description="是否自动确认 Plan")


@tool(args_schema=PlanToolInput)
def plan_tool(prompt: str, auto_approve: bool = False) -> str:
    """创建并执行 DAG 编排计划。将复杂任务拆分为多个子任务，按依赖关系并行执行。"""
    import asyncio

    initial_state: PlanState = {
        "messages": [{"role": "user", "content": prompt}],
        "plan": None,
        "plan_approved": auto_approve,
        "active_node_ids": None,
        "plan_revised": None,
    }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, _arun_plan(initial_state)).result()
    else:
        result = asyncio.run(_arun_plan(initial_state))

    plan_dict = result.get("plan")
    if plan_dict is None:
        return "Plan 创建失败"

    from deerflow.plan.models import PlanDAG
    plan = PlanDAG.model_validate(plan_dict)
    completed = sum(1 for n in plan.nodes.values() if n.status.value == "completed")
    failed = sum(1 for n in plan.nodes.values() if n.status.value == "failed")
    total = len(plan.nodes)
    return f"Plan 执行完成：{completed}/{total} 成功，{failed} 失败"


async def _arun_plan(initial_state: PlanState) -> dict:
    config = {"configurable": {"thread_id": f"plan_{id(initial_state)}"}}
    result = None
    async for event in plan_graph.astream(initial_state, config=config):
        result = event
    return result or {}
```
- **验收**: PlanGraph 作为独立 StateGraph 正确构建，plan_tool 可被 lead_agent 调用

### 步骤8: 注册 plan_tool 到 lead_agent 的工具列表
- **文件**: `backend/packages/harness/deerflow/tools/tools.py`
- **操作**: 改造
- **内容**: 将 `plan_tool` 添加到 `BUILTIN_TOOLS` 列表，或通过配置系统注册。推荐通过 `get_available_tools` 的 `groups` 参数控制是否暴露。
```python
from deerflow.plan.plan_tool import plan_tool

BUILTIN_TOOLS = [
    present_file_tool,
    ask_clarification_tool,
    plan_tool,
]
```
- **验收**: lead_agent 可通过 `plan_tool` 调用 PlanGraph

## 验收标准
- [ ] PlanState 定义完成，与 ThreadState 解耦
- [ ] 4 个 DAG 调度节点实现完成（plan_create, plan_execute_dag, plan_supervise, plan_reorchestrate）
- [ ] `_build_subagent_context` 正确从上游节点继承结果
- [ ] `_dispatch_subagent` 复用 `SubagentExecutor.execute_async()` 机制
- [ ] PlanGraph 作为独立 StateGraph 构建，**不修改 lead_agent 的图定义**
- [ ] `plan_tool` 可被 lead_agent 调用，内部运行 PlanGraph
- [ ] DAG 节点并行执行（asyncio.gather）
- [ ] 条件边正确路由：plan_approved → execute, failed → reorchestrate, complete → END

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | plan_create_node | 返回 PlanDAG dict + plan_approved=False |
| 单元测试 | plan_execute_dag_node 单节点 | 节点状态 PENDING→RUNNING→COMPLETED |
| 单元测试 | plan_execute_dag_node 并行 | 多节点并行执行 |
| 单元测试 | plan_execute_dag_node 失败 | 节点状态→FAILED |
| 单元测试 | plan_supervise_node 验收通过 | 状态不变 |
| 单元测试 | plan_supervise_node 验收失败 | COMPLETED→FAILED |
| 单元测试 | _build_subagent_context | 包含上游结果 |
| 单元测试 | PlanGraph 条件边路由 | plan_approved=False→END |
| 单元测试 | plan_tool 调用 | 返回执行结果摘要 |
| 单元测试 | _dispatch_subagent 复用 SubagentExecutor | 调用 execute_async |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| PlanGraph 与 lead_agent 状态同步 | 中 | PlanState 独立，通过 plan_tool 隔离 |
| SubagentExecutor 在 PlanGraph 上下文中的事件循环冲突 | 中 | 使用 ThreadPoolExecutor 隔离 |
| plan_tool 阻塞 lead_agent 事件循环 | 中 | plan_tool 使用 sync wrapper，内部处理 async |
| PlanGraph 长时间运行超时 | 低 | 添加节点级超时控制 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第1节
- `backend/packages/harness/deerflow/tools/builtins/task_tool.py` - task_tool 实现模式参考
- `backend/packages/harness/deerflow/subagents/executor.py` - SubagentExecutor.execute_async() 参考
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py` - create_agent() 和工具注册
- `backend/packages/harness/deerflow/tools/tools.py` - get_available_tools 和工具列表
