from langchain_core.language_models import BaseChatModel

from deerflow.plan.models import PlanDAG, PlanNode


class PlanEngine:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def create_from_intent(self, messages: list) -> PlanDAG:
        raise NotImplementedError

    async def verify_acceptance(self, node: PlanNode) -> bool:
        raise NotImplementedError

    async def reorchestrate(self, plan: PlanDAG, failed_nodes: list[PlanNode]) -> PlanDAG:
        raise NotImplementedError

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
