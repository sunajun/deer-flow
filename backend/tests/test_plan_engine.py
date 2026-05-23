from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from deerflow.plan.engine import PlanEngine, _find_downstream
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
