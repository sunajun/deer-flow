import json

from deerflow.plan.engine import PlanEngine
from deerflow.plan.models import BarrierType, NodeStatus, PlanDAG, PlanNode


def _make_node(
    nid: str,
    title: str = "",
    description: str = "",
    dependencies: list[str] | None = None,
    barrier_type: BarrierType = BarrierType.ALL,
    status: NodeStatus = NodeStatus.PENDING,
) -> PlanNode:
    return PlanNode(
        id=nid,
        title=title or nid,
        description=description or nid,
        dependencies=dependencies or [],
        barrier_type=barrier_type,
        status=status,
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


class TestEmptyDAG:
    def test_empty_dag_is_complete(self):
        dag = _make_dag()
        assert dag.is_complete() is True

    def test_empty_dag_no_ready_nodes(self):
        dag = _make_dag()
        assert dag.get_ready_nodes() == []

    def test_empty_dag_no_failed_nodes(self):
        dag = _make_dag()
        assert dag.get_failed_nodes() == []


class TestSingleNode:
    def test_single_node_ready(self):
        node = _make_node("A")
        dag = _make_dag(nodes={"A": node})
        ready = dag.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "A"

    def test_single_node_not_ready_when_running(self):
        node = _make_node("A", status=NodeStatus.RUNNING)
        dag = _make_dag(nodes={"A": node})
        assert dag.get_ready_nodes() == []


class TestLinearChain:
    def test_linear_chain_a_b_c(self):
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


class TestParallelBranches:
    def test_parallel_a_to_b_c_to_d(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        c = _make_node("C", dependencies=["A"])
        d = _make_node("D", dependencies=["B", "C"])
        dag = _make_dag(
            nodes={"A": a, "B": b, "C": c, "D": d},
            edges=[["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"]],
        )

        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["A"]

        dag.nodes["A"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert set(n.id for n in ready) == {"B", "C"}

        dag.nodes["B"].status = NodeStatus.COMPLETED
        dag.nodes["C"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["D"]


class TestBarrierAll:
    def test_barrier_all_requires_all_deps(self):
        a = _make_node("A")
        b = _make_node("B")
        c = _make_node("C", dependencies=["A", "B"], barrier_type=BarrierType.ALL)
        dag = _make_dag(nodes={"A": a, "B": b, "C": c})

        dag.nodes["A"].status = NodeStatus.COMPLETED
        ready_ids = [n.id for n in dag.get_ready_nodes()]
        assert "C" not in ready_ids

        dag.nodes["B"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert [n.id for n in ready] == ["C"]


class TestBarrierAny:
    def test_barrier_any_one_dep_sufficient(self):
        a = _make_node("A")
        b = _make_node("B")
        c = _make_node("C", dependencies=["A", "B"], barrier_type=BarrierType.ANY)
        dag = _make_dag(nodes={"A": a, "B": b, "C": c})

        dag.nodes["A"].status = NodeStatus.COMPLETED
        ready_ids = [n.id for n in dag.get_ready_nodes()]
        assert "C" in ready_ids


class TestBarrierManual:
    def test_manual_not_in_ready_nodes(self):
        a = _make_node("A")
        b = _make_node("B", barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a, "B": b})
        ready = dag.get_ready_nodes()
        assert all(n.id != "B" for n in ready)

    def test_manual_with_deps_not_in_ready_nodes(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"], barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a, "B": b})

        dag.nodes["A"].status = NodeStatus.COMPLETED
        ready = dag.get_ready_nodes()
        assert all(n.id != "B" for n in ready)

    def test_manual_waiting_nodes_no_deps(self):
        a = _make_node("A", barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a})
        waiting = dag.get_manual_waiting_nodes()
        assert [n.id for n in waiting] == ["A"]

    def test_manual_waiting_nodes_deps_completed(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"], barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a, "B": b})

        dag.nodes["A"].status = NodeStatus.COMPLETED
        waiting = dag.get_manual_waiting_nodes()
        assert [n.id for n in waiting] == ["B"]

    def test_manual_waiting_nodes_deps_not_completed(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"], barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a, "B": b})
        waiting = dag.get_manual_waiting_nodes()
        assert [n.id for n in waiting] == []


class TestIsComplete:
    def test_all_completed(self):
        a = _make_node("A", status=NodeStatus.COMPLETED)
        b = _make_node("B", status=NodeStatus.COMPLETED)
        dag = _make_dag(nodes={"A": a, "B": b})
        assert dag.is_complete() is True

    def test_with_skipped(self):
        a = _make_node("A", status=NodeStatus.COMPLETED)
        b = _make_node("B", status=NodeStatus.SKIPPED)
        dag = _make_dag(nodes={"A": a, "B": b})
        assert dag.is_complete() is True

    def test_not_complete_with_pending(self):
        a = _make_node("A", status=NodeStatus.COMPLETED)
        b = _make_node("B", status=NodeStatus.PENDING)
        dag = _make_dag(nodes={"A": a, "B": b})
        assert dag.is_complete() is False

    def test_not_complete_with_running(self):
        a = _make_node("A", status=NodeStatus.COMPLETED)
        b = _make_node("B", status=NodeStatus.RUNNING)
        dag = _make_dag(nodes={"A": a, "B": b})
        assert dag.is_complete() is False


class TestGetFailedNodes:
    def test_get_failed_nodes(self):
        a = _make_node("A", status=NodeStatus.COMPLETED)
        b = _make_node("B", status=NodeStatus.FAILED)
        c = _make_node("C", status=NodeStatus.FAILED)
        dag = _make_dag(nodes={"A": a, "B": b, "C": c})
        failed = dag.get_failed_nodes()
        assert set(n.id for n in failed) == {"B", "C"}

    def test_no_failed_nodes(self):
        a = _make_node("A", status=NodeStatus.COMPLETED)
        dag = _make_dag(nodes={"A": a})
        assert dag.get_failed_nodes() == []


class TestGetReadyNodesNoMutation:
    def test_get_ready_nodes_no_mutation(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"], barrier_type=BarrierType.MANUAL)
        dag = _make_dag(nodes={"A": a, "B": b})

        dag.get_ready_nodes()
        assert dag.nodes["A"].status == NodeStatus.PENDING
        assert dag.nodes["B"].status == NodeStatus.PENDING

        dag.nodes["A"].status = NodeStatus.COMPLETED
        dag.get_ready_nodes()
        dag.get_manual_waiting_nodes()
        assert dag.nodes["B"].status == NodeStatus.PENDING


class TestEdgesListListStr:
    def test_edges_serialization_roundtrip(self):
        edges = [["A", "B"], ["B", "C"]]
        dag = _make_dag(
            nodes={"A": _make_node("A"), "B": _make_node("B", dependencies=["A"]), "C": _make_node("C", dependencies=["B"])},
            edges=edges,
        )
        json_str = dag.model_dump_json()
        data = json.loads(json_str)
        assert isinstance(data["edges"], list)
        for edge in data["edges"]:
            assert isinstance(edge, list)
            for item in edge:
                assert isinstance(item, str)
        restored = PlanDAG.model_validate_json(json_str)
        assert restored.edges == edges

    def test_edges_type_is_list_list_str(self):
        dag = _make_dag(edges=[["X", "Y"]])
        assert dag.edges == [["X", "Y"]]
        assert isinstance(dag.edges[0], list)


class TestValidateDAG:
    def test_valid_dag(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        errors = PlanEngine.validate_dag(dag)
        assert errors == []

    def test_circular_dependency(self):
        a = _make_node("A", dependencies=["B"])
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b})
        errors = PlanEngine.validate_dag(dag)
        assert any("环形依赖" in e for e in errors)

    def test_missing_dependency(self):
        a = _make_node("A", dependencies=["Z"])
        dag = _make_dag(nodes={"A": a})
        errors = PlanEngine.validate_dag(dag)
        assert any("不存在的依赖" in e for e in errors)

    def test_orphan_node(self):
        a = _make_node("A")
        b = _make_node("B")
        dag = _make_dag(nodes={"A": a, "B": b})
        errors = PlanEngine.validate_dag(dag)
        assert any("孤立节点" in e for e in errors)

    def test_single_node_no_orphan_error(self):
        a = _make_node("A")
        dag = _make_dag(nodes={"A": a})
        errors = PlanEngine.validate_dag(dag)
        assert errors == []

    def test_node_with_deps_not_orphan(self):
        a = _make_node("A")
        b = _make_node("B", dependencies=["A"])
        dag = _make_dag(nodes={"A": a, "B": b}, edges=[["A", "B"]])
        errors = PlanEngine.validate_dag(dag)
        assert errors == []
