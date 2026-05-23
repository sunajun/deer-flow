from collections import deque
from datetime import datetime

from langchain_core.language_models import BaseChatModel

from deerflow.plan.models import NodeStatus, PlanDAG, PlanNode


def _find_downstream(plan: PlanDAG, failed_nodes: list[PlanNode]) -> set[str]:
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


class PlanEngine:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def create_from_intent(self, messages: list) -> PlanDAG:
        structured_llm = self.llm.with_structured_output(PlanDAG)
        plan = await structured_llm.ainvoke(messages)
        errors = self.validate_dag(plan)
        if errors:
            raise ValueError(f"生成的 Plan 校验失败：{'; '.join(errors)}")
        return plan

    async def verify_acceptance(self, node: PlanNode) -> bool:
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

    async def reorchestrate(self, plan: PlanDAG, failed_nodes: list[PlanNode]) -> PlanDAG:
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
