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
