from unittest.mock import AsyncMock, patch

import pytest

from deerflow.plan.graph import _route_after_create, _route_after_execute, _route_after_reorchestrate, _route_after_supervise, build_plan_graph
from deerflow.plan.graph_state import PlanState
from deerflow.plan.models import NodeStatus, PlanDAG, PlanNode


def _make_node(
    nid: str,
    title: str = "",
    description: str = "",
    dependencies: list[str] | None = None,
    status: NodeStatus = NodeStatus.PENDING,
    acceptance_criteria: list[str] | None = None,
    result: str | None = None,
    error: str | None = None,
    context_from: list[str] | None = None,
) -> PlanNode:
    return PlanNode(
        id=nid,
        title=title or nid,
        description=description or nid,
        dependencies=dependencies or [],
        status=status,
        acceptance_criteria=acceptance_criteria or [],
        result=result,
        error=error,
        context_from=context_from or [],
    )


def _make_dag(
    nodes: dict[str, PlanNode] | None = None,
    edges: list[list[str]] | None = None,
) -> PlanDAG:
    return PlanDAG(
        plan_id="test-plan",
        title="Test Plan",
        description="Test",
        goal="Test goal",
        nodes=nodes or {},
        edges=edges or [],
    )


class TestFullPlanLifecycle:
    @pytest.mark.asyncio
    async def test_full_plan_lifecycle(self):
        a = _make_node("A", description="步骤A")
        b = _make_node("B", description="步骤B", dependencies=["A"])
        dag = _make_dag(
            nodes={"A": a, "B": b},
            edges=[["A", "B"]],
        )

        with patch("deerflow.plan.nodes._dispatch_subagent", new_callable=AsyncMock, return_value="result"):
            state: PlanState = {
                "messages": [{"role": "user", "content": "测试任务"}],
                "plan": dag.model_dump(),
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }

            from deerflow.plan.nodes import plan_execute_dag_node

            result = await plan_execute_dag_node(state)
            plan = PlanDAG.model_validate(result["plan"])
            assert plan.nodes["A"].status == NodeStatus.COMPLETED

            state["plan"] = plan.model_dump()
            result = await plan_execute_dag_node(state)
            plan = PlanDAG.model_validate(result["plan"])
            assert plan.nodes["B"].status == NodeStatus.COMPLETED
            assert plan.is_complete()


class TestPlanWithApprovalRejection:
    def test_plan_not_approved_routes_to_end(self):
        state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": False,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_create(state)
        assert result == "__end__"

    def test_plan_approved_routes_to_execute(self):
        a = _make_node("A")
        dag = _make_dag(nodes={"A": a})
        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_create(state)
        assert result == "plan_execute_dag"


class TestPlanWithFailureAndRetry:
    @pytest.mark.asyncio
    async def test_plan_with_failure_and_retry(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err")
        dag = _make_dag(nodes={"A": a})

        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }

        from deerflow.plan.nodes import plan_reorchestrate_node

        result = await plan_reorchestrate_node(state)
        updated_plan = PlanDAG.model_validate(result["plan"])
        assert updated_plan.nodes["A"].status == NodeStatus.PENDING
        assert result["plan_revised"] is True

        with patch("deerflow.plan.nodes._dispatch_subagent", new_callable=AsyncMock, return_value="success"):
            state["plan"] = updated_plan.model_dump()
            state["plan_revised"] = None

            from deerflow.plan.nodes import plan_execute_dag_node

            result = await plan_execute_dag_node(state)
            final_plan = PlanDAG.model_validate(result["plan"])
            assert final_plan.nodes["A"].status == NodeStatus.COMPLETED
            assert final_plan.nodes["A"].result == "success"


class TestPlanApiCRUD:
    def test_create_dag(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(
            nodes={"A": a, "B": b},
            edges=[["A", "B"]],
        )
        assert dag.plan_id == "test-plan"
        assert len(dag.nodes) == 2
        assert dag.edges == [["A", "B"]]

    def test_read_dag_state(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="done")
        dag = _make_dag(nodes={"A": a})
        assert dag.nodes["A"].status == NodeStatus.COMPLETED
        assert dag.nodes["A"].result == "done"

    def test_update_dag_state(self):
        a = _make_node("A")
        dag = _make_dag(nodes={"A": a})
        dag.nodes["A"].status = NodeStatus.COMPLETED
        dag.nodes["A"].result = "done"
        assert dag.nodes["A"].status == NodeStatus.COMPLETED

    def test_delete_node(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        del dag.nodes["B"]
        dag.edges = []
        assert "B" not in dag.nodes
        assert len(dag.edges) == 0


class TestPlanProgressSSE:
    @pytest.mark.asyncio
    async def test_plan_progress_tracking(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])

        with patch("deerflow.plan.nodes._dispatch_subagent", new_callable=AsyncMock, return_value="result_A"):
            state: PlanState = {
                "messages": [],
                "plan": dag.model_dump(),
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }

            from deerflow.plan.nodes import plan_execute_dag_node

            result = await plan_execute_dag_node(state)
            plan = PlanDAG.model_validate(result["plan"])

            completed = sum(1 for n in plan.nodes.values() if n.status == NodeStatus.COMPLETED)
            total = len(plan.nodes)
            assert completed == 1
            assert total == 2


class TestPlanToolInvocation:
    @pytest.mark.asyncio
    async def test_plan_tool_invocation(self):
        from deerflow.plan.plan_tool import _arun_plan

        mock_plan = _make_dag(
            nodes={"A": _make_node("A"), "B": _make_node("B", dependencies=["A"])},
            edges=[["A", "B"]],
        )

        with patch("deerflow.plan.graph.plan_graph") as mock_graph:
            async def mock_astream(initial_state, config=None):
                yield {
                    "plan_create": {
                        "messages": [{"role": "assistant", "content": "Plan 已生成"}],
                        "plan": mock_plan.model_dump(),
                        "plan_approved": True,
                        "active_node_ids": None,
                        "plan_revised": None,
                    }
                }

            mock_graph.astream = mock_astream

            initial_state: PlanState = {
                "messages": [{"role": "user", "content": "测试任务"}],
                "plan": None,
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }

            result = await _arun_plan(initial_state)
            assert result is not None


class TestPlanGraphIndependentState:
    def test_plan_state_independent(self):
        plan_state: PlanState = {
            "messages": [{"role": "user", "content": "plan message"}],
            "plan": None,
            "plan_approved": False,
            "active_node_ids": None,
            "plan_revised": None,
        }

        assert "plan" in plan_state
        assert plan_state["plan"] is None
        assert plan_state["plan_approved"] is False

    def test_plan_state_does_not_contain_thread_fields(self):
        plan_state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": None,
            "active_node_ids": None,
            "plan_revised": None,
        }

        thread_specific_fields = {"sandbox", "thread_data", "title", "artifacts", "todos", "uploaded_files", "viewed_images"}
        for field in thread_specific_fields:
            assert field not in plan_state


class TestRouteAfterExecute:
    def test_route_failed_to_reorchestrate(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err")
        dag = _make_dag(nodes={"A": a})
        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_execute(state)
        assert result == "plan_reorchestrate"

    def test_route_incomplete_to_supervise(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="ok")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_execute(state)
        assert result == "plan_supervise"

    def test_route_complete_to_end(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="ok")
        dag = _make_dag(nodes={"A": a})
        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_execute(state)
        assert result == "__end__"

    def test_route_no_plan_to_end(self):
        state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_execute(state)
        assert result == "__end__"


class TestRouteAfterReorchestrate:
    def test_route_revised_to_execute(self):
        state: PlanState = {
            "messages": [],
            "plan": {},
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": True,
        }
        result = _route_after_reorchestrate(state)
        assert result == "plan_execute_dag"

    def test_route_not_revised_to_end(self):
        state: PlanState = {
            "messages": [],
            "plan": {},
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": False,
        }
        result = _route_after_reorchestrate(state)
        assert result == "__end__"


class TestRouteAfterSupervise:
    def test_route_failed_to_reorchestrate(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="验收标准未通过")
        dag = _make_dag(nodes={"A": a})
        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_supervise(state)
        assert result == "plan_reorchestrate"

    def test_route_no_failed_to_execute(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="ok")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_supervise(state)
        assert result == "plan_execute_dag"

    def test_route_no_plan_to_end(self):
        state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = _route_after_supervise(state)
        assert result == "__end__"


class TestBuildPlanGraph:
    def test_build_plan_graph(self):
        graph = build_plan_graph()
        assert graph is not None

    def test_plan_graph_has_nodes(self):
        graph = build_plan_graph()
        node_names = set(graph.nodes.keys())
        expected_nodes = {"plan_create", "plan_execute_dag", "plan_supervise", "plan_reorchestrate"}
        assert expected_nodes.issubset(node_names)

    def test_plan_graph_entry_point(self):
        graph = build_plan_graph()
        assert "plan_create" in graph.nodes


class TestPlanToolFunction:
    def test_plan_tool_is_callable(self):
        from deerflow.plan.plan_tool import plan_tool

        assert hasattr(plan_tool, "func")
        assert plan_tool.func is not None

    def test_plan_tool_has_description(self):
        from deerflow.plan.plan_tool import plan_tool

        assert plan_tool.description is not None
        assert len(plan_tool.description) > 0

    def test_plan_tool_input_schema(self):
        from deerflow.plan.plan_tool import PlanToolInput

        schema = PlanToolInput.model_json_schema()
        assert "prompt" in schema["properties"]
        assert "auto_approve" in schema["properties"]


class TestPlanGraphStateMerge:
    def test_merge_dict_both_none(self):
        from deerflow.plan.graph_state import merge_dict

        assert merge_dict(None, None) == {}

    def test_merge_dict_existing_none(self):
        from deerflow.plan.graph_state import merge_dict

        assert merge_dict(None, {"a": 1}) == {"a": 1}

    def test_merge_dict_new_none(self):
        from deerflow.plan.graph_state import merge_dict

        assert merge_dict({"a": 1}, None) == {"a": 1}

    def test_merge_dict_both_present(self):
        from deerflow.plan.graph_state import merge_dict

        result = merge_dict({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_merge_dict_override(self):
        from deerflow.plan.graph_state import merge_dict

        result = merge_dict({"a": 1}, {"a": 2})
        assert result == {"a": 2}
