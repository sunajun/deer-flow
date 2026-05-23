from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BarrierType(StrEnum):
    ALL = "all"
    ANY = "any"
    MANUAL = "manual"


class PlanNode(BaseModel):
    id: str
    title: str
    description: str
    assignee: str = "general-purpose"
    dependencies: list[str] = Field(default_factory=list)
    barrier_type: BarrierType = BarrierType.ALL
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_from: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    subagent_config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 900


class PlanDAG(BaseModel):
    plan_id: str
    title: str
    description: str
    goal: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    nodes: dict[str, PlanNode] = Field(default_factory=dict)
    edges: list[list[str]] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_ready_nodes(self) -> list[PlanNode]:
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps = [self.nodes[dep_id] for dep_id in node.dependencies if dep_id in self.nodes]
            if not deps:
                if node.barrier_type == BarrierType.MANUAL:
                    continue
                ready.append(node)
                continue
            if node.barrier_type == BarrierType.ALL:
                if all(d.status == NodeStatus.COMPLETED for d in deps):
                    ready.append(node)
            elif node.barrier_type == BarrierType.ANY:
                if any(d.status == NodeStatus.COMPLETED for d in deps):
                    ready.append(node)
            elif node.barrier_type == BarrierType.MANUAL:
                if all(d.status == NodeStatus.COMPLETED for d in deps):
                    pass
        return ready

    def get_manual_waiting_nodes(self) -> list[PlanNode]:
        waiting = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING or node.barrier_type != BarrierType.MANUAL:
                continue
            deps = [self.nodes[dep_id] for dep_id in node.dependencies if dep_id in self.nodes]
            if not deps or all(d.status == NodeStatus.COMPLETED for d in deps):
                waiting.append(node)
        return waiting

    def is_complete(self) -> bool:
        return all(n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED) for n in self.nodes.values())

    def get_failed_nodes(self) -> list[PlanNode]:
        return [n for n in self.nodes.values() if n.status == NodeStatus.FAILED]
