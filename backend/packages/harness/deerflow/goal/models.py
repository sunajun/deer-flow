from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProblemStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    DROPPED = "dropped"


class SubProblem(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: ProblemStatus = ProblemStatus.OPEN
    assigned_to: str | None = None
    result_summary: str | None = None
    blockers: list[str] = Field(default_factory=list)


class GoalSnapshot(BaseModel):
    goal_id: str
    core_goal: str
    non_goals: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    sub_problems: list[SubProblem] = Field(default_factory=list)
    current_focus: str | None = None
    alignment_version: int = 1
    last_aligned_at: datetime = Field(default_factory=datetime.now)
    direction_changes: list[dict] = Field(default_factory=list)
