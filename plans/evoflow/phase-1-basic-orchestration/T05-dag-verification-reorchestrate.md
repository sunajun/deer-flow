# T05 - DAG 验收校验、重编排与 API

## 元信息
- **任务ID**: T05
- **阶段**: 第1期 - 基础编排增强
- **优先级**: P3
- **预估工期**: 3 天
- **依赖任务**: T04
- **关联差距**: 差距1 - 显式 DAG 编排

## 目标
实现 PlanEngine 的验收校验和重编排逻辑，创建 Plan CRUD API，使 DAG 编排可通过 REST API 操作。

## 详细实现步骤

### 步骤1: 实现 create_from_intent
- **文件**: `backend/packages/harness/deerflow/plan/engine.py`
- **操作**: 续写
- **内容**: LLM 结构化输出生成 PlanDAG
```python
async def create_from_intent(self, messages: list) -> PlanDAG:
    """从用户意图生成 PlanDAG。"""
    structured_llm = self.llm.with_structured_output(PlanDAG)
    plan = await structured_llm.ainvoke(messages)
    errors = self.validate_dag(plan)
    if errors:
        raise ValueError(f"生成的 Plan 校验失败：{'; '.join(errors)}")
    return plan
```
- **验收**: 从自然语言输入生成有效的 PlanDAG

### 步骤2: 实现 verify_acceptance
- **文件**: `backend/packages/harness/deerflow/plan/engine.py`
- **操作**: 续写
- **内容**: 校验节点结果是否满足验收标准
```python
async def verify_acceptance(self, node: PlanNode) -> bool:
    """校验节点结果是否满足验收标准。"""
    if not node.acceptance_criteria:
        return True
    criteria_text = "\n".join(f"- {c}" for c in node.acceptance_criteria)
    prompt = (
        f"请判断以下执行结果是否满足所有验收标准。\n"
        f"验收标准：\n{criteria_text}\n"
        f"执行结果：{node.result}\n"
        f"请仅回答 YES 或 NO。"
    )
    response = await self.llm.ainvoke(prompt)
    answer = response.content.strip().upper()
    return answer.startswith("YES")
```
- **验收**: 可判断节点结果是否满足预设验收标准

### 步骤3: 实现 reorchestrate
- **文件**: `backend/packages/harness/deerflow/plan/engine.py`
- **操作**: 续写
- **内容**: 局部重编排
```python
async def reorchestrate(self, plan: PlanDAG, failed_nodes: list[PlanNode]) -> PlanDAG:
    """局部重编排：仅调整失败节点及其下游。"""
    downstream = _find_downstream(plan, failed_nodes)
    for node_id in downstream:
        plan.nodes[node_id].status = NodeStatus.PENDING
        plan.nodes[node_id].result = None
        plan.nodes[node_id].error = None
    for failed in failed_nodes:
        plan.nodes[failed.id].status = NodeStatus.PENDING
        plan.nodes[failed.id].result = None
        plan.nodes[failed.id].error = None
    plan.updated_at = datetime.now()
    return plan
```
- **验收**: 仅失败节点及其下游被重置，其余节点保留

### 步骤4: 实现 _find_downstream 辅助函数
- **文件**: `backend/packages/harness/deerflow/plan/engine.py`
- **操作**: 续写
- **内容**: 沿 edges 查找失败节点的所有下游。**关键修正**: 使用 `collections.deque` 替代 `list.pop(0)`，避免 O(n) 的队列操作。
```python
from collections import deque


def _find_downstream(plan: PlanDAG, failed_nodes: list[PlanNode]) -> set[str]:
    """BFS 查找所有下游节点，使用 deque 保证 O(1) popleft。"""
    failed_ids = {n.id for n in failed_nodes}
    downstream: set[str] = set()
    queue: deque[str] = deque(failed_ids)
    while queue:
        current = queue.popleft()
        for from_id, to_id in plan.edges:
            if from_id == current and to_id not in failed_ids and to_id not in downstream:
                downstream.add(to_id)
                queue.append(to_id)
    return downstream
```
- **验收**: 正确找到所有直接和间接下游，使用 deque 保证性能

### 步骤5: 创建 Plan API 路由
- **文件**: `backend/app/gateway/routers/plans.py`
- **操作**: 新建
- **内容**: 完整 CRUD API。**注意**: 使用独立的 `plans.py` 路由文件，不要修改已有的 `agents.py` 路由。
```python
import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deerflow.plan.engine import PlanEngine
from deerflow.plan.models import PlanDAG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanCreateRequest(BaseModel):
    prompt: str = Field(..., description="用户意图描述")
    auto_approve: bool = Field(default=False, description="是否自动确认")


class PlanResponse(BaseModel):
    plan_id: str
    title: str
    status: str
    nodes: dict
    edges: list


@router.post("/")
async def create_plan(request: PlanCreateRequest) -> PlanResponse: ...


@router.get("/{plan_id}")
async def get_plan(plan_id: str) -> PlanResponse: ...


@router.post("/{plan_id}/approve")
async def approve_plan(plan_id: str) -> PlanResponse: ...


@router.post("/{plan_id}/nodes/{node_id}/retry")
async def retry_node(plan_id: str, node_id: str) -> PlanResponse: ...


@router.post("/{plan_id}/reorchestrate")
async def reorchestrate_plan(plan_id: str) -> PlanResponse: ...


@router.get("/{plan_id}/progress")
async def plan_progress(plan_id: str): ...
```
- **验收**: API 端点可访问，返回正确响应

### 步骤6: 实现进度 SSE 推送
- **文件**: `backend/app/gateway/routers/plans.py`
- **操作**: 续写
- **内容**: SSE 流式推送 DAG 执行进度
```python
from sse_starlette.sse import EventSourceResponse


@router.get("/{plan_id}/progress")
async def plan_progress(plan_id: str):
    async def event_generator():
        while True:
            plan = await _get_plan(plan_id)
            if plan is None:
                yield {"event": "plan_error", "data": "Plan not found"}
                break
            yield {"event": "plan_progress", "data": plan.model_dump_json()}
            if plan.is_complete() or plan.get_failed_nodes():
                break
            await asyncio.sleep(1)
    return EventSourceResponse(event_generator())
```
- **验收**: SSE 流正确推送进度事件

### 步骤7: 集成到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 函数中使用 `app.include_router()` 注册 plans router。**注意**: Gateway 使用 `lifespan` 上下文管理器（不是 `@app.on_event("startup")`），路由注册在 `create_app()` 函数中。
```python
from app.gateway.routers import plans

app.include_router(plans.router)
```
- **验收**: API 在 Gateway 启动后可访问

## 验收标准
- [ ] create_from_intent 可从自然语言生成有效 PlanDAG
- [ ] verify_acceptance 可判断验收通过/不通过
- [ ] reorchestrate 仅重置失败节点及其下游
- [ ] `_find_downstream` 使用 `collections.deque`，正确递归查找
- [ ] 6 个 API 端点全部可访问（plans.py 独立路由文件）
- [ ] SSE 进度推送正常工作
- [ ] 路由通过 `app.include_router()` 注册到 `create_app()`

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | verify_acceptance 无标准 | 返回 True |
| 单元测试 | verify_acceptance 满足标准 | 返回 True |
| 单元测试 | verify_acceptance 不满足 | 返回 False |
| 单元测试 | _find_downstream 直接下游 | 返回下游节点集 |
| 单元测试 | _find_downstream 间接下游 | 递归查找正确 |
| 单元测试 | _find_downstream 使用 deque | 性能 O(V+E) |
| 单元测试 | reorchestrate | 失败+下游重置，其余保留 |
| 集成测试 | POST /api/plans | 返回 plan_id |
| 集成测试 | POST /api/plans/{id}/approve | plan_approved=True |
| 集成测试 | GET /api/plans/{id}/progress | SSE 流 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| LLM 结构化输出不稳定 | 中 | 增加重试 + 回退机制 |
| 验收校验 LLM 幻觉 | 中 | 多次校验取多数 |
| 重编排策略选择不当 | 中 | 提供策略可配置 |
| SSE 连接泄漏 | 低 | 设置超时和心跳 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第1节
- `backend/app/gateway/app.py` - create_app() 和 include_router 模式
- `backend/app/gateway/routers/agents.py` - 已有路由文件参考（新路由使用 plans.py）
