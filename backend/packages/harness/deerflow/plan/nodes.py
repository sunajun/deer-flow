import asyncio
import logging
from datetime import datetime
from typing import Any

from deerflow.plan.engine import PlanEngine
from deerflow.plan.graph_state import PlanState
from deerflow.plan.models import NodeStatus, PlanDAG, PlanNode

logger = logging.getLogger(__name__)


async def plan_create_node(state: PlanState) -> dict:
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


async def plan_execute_dag_node(state: PlanState) -> dict:
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


def _build_subagent_context(plan: PlanDAG, node: PlanNode) -> dict:
    context = {
        "task_description": node.description,
        "acceptance_criteria": node.acceptance_criteria,
    }
    for upstream_id in node.context_from:
        if upstream_id in plan.nodes and plan.nodes[upstream_id].result:
            context[f"upstream_{upstream_id}_result"] = plan.nodes[upstream_id].result
    return context


async def _dispatch_subagent(node: PlanNode, context: dict) -> Any:
    from deerflow.config import get_app_config
    from deerflow.subagents import get_subagent_config
    from deerflow.subagents.executor import SubagentExecutor, get_background_task_result

    app_config = get_app_config()
    subagent_config = get_subagent_config(node.assignee, app_config=app_config)
    if subagent_config is None:
        raise ValueError(f"未找到子代理配置：{node.assignee}")

    from deerflow.tools import get_available_tools

    tools = get_available_tools(subagent_enabled=False, app_config=app_config)

    executor = SubagentExecutor(
        config=subagent_config,
        tools=tools,
        app_config=app_config,
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
        if result is None:
            await asyncio.sleep(1)
            continue
        if result.status.value in ("completed", "failed", "timed_out", "cancelled"):
            if result.status.value == "failed":
                raise RuntimeError(f"子代理执行失败：{result.error}")
            if result.status.value in ("timed_out", "cancelled"):
                raise TimeoutError(f"子代理执行超时或取消：{node.timeout_seconds}s")
            return result.result
        await asyncio.sleep(1)


async def plan_supervise_node(state: PlanState) -> dict:
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
