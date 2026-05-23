from __future__ import annotations

import logging
from datetime import datetime
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import ThreadState
from deerflow.goal.models import GoalSnapshot, ProblemStatus, SubProblem

logger = logging.getLogger(__name__)


class GoalTrackerMiddleware(AgentMiddleware):

    def _get_snapshot(self, state: ThreadState) -> GoalSnapshot | None:
        raw = state.get("goal_snapshot")
        if raw is None:
            return None
        return GoalSnapshot.model_validate(raw)

    def _put_snapshot(self, snapshot: GoalSnapshot) -> dict:
        return {"goal_snapshot": snapshot.model_dump()}

    def on_plan_created(self, state: ThreadState, plan: dict) -> dict:
        snapshot = GoalSnapshot(
            goal_id=f"goal_{plan.get('plan_id', 'unknown')}",
            core_goal=plan.get("goal", ""),
            non_goals=[],
            acceptance_criteria=plan.get("acceptance_criteria", []),
            sub_problems=[
                SubProblem(
                    id=f"sub_{node_id}",
                    title=node_data.get("title", ""),
                    description=node_data.get("description", ""),
                    acceptance_criteria=node_data.get("acceptance_criteria", []),
                    assigned_to=node_data.get("assignee"),
                )
                for node_id, node_data in plan.get("nodes", {}).items()
            ],
        )
        return self._put_snapshot(snapshot)

    def on_subtask_completed(self, state: ThreadState, node_id: str, result: str) -> dict:
        snapshot = self._get_snapshot(state)
        if snapshot is None:
            return {}
        for sub in snapshot.sub_problems:
            if sub.id == f"sub_{node_id}":
                sub.status = ProblemStatus.RESOLVED
                sub.result_summary = str(result)[:500]
                break
        return self._put_snapshot(snapshot)

    def on_direction_change(self, state: ThreadState, new_direction: str) -> dict:
        snapshot = self._get_snapshot(state)
        if snapshot is None:
            return {}
        snapshot.direction_changes.append({
            "from": snapshot.core_goal,
            "to": new_direction,
            "at": datetime.now().isoformat(),
        })
        snapshot.core_goal = new_direction
        snapshot.alignment_version += 1
        snapshot.last_aligned_at = datetime.now()
        for sub in snapshot.sub_problems:
            if sub.status not in (ProblemStatus.RESOLVED, ProblemStatus.DROPPED):
                sub.status = ProblemStatus.OPEN
        return self._put_snapshot(snapshot)

    def inject_to_prompt(self, state: ThreadState) -> str:
        snapshot = self._get_snapshot(state)
        if snapshot is None:
            return ""
        lines = [
            f"\u3010\u6838\u5fc3\u76ee\u6807\u3011{snapshot.core_goal}",
            f"\u3010\u9a8c\u6536\u6807\u51c6\u3011{'; '.join(snapshot.acceptance_criteria)}",
            "\u3010\u5b50\u95ee\u9898\u3011",
        ]
        for sub in snapshot.sub_problems:
            lines.append(f"  - [{sub.status.value}] {sub.title}: {sub.description}")
            if sub.result_summary:
                lines.append(f"    \u7ed3\u679c: {sub.result_summary}")
        if snapshot.non_goals:
            lines.append(f"\u3010\u975e\u76ee\u6807\u3011{'; '.join(snapshot.non_goals)}")
        lines.append(f"\u3010\u5bf9\u9f50\u7248\u672c\u3011v{snapshot.alignment_version}")
        return "\n".join(lines)

    @override
    def before_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        prompt_text = self.inject_to_prompt(state)
        if not prompt_text:
            return None
        messages = list(state.get("messages", []))
        if not messages:
            return None
        reminder = HumanMessage(
            content=f"<system-reminder>\n{prompt_text}\n</system-reminder>",
            additional_kwargs={"hide_from_ui": True, "goal_tracker_reminder": True},
        )
        return {"messages": [reminder]}

    @override
    async def abefore_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self.before_agent(state, runtime)
