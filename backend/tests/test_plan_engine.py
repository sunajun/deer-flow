from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deerflow.plan.engine import PlanEngine, _find_downstream
from deerflow.plan.graph_state import PlanState
from deerflow.plan.models import BarrierType, NodeStatus, PlanDAG, PlanNode
from deerflow.plan.nodes import (
    _build_subagent_context,
    _dispatch_subagent,
    plan_execute_dag_node,
    plan_reorchestrate_node,
    plan_supervise_node,
)


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
    barrier_type: BarrierType = BarrierType.ALL,
    assignee: str = "general-purpose",
    timeout_seconds: int = 900,
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
        barrier_type=barrier_type,
        assignee=assignee,
        timeout_seconds=timeout_seconds,
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


class TestFindDownstream:
    def test_no_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        dag = _make_dag(nodes={"A": a})
        result = _find_downstream(dag, [a])
        assert result == set()

    def test_direct_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        result = _find_downstream(dag, [a])
        assert result == {"B"}

    def test_indirect_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["B"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c},
            edges=[["A", "B"], ["B", "C"]],
        )
        result = _find_downstream(dag, [a])
        assert result == {"B", "C"}

    def test_parallel_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["A"])
        d = _make_node("D", dependencies=["B", "C"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d},
            edges=[["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"]],
        )
        result = _find_downstream(dag, [a])
        assert result == {"B", "C", "D"}

    def test_multiple_failed_nodes(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", status=NodeStatus.FAILED)
        c = _make_node("C", dependencies=["A"])
        d = _make_node("D", dependencies=["B"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d},
            edges=[["A", "C"], ["B", "D"]],
        )
        result = _find_downstream(dag, [a, b])
        assert result == {"C", "D"}

    def test_failed_node_not_in_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", status=NodeStatus.FAILED, dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        result = _find_downstream(dag, [a, b])
        assert result == set()

    def test_uses_deque(self):
        import inspect

        source = inspect.getsource(_find_downstream)
        assert "deque" in source
        assert "list.pop(0)" not in source


class TestVerifyAcceptance:
    @pytest.mark.asyncio
    async def test_no_criteria_returns_true(self):
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=[], result="some result")
        assert await engine.verify_acceptance(node) is True

    @pytest.mark.asyncio
    async def test_criteria_satisfied(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="YES"))
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=["结果包含数据"], result="包含数据的结果")
        assert await engine.verify_acceptance(node) is True

    @pytest.mark.asyncio
    async def test_criteria_not_satisfied(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="NO"))
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=["结果必须为正数"], result="-5")
        assert await engine.verify_acceptance(node) is False

    @pytest.mark.asyncio
    async def test_criteria_yes_with_extra_text(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="YES, the result meets all criteria"))
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=["结果正确"], result="正确结果")
        assert await engine.verify_acceptance(node) is True

    @pytest.mark.asyncio
    async def test_criteria_whitespace_handling(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="  yes  "))
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=["结果正确"], result="正确结果")
        assert await engine.verify_acceptance(node) is True


class TestReorchestrate:
    @pytest.mark.asyncio
    async def test_resets_failed_and_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err", result="bad")
        b = _make_node("B", dependencies=["A"], status=NodeStatus.COMPLETED, result="ok")
        c = _make_node("C", status=NodeStatus.COMPLETED, result="ok")
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c},
            edges=[["A", "B"]],
        )
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a])

        assert result.nodes["A"].status == NodeStatus.PENDING
        assert result.nodes["A"].result is None
        assert result.nodes["A"].error is None

        assert result.nodes["B"].status == NodeStatus.PENDING
        assert result.nodes["B"].result is None
        assert result.nodes["B"].error is None

        assert result.nodes["C"].status == NodeStatus.COMPLETED
        assert result.nodes["C"].result == "ok"

    @pytest.mark.asyncio
    async def test_no_failed_nodes_no_change(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="ok")
        dag = _make_dag(nodes={"A": a})
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [])
        assert result.nodes["A"].status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_updates_timestamp(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err")
        dag = _make_dag(nodes={"A": a})
        old_updated = dag.updated_at
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a])
        assert result.updated_at >= old_updated

    @pytest.mark.asyncio
    async def test_multiple_failed_with_shared_downstream(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err")
        b = _make_node("B", status=NodeStatus.FAILED, error="err")
        c = _make_node("C", dependencies=["A", "B"], status=NodeStatus.COMPLETED, result="ok")
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c},
            edges=[["A", "C"], ["B", "C"]],
        )
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a, b])

        assert result.nodes["A"].status == NodeStatus.PENDING
        assert result.nodes["B"].status == NodeStatus.PENDING
        assert result.nodes["C"].status == NodeStatus.PENDING


class TestCreateFromIntent:
    @pytest.mark.asyncio
    async def test_valid_plan_created(self):
        mock_plan = _make_dag(
            nodes={"A": _make_node("A"), "B": _make_node("B", dependencies=["A"])},
            edges=[["A", "B"]],
        )
        llm = MagicMock()
        structured_llm = AsyncMock()
        structured_llm.ainvoke = AsyncMock(return_value=mock_plan)
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        engine = PlanEngine(llm=llm)
        result = await engine.create_from_intent([{"role": "user", "content": "test"}])
        assert result.plan_id == "test-plan"
        assert "A" in result.nodes

    @pytest.mark.asyncio
    async def test_invalid_plan_raises(self):
        a = _make_node("A", dependencies=["Z"])
        mock_plan = _make_dag(nodes={"A": a})
        llm = MagicMock()
        structured_llm = AsyncMock()
        structured_llm.ainvoke = AsyncMock(return_value=mock_plan)
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        engine = PlanEngine(llm=llm)
        with pytest.raises(ValueError, match="校验失败"):
            await engine.create_from_intent([{"role": "user", "content": "test"}])


class TestCreateFromIntentSimple:
    @pytest.mark.asyncio
    async def test_simple_task_split(self):
        mock_plan = _make_dag(
            nodes={
                "A": _make_node("A", description="步骤1"),
                "B": _make_node("B", description="步骤2", dependencies=["A"]),
            },
            edges=[["A", "B"]],
        )
        llm = MagicMock()
        structured_llm = AsyncMock()
        structured_llm.ainvoke = AsyncMock(return_value=mock_plan)
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        engine = PlanEngine(llm=llm)
        result = await engine.create_from_intent([{"role": "user", "content": "简单任务"}])
        assert len(result.nodes) == 2
        assert result.nodes["B"].dependencies == ["A"]


class TestCreateFromIntentComplex:
    @pytest.mark.asyncio
    async def test_complex_multi_step_task(self):
        mock_plan = _make_dag(
            nodes={
                "research": _make_node("research", description="调研"),
                "design": _make_node("design", description="设计", dependencies=["research"]),
                "implement": _make_node("implement", description="实现", dependencies=["design"]),
                "test": _make_node("test", description="测试", dependencies=["implement"]),
                "deploy": _make_node("deploy", description="部署", dependencies=["test"]),
            },
            edges=[["research", "design"], ["design", "implement"], ["implement", "test"], ["test", "deploy"]],
        )
        llm = MagicMock()
        structured_llm = AsyncMock()
        structured_llm.ainvoke = AsyncMock(return_value=mock_plan)
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        engine = PlanEngine(llm=llm)
        result = await engine.create_from_intent([{"role": "user", "content": "复杂多步骤任务"}])
        assert len(result.nodes) == 5
        assert result.nodes["deploy"].dependencies == ["test"]


class TestVerifyAcceptancePass:
    @pytest.mark.asyncio
    async def test_verify_acceptance_pass(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="YES"))
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=["输出非空"], result="有内容的结果")
        assert await engine.verify_acceptance(node) is True


class TestVerifyAcceptanceFail:
    @pytest.mark.asyncio
    async def test_verify_acceptance_fail(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="NO"))
        engine = PlanEngine(llm=llm)
        node = _make_node("A", acceptance_criteria=["必须返回正数"], result="-1")
        assert await engine.verify_acceptance(node) is False


class TestReorchestrateRetry:
    @pytest.mark.asyncio
    async def test_reorchestrate_retry(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="timeout")
        dag = _make_dag(nodes={"A": a})
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a])
        assert result.nodes["A"].status == NodeStatus.PENDING
        assert result.nodes["A"].error is None
        assert result.nodes["A"].result is None


class TestReorchestrateSplit:
    @pytest.mark.asyncio
    async def test_reorchestrate_split(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="too complex")
        b = _make_node("B", dependencies=["A"], status=NodeStatus.PENDING)
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a])
        assert result.nodes["A"].status == NodeStatus.PENDING
        assert result.nodes["B"].status == NodeStatus.PENDING


class TestReorchestrateChangeAssignee:
    @pytest.mark.asyncio
    async def test_reorchestrate_change_assignee(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="agent failed", assignee="researcher")
        dag = _make_dag(nodes={"A": a})
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a])
        assert result.nodes["A"].status == NodeStatus.PENDING
        assert result.nodes["A"].assignee == "researcher"


class TestFindDownstreamDirect:
    def test_find_downstream_direct(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        result = _find_downstream(dag, [a])
        assert result == {"B"}


class TestFindDownstreamTransitive:
    def test_find_downstream_transitive(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["B"])
        d = _make_node("D", dependencies=["C"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d},
            edges=[["A", "B"], ["B", "C"], ["C", "D"]],
        )
        result = _find_downstream(dag, [a])
        assert result == {"B", "C", "D"}


class TestFindDownstreamDiamond:
    def test_find_downstream_diamond(self):
        a = _make_node("A", status=NodeStatus.FAILED)
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["A"])
        d = _make_node("D", dependencies=["B", "C"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d},
            edges=[["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"]],
        )
        result = _find_downstream(dag, [a])
        assert result == {"B", "C", "D"}


class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="done_a")
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["A"])
        d = _make_node("D", dependencies=["B", "C"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d},
            edges=[["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"]],
        )
        ready = dag.get_ready_nodes()
        assert set(n.id for n in ready) == {"B", "C"}

        for node in ready:
            node.status = NodeStatus.COMPLETED
            node.result = f"done_{node.id.lower()}"

        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["D"]


class TestContextPassing:
    def test_context_passing(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="result_A")
        b = _make_node("B", dependencies=["A"], status=NodeStatus.COMPLETED, result="result_B")
        d = _make_node("D", dependencies=["B"], context_from=["B"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "D": d},
            edges=[["A", "B"], ["B", "D"]],
        )
        context = _build_subagent_context(dag, d)
        assert context["upstream_B_result"] == "result_B"


class TestContextFromMultiple:
    def test_context_from_multiple(self):
        b = _make_node("B", status=NodeStatus.COMPLETED, result="result_B")
        c = _make_node("C", status=NodeStatus.COMPLETED, result="result_C")
        d = _make_node("D", dependencies=["B", "C"], context_from=["B", "C"])
        dag = _make_dag(
            nodes={"B": b, "C": c, "D": d},
            edges=[["B", "D"], ["C", "D"]],
        )
        context = _build_subagent_context(dag, d)
        assert context["upstream_B_result"] == "result_B"
        assert context["upstream_C_result"] == "result_C"


class TestLinearExecution:
    def test_linear_execution(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["B"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c},
            edges=[["A", "B"], ["B", "C"]],
        )
        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["A"]

        dag.nodes["A"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["B"]

        dag.nodes["B"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["C"]


class TestMixedExecution:
    def test_mixed_execution(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["A"])
        d = _make_node("D", dependencies=["B"])
        e = _make_node("E", dependencies=["B", "C"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d, "E": e},
            edges=[["A", "B"], ["A", "C"], ["B", "D"], ["B", "E"], ["C", "E"]],
        )
        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["A"]

        dag.nodes["A"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert set(n.id for n in ready) == {"B", "C"}

        dag.nodes["B"].status = NodeStatus.COMPLETED
        dag.nodes["C"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert set(n.id for n in ready) == {"D", "E"}


class TestDispatchSubagentUsesExecutor:
    @pytest.mark.asyncio
    async def test_dispatch_subagent_uses_executor(self):
        node = _make_node("A", description="测试任务", assignee="general-purpose")
        context = {"task_description": "测试任务", "acceptance_criteria": []}

        mock_executor_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "completed"
        mock_result.result = "task completed"
        mock_result.error = None

        mock_get_config = MagicMock()
        mock_get_subagent = MagicMock(return_value=MagicMock())
        mock_get_tools = MagicMock(return_value=[])

        task_id = "test_task_123"
        mock_executor_instance.execute_async.return_value = task_id

        call_count = 0

        def side_effect(tid):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                return mock_result
            return None

        with patch("deerflow.config.get_app_config", return_value=mock_get_config), \
             patch("deerflow.subagents.get_subagent_config", mock_get_subagent), \
             patch("deerflow.tools.get_available_tools", mock_get_tools), \
             patch("deerflow.subagents.executor.SubagentExecutor", return_value=mock_executor_instance), \
             patch("deerflow.subagents.executor.get_background_task_result", side_effect=side_effect):

            result = await _dispatch_subagent(node, context)

            mock_executor_instance.execute_async.assert_called_once()
            assert result == "task completed"


class TestSingleNodeFailure:
    @pytest.mark.asyncio
    async def test_single_node_failure(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="执行失败")
        dag = _make_dag(nodes={"A": a})
        assert dag.get_failed_nodes() == [a]
        assert len(dag.get_failed_nodes()) == 1


class TestCascadingFailure:
    @pytest.mark.asyncio
    async def test_cascading_failure(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="执行失败")
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["B"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c},
            edges=[["A", "B"], ["B", "C"]],
        )
        ready = dag.get_ready_nodes()
        assert all(n.id != "B" for n in ready)
        assert all(n.id != "C" for n in ready)


class TestReorchestrateAfterFailure:
    @pytest.mark.asyncio
    async def test_reorchestrate_after_failure(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err")
        b = _make_node("B", dependencies=["A"], status=NodeStatus.PENDING)
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        llm = MagicMock()
        engine = PlanEngine(llm=llm)
        result = await engine.reorchestrate(dag, [a])
        assert result.nodes["A"].status == NodeStatus.PENDING
        ready = result.get_ready_nodes()
        assert "A" in [n.id for n in ready]


class TestMaxReorchestrateRetries:
    @pytest.mark.asyncio
    async def test_max_reorchestrate_retries(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="persistent error")
        dag = _make_dag(nodes={"A": a})
        llm = MagicMock()
        engine = PlanEngine(llm=llm)

        from deerflow.config.plan_config import PlanConfig, load_plan_config_from_dict

        config = PlanConfig(reorchestrate_max_retries=2)
        load_plan_config_from_dict(config.model_dump())

        for _ in range(config.reorchestrate_max_retries):
            result = await engine.reorchestrate(dag, [a])
            dag = result

        assert dag.nodes["A"].status == NodeStatus.PENDING

        load_plan_config_from_dict(None)


class TestPartialFailure:
    @pytest.mark.asyncio
    async def test_partial_failure(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="ok")
        b = _make_node("B", status=NodeStatus.FAILED, error="err")
        c = _make_node("C", status=NodeStatus.COMPLETED, result="ok")
        dag = _make_dag(nodes={"A": a, "B": b, "C": c})
        failed = dag.get_failed_nodes()
        assert len(failed) == 1
        assert failed[0].id == "B"
        assert not dag.is_complete()


class TestEmptyDAG:
    def test_empty_dag(self):
        dag = _make_dag()
        assert dag.is_complete() is True
        assert dag.get_ready_nodes() == []
        assert dag.get_failed_nodes() == []


class TestSingleNodeDAG:
    def test_single_node_dag(self):
        node = _make_node("A")
        dag = _make_dag(nodes={"A": node})
        ready = dag.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "A"

    def test_single_node_completed(self):
        node = _make_node("A", status=NodeStatus.COMPLETED, result="done")
        dag = _make_dag(nodes={"A": node})
        assert dag.is_complete() is True


class TestCircularDependency:
    def test_circular_dependency(self):
        a = _make_node("A", dependencies=["B"])
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b})
        errors = PlanEngine.validate_dag(dag)
        assert any("环形依赖" in e for e in errors)


class TestAllNodesFail:
    def test_all_nodes_fail(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err1")
        b = _make_node("B", status=NodeStatus.FAILED, error="err2")
        dag = _make_dag(nodes={"A": a, "B": b})
        assert len(dag.get_failed_nodes()) == 2
        assert dag.is_complete() is False


class TestBarrierWaiting:
    def test_barrier_waiting(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"], barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a, "B": b})
        ready = dag.get_ready_nodes()
        assert all(n.id != "B" for n in ready)

        dag.nodes["A"].status = NodeStatus.COMPLETED
        waiting = dag.get_manual_waiting_nodes()
        assert [n.id for n in waiting] == ["B"]


class TestNodeTimeout:
    @pytest.mark.asyncio
    async def test_node_timeout(self):
        node = _make_node("A", timeout_seconds=1)
        assert node.timeout_seconds == 1

        mock_executor_instance = MagicMock()
        mock_executor_instance.execute_async.return_value = "task_1"

        mock_result = MagicMock()
        mock_result.status.value = "timed_out"
        mock_result.error = "timeout"

        call_count = 0

        def side_effect(tid):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                return mock_result
            return None

        with patch("deerflow.config.get_app_config", return_value=MagicMock()), \
             patch("deerflow.subagents.get_subagent_config", return_value=MagicMock()), \
             patch("deerflow.tools.get_available_tools", return_value=[]), \
             patch("deerflow.subagents.executor.SubagentExecutor", return_value=mock_executor_instance), \
             patch("deerflow.subagents.executor.get_background_task_result", side_effect=side_effect):

            with pytest.raises(TimeoutError, match="超时或取消"):
                await _dispatch_subagent(node, {"task_description": "test"})


class TestOrphanNode:
    def test_orphan_node(self):
        a = _make_node("A")
        b = _make_node("B")
        dag = _make_dag(nodes={"A": a, "B": b})
        errors = PlanEngine.validate_dag(dag)
        assert any("孤立节点" in e for e in errors)


class TestSelfDependency:
    def test_self_dependency(self):
        a = _make_node("A", dependencies=["A"])
        dag = _make_dag(nodes={"A": a})
        errors = PlanEngine.validate_dag(dag)
        assert any("环形依赖" in e for e in errors)


class TestPlanExecuteDagNode:
    @pytest.mark.asyncio
    async def test_execute_dag_no_plan(self):
        state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = await plan_execute_dag_node(state)
        assert result["plan"] is None

    @pytest.mark.asyncio
    async def test_execute_dag_with_ready_nodes(self):
        a = _make_node("A")
        dag = _make_dag(nodes={"A": a})

        with patch("deerflow.plan.nodes._dispatch_subagent", new_callable=AsyncMock, return_value="result_A"):
            state: PlanState = {
                "messages": [],
                "plan": dag.model_dump(),
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }
            result = await plan_execute_dag_node(state)
            updated_plan = PlanDAG.model_validate(result["plan"])
            assert updated_plan.nodes["A"].status == NodeStatus.COMPLETED
            assert updated_plan.nodes["A"].result == "result_A"

    @pytest.mark.asyncio
    async def test_execute_dag_with_failed_dispatch(self):
        a = _make_node("A")
        dag = _make_dag(nodes={"A": a})

        with patch("deerflow.plan.nodes._dispatch_subagent", new_callable=AsyncMock, side_effect=RuntimeError("dispatch failed")):
            state: PlanState = {
                "messages": [],
                "plan": dag.model_dump(),
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }
            result = await plan_execute_dag_node(state)
            updated_plan = PlanDAG.model_validate(result["plan"])
            assert updated_plan.nodes["A"].status == NodeStatus.FAILED
            assert "dispatch failed" in updated_plan.nodes["A"].error


class TestPlanSuperviseNode:
    @pytest.mark.asyncio
    async def test_supervise_no_plan(self):
        state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = await plan_supervise_node(state)
        assert result["plan"] is None

    @pytest.mark.asyncio
    async def test_supervise_acceptance_fail(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="bad result", acceptance_criteria=["必须返回正数"])
        dag = _make_dag(nodes={"A": a})

        with patch.object(PlanEngine, "verify_acceptance", new_callable=AsyncMock, return_value=False):
            state: PlanState = {
                "messages": [],
                "plan": dag.model_dump(),
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }
            result = await plan_supervise_node(state)
            updated_plan = PlanDAG.model_validate(result["plan"])
            assert updated_plan.nodes["A"].status == NodeStatus.FAILED
            assert updated_plan.nodes["A"].error == "验收标准未通过"

    @pytest.mark.asyncio
    async def test_supervise_acceptance_pass(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="good result", acceptance_criteria=["输出非空"])
        dag = _make_dag(nodes={"A": a})

        with patch.object(PlanEngine, "verify_acceptance", new_callable=AsyncMock, return_value=True):
            state: PlanState = {
                "messages": [],
                "plan": dag.model_dump(),
                "plan_approved": True,
                "active_node_ids": None,
                "plan_revised": None,
            }
            result = await plan_supervise_node(state)
            updated_plan = PlanDAG.model_validate(result["plan"])
            assert updated_plan.nodes["A"].status == NodeStatus.COMPLETED


class TestPlanReorchestrateNode:
    @pytest.mark.asyncio
    async def test_reorchestrate_no_plan(self):
        state: PlanState = {
            "messages": [],
            "plan": None,
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = await plan_reorchestrate_node(state)
        assert result["plan"] is None
        assert result["plan_revised"] is False

    @pytest.mark.asyncio
    async def test_reorchestrate_with_failed_nodes(self):
        a = _make_node("A", status=NodeStatus.FAILED, error="err")
        b = _make_node("B", dependencies=["A"], status=NodeStatus.PENDING)
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])

        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = await plan_reorchestrate_node(state)
        updated_plan = PlanDAG.model_validate(result["plan"])
        assert updated_plan.nodes["A"].status == NodeStatus.PENDING
        assert result["plan_revised"] is True

    @pytest.mark.asyncio
    async def test_reorchestrate_no_failed_nodes(self):
        a = _make_node("A", status=NodeStatus.COMPLETED, result="ok")
        dag = _make_dag(nodes={"A": a})

        state: PlanState = {
            "messages": [],
            "plan": dag.model_dump(),
            "plan_approved": True,
            "active_node_ids": None,
            "plan_revised": None,
        }
        result = await plan_reorchestrate_node(state)
        assert result["plan_revised"] is False


class TestPlanConfig:
    def test_default_values(self):
        from deerflow.config.plan_config import PlanConfig

        config = PlanConfig()
        assert config.enabled is False
        assert config.max_parallel_nodes == 3
        assert config.default_timeout == 900
        assert config.auto_approve is False
        assert config.acceptance_verification is True
        assert config.reorchestrate_max_retries == 2

    def test_custom_values(self):
        from deerflow.config.plan_config import PlanConfig

        config = PlanConfig(
            enabled=True,
            max_parallel_nodes=5,
            default_timeout=600,
            auto_approve=True,
            acceptance_verification=False,
            reorchestrate_max_retries=3,
        )
        assert config.enabled is True
        assert config.max_parallel_nodes == 5
        assert config.default_timeout == 600
        assert config.auto_approve is True
        assert config.acceptance_verification is False
        assert config.reorchestrate_max_retries == 3

    def test_load_from_dict(self):
        from deerflow.config.plan_config import load_plan_config_from_dict

        config = load_plan_config_from_dict({"enabled": True, "max_parallel_nodes": 5})
        assert config.enabled is True
        assert config.max_parallel_nodes == 5

    def test_load_from_none(self):
        from deerflow.config.plan_config import load_plan_config_from_dict

        config = load_plan_config_from_dict(None)
        assert config.enabled is False

    def test_get_plan_config(self):
        from deerflow.config.plan_config import get_plan_config, load_plan_config_from_dict

        load_plan_config_from_dict({"enabled": True})
        config = get_plan_config()
        assert config.enabled is True

        load_plan_config_from_dict(None)

    def test_reset_plan_config(self):
        from deerflow.config.plan_config import get_plan_config, load_plan_config_from_dict, reset_plan_config

        load_plan_config_from_dict({"enabled": True})
        reset_plan_config()
        config = get_plan_config()
        assert config.enabled is False

    def test_app_config_includes_plan(self):
        from deerflow.config.plan_config import PlanConfig
        from deerflow.config.sandbox_config import SandboxConfig

        plan = PlanConfig(enabled=True, max_parallel_nodes=5)
        from deerflow.config.app_config import AppConfig

        ac = AppConfig(sandbox=SandboxConfig(use="deerflow.sandbox.local.LocalSandboxProvider"), plan=plan)
        assert ac.plan.enabled is True
        assert ac.plan.max_parallel_nodes == 5
