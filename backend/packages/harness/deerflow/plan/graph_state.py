from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


def merge_dict(existing: dict | None, new: dict | None) -> dict:
    if existing is None:
        return new or {}
    if new is None:
        return existing
    return {**existing, **new}


class PlanState(TypedDict):
    messages: Annotated[list, add_messages]
    plan: NotRequired[dict | None]
    plan_approved: NotRequired[bool | None]
    active_node_ids: NotRequired[list[str] | None]
    plan_revised: NotRequired[bool | None]
