"""Tests for GoalSnapshot models and GoalTrackerMiddleware."""

from types import SimpleNamespace
from unittest import mock

from langchain_core.messages import HumanMessage

from deerflow.agents.middlewares.goal_middleware import GoalTrackerMiddleware
from deerflow.goal.models import GoalSnapshot, ProblemStatus, SubProblem


def _fake_runtime():
    return SimpleNamespace(context={})


def _make_snapshot(**overrides) -> dict:
    defaults = {
        "goal_id": "goal_test",
        "core_goal": "Build a REST API",
        "non_goals": ["No frontend"],
        "acceptance_criteria": ["All endpoints return 200"],
        "sub_problems": [
            {
                "id": "sub_design",
                "title": "Design API schema",
                "description": "Define routes and models",
                "acceptance_criteria": ["Schema reviewed"],
                "status": "open",
                "assigned_to": None,
                "result_summary": None,
                "blockers": [],
            }
        ],
        "current_focus": None,
        "alignment_version": 1,
        "direction_changes": [],
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# GoalSnapshot / SubProblem / ProblemStatus model tests
# ---------------------------------------------------------------------------


def test_goal_snapshot_instantiation():
    snapshot = GoalSnapshot(**_make_snapshot())
    assert snapshot.goal_id == "goal_test"
    assert snapshot.core_goal == "Build a REST API"
    assert snapshot.non_goals == ["No frontend"]
    assert snapshot.acceptance_criteria == ["All endpoints return 200"]
    assert len(snapshot.sub_problems) == 1
    assert snapshot.alignment_version == 1


def test_sub_problem_default_status():
    sub = SubProblem(id="s1", title="t", description="d")
    assert sub.status == ProblemStatus.OPEN


def test_problem_status_values():
    assert ProblemStatus.OPEN.value == "open"
    assert ProblemStatus.IN_PROGRESS.value == "in_progress"
    assert ProblemStatus.BLOCKED.value == "blocked"
    assert ProblemStatus.RESOLVED.value == "resolved"
    assert ProblemStatus.DROPPED.value == "dropped"


def test_dict_roundtrip():
    snapshot = GoalSnapshot(**_make_snapshot())
    data = snapshot.model_dump()
    restored = GoalSnapshot.model_validate(data)
    assert restored.goal_id == snapshot.goal_id
    assert restored.core_goal == snapshot.core_goal
    assert len(restored.sub_problems) == len(snapshot.sub_problems)
    assert restored.sub_problems[0].id == snapshot.sub_problems[0].id


# ---------------------------------------------------------------------------
# inject_to_prompt tests
# ---------------------------------------------------------------------------


def test_inject_to_prompt_no_snapshot():
    mw = GoalTrackerMiddleware()
    state = {"messages": []}
    assert mw.inject_to_prompt(state) == ""


def test_inject_to_prompt_with_snapshot():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.inject_to_prompt(state)
    assert "Build a REST API" in result
    assert "All endpoints return 200" in result
    assert "Design API schema" in result
    assert "Define routes and models" in result


def test_inject_to_prompt_with_non_goals():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot(non_goals=["No frontend", "No mobile"]))
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.inject_to_prompt(state)
    assert "No frontend" in result
    assert "No mobile" in result


def test_inject_to_prompt_with_result_summary():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    snapshot.sub_problems[0].status = ProblemStatus.RESOLVED
    snapshot.sub_problems[0].result_summary = "Schema approved"
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.inject_to_prompt(state)
    assert "Schema approved" in result


def test_inject_to_prompt_alignment_version():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot(alignment_version=3))
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.inject_to_prompt(state)
    assert "v3" in result


# ---------------------------------------------------------------------------
# before_agent tests
# ---------------------------------------------------------------------------


def test_before_agent_injects_reminder():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    state = {
        "messages": [HumanMessage(content="Hello")],
        "goal_snapshot": snapshot.model_dump(),
    }
    result = mw.before_agent(state, _fake_runtime())
    assert result is not None
    msgs = result["messages"]
    assert len(msgs) == 1
    reminder = msgs[0]
    assert isinstance(reminder, HumanMessage)
    assert "<system-reminder>" in reminder.content
    assert "Build a REST API" in reminder.content
    assert reminder.additional_kwargs.get("hide_from_ui") is True
    assert reminder.additional_kwargs.get("goal_tracker_reminder") is True


def test_before_agent_no_snapshot_returns_none():
    mw = GoalTrackerMiddleware()
    state = {"messages": [HumanMessage(content="Hello")]}
    result = mw.before_agent(state, _fake_runtime())
    assert result is None


def test_before_agent_no_messages_returns_none():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    state = {"messages": [], "goal_snapshot": snapshot.model_dump()}
    result = mw.before_agent(state, _fake_runtime())
    assert result is None


# ---------------------------------------------------------------------------
# on_plan_created tests
# ---------------------------------------------------------------------------


def test_on_plan_created():
    mw = GoalTrackerMiddleware()
    plan = {
        "plan_id": "p1",
        "goal": "Refactor module",
        "acceptance_criteria": ["Tests pass"],
        "nodes": {
            "step1": {
                "title": "Extract utils",
                "description": "Move helpers",
                "acceptance_criteria": ["No import errors"],
                "assignee": "agent_a",
            },
            "step2": {
                "title": "Update tests",
                "description": "Fix test imports",
            },
        },
    }
    state = {}
    result = mw.on_plan_created(state, plan)
    snapshot = GoalSnapshot.model_validate(result["goal_snapshot"])
    assert snapshot.goal_id == "goal_p1"
    assert snapshot.core_goal == "Refactor module"
    assert len(snapshot.sub_problems) == 2
    assert snapshot.sub_problems[0].id == "sub_step1"
    assert snapshot.sub_problems[0].title == "Extract utils"
    assert snapshot.sub_problems[0].assigned_to == "agent_a"
    assert snapshot.sub_problems[1].id == "sub_step2"


# ---------------------------------------------------------------------------
# on_subtask_completed tests
# ---------------------------------------------------------------------------


def test_on_subtask_completed():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.on_subtask_completed(state, "design", "Schema reviewed and approved")
    updated = GoalSnapshot.model_validate(result["goal_snapshot"])
    assert updated.sub_problems[0].status == ProblemStatus.RESOLVED
    assert "Schema reviewed and approved" in updated.sub_problems[0].result_summary


def test_on_subtask_completed_no_snapshot():
    mw = GoalTrackerMiddleware()
    state = {}
    result = mw.on_subtask_completed(state, "design", "done")
    assert result == {}


def test_on_subtask_completed_result_truncated():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    state = {"goal_snapshot": snapshot.model_dump()}
    long_result = "x" * 1000
    result = mw.on_subtask_completed(state, "design", long_result)
    updated = GoalSnapshot.model_validate(result["goal_snapshot"])
    assert len(updated.sub_problems[0].result_summary) == 500


# ---------------------------------------------------------------------------
# on_direction_change tests
# ---------------------------------------------------------------------------


def test_on_direction_change():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.on_direction_change(state, "Build a GraphQL API")
    updated = GoalSnapshot.model_validate(result["goal_snapshot"])
    assert updated.core_goal == "Build a GraphQL API"
    assert updated.alignment_version == 2
    assert len(updated.direction_changes) == 1
    assert updated.direction_changes[0]["from"] == "Build a REST API"
    assert updated.direction_changes[0]["to"] == "Build a GraphQL API"


def test_on_direction_change_resets_open_subproblems():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    snapshot.sub_problems[0].status = ProblemStatus.IN_PROGRESS
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.on_direction_change(state, "New direction")
    updated = GoalSnapshot.model_validate(result["goal_snapshot"])
    assert updated.sub_problems[0].status == ProblemStatus.OPEN


def test_on_direction_change_preserves_resolved_subproblems():
    mw = GoalTrackerMiddleware()
    snapshot = GoalSnapshot(**_make_snapshot())
    snapshot.sub_problems[0].status = ProblemStatus.RESOLVED
    snapshot.sub_problems[0].result_summary = "Done"
    state = {"goal_snapshot": snapshot.model_dump()}
    result = mw.on_direction_change(state, "New direction")
    updated = GoalSnapshot.model_validate(result["goal_snapshot"])
    assert updated.sub_problems[0].status == ProblemStatus.RESOLVED


def test_on_direction_change_no_snapshot():
    mw = GoalTrackerMiddleware()
    state = {}
    result = mw.on_direction_change(state, "New direction")
    assert result == {}
