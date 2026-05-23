import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from deerflow.models.factory import create_chat_model
from deerflow.plan.engine import PlanEngine
from deerflow.plan.models import NodeStatus, PlanDAG, PlanNode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["plans"])

_plan_store: dict[str, PlanDAG] = {}


class PlanCreateRequest(BaseModel):
    prompt: str = Field(..., description="用户意图描述")
    auto_approve: bool = Field(default=False, description="是否自动确认")


class PlanResponse(BaseModel):
    plan_id: str
    title: str
    status: str
    nodes: dict[str, Any]
    edges: list[list[str]]


class PlanApproveResponse(BaseModel):
    plan_id: str
    approved: bool


class NodeRetryResponse(BaseModel):
    plan_id: str
    node_id: str
    status: str


class PlanProgressEvent(BaseModel):
    plan_id: str
    status: str
    completed: int
    total: int
    failed: int


def _plan_to_response(plan: PlanDAG) -> PlanResponse:
    return PlanResponse(
        plan_id=plan.plan_id,
        title=plan.title,
        status=plan.status,
        nodes={nid: node.model_dump() for nid, node in plan.nodes.items()},
        edges=plan.edges,
    )


def _get_plan_or_404(plan_id: str) -> PlanDAG:
    plan = _plan_store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
    return plan


def _get_plan_engine() -> PlanEngine:
    llm = create_chat_model()
    return PlanEngine(llm=llm)


@router.post("/", response_model=PlanResponse, summary="Create Plan", description="从用户意图创建 PlanDAG")
async def create_plan(request: PlanCreateRequest) -> PlanResponse:
    engine = _get_plan_engine()
    messages = [{"role": "user", "content": request.prompt}]
    try:
        plan = await engine.create_from_intent(messages)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to create plan from intent: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create plan: {e}") from e

    if not plan.plan_id:
        plan.plan_id = str(uuid.uuid4())
    _plan_store[plan.plan_id] = plan
    return _plan_to_response(plan)


@router.get("/{plan_id}", response_model=PlanResponse, summary="Get Plan", description="获取 PlanDAG 详情")
async def get_plan(plan_id: str) -> PlanResponse:
    plan = _get_plan_or_404(plan_id)
    return _plan_to_response(plan)


@router.post("/{plan_id}/approve", response_model=PlanApproveResponse, summary="Approve Plan", description="确认 Plan 开始执行")
async def approve_plan(plan_id: str) -> PlanApproveResponse:
    plan = _get_plan_or_404(plan_id)
    plan.status = NodeStatus.RUNNING
    return PlanApproveResponse(plan_id=plan_id, approved=True)


@router.post("/{plan_id}/nodes/{node_id}/retry", response_model=NodeRetryResponse, summary="Retry Node", description="重试失败节点")
async def retry_node(plan_id: str, node_id: str) -> NodeRetryResponse:
    plan = _get_plan_or_404(plan_id)
    if node_id not in plan.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in plan '{plan_id}'")
    node = plan.nodes[node_id]
    if node.status != NodeStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Node '{node_id}' is not in FAILED status, cannot retry")
    node.status = NodeStatus.PENDING
    node.result = None
    node.error = None
    return NodeRetryResponse(plan_id=plan_id, node_id=node_id, status=node.status)


@router.post("/{plan_id}/reorchestrate", response_model=PlanResponse, summary="Reorchestrate Plan", description="局部重编排：重置失败节点及其下游")
async def reorchestrate_plan(plan_id: str) -> PlanResponse:
    plan = _get_plan_or_404(plan_id)
    failed_nodes = plan.get_failed_nodes()
    if not failed_nodes:
        return _plan_to_response(plan)
    engine = _get_plan_engine()
    plan = await engine.reorchestrate(plan, failed_nodes)
    _plan_store[plan_id] = plan
    return _plan_to_response(plan)


@router.get("/{plan_id}/progress", summary="Plan Progress", description="SSE 流式推送 DAG 执行进度")
async def plan_progress(plan_id: str) -> EventSourceResponse:
    async def event_generator():
        while True:
            plan = _plan_store.get(plan_id)
            if plan is None:
                yield {"event": "plan_error", "data": "Plan not found"}
                break
            total = len(plan.nodes)
            completed = sum(1 for n in plan.nodes.values() if n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED))
            failed = len(plan.get_failed_nodes())
            progress = PlanProgressEvent(
                plan_id=plan_id,
                status=plan.status,
                completed=completed,
                total=total,
                failed=failed,
            )
            yield {"event": "plan_progress", "data": progress.model_dump_json()}
            if plan.is_complete() or plan.get_failed_nodes():
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
