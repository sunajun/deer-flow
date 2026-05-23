import asyncio
import concurrent.futures
import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from deerflow.plan.graph_state import PlanState

logger = logging.getLogger(__name__)


class PlanToolInput(BaseModel):
    prompt: str = Field(description="用户意图描述，用于生成 Plan DAG")
    auto_approve: bool = Field(default=False, description="是否自动确认 Plan")


@tool(args_schema=PlanToolInput)
def plan_tool(prompt: str, auto_approve: bool = False) -> str:
    """创建并执行 DAG 编排计划。将复杂任务拆分为多个子任务，按依赖关系并行执行。"""
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
    from deerflow.plan.graph import plan_graph

    config = {"configurable": {"thread_id": f"plan_{id(initial_state)}"}}
    final_state = None
    async for event in plan_graph.astream(initial_state, config=config):
        final_state = event
    return final_state or {}
