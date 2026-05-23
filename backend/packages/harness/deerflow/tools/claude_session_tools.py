from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from deerflow.claude_session.manager import ClaudeSessionManager
from deerflow.claude_session.models import SessionConfig
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)

_manager_instance: ClaudeSessionManager | None = None


def get_claude_session_manager() -> ClaudeSessionManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ClaudeSessionManager(config=SessionConfig())
    return _manager_instance


def set_claude_session_manager(manager: ClaudeSessionManager) -> None:
    global _manager_instance
    _manager_instance = manager


def _current_thread_id(runtime: Runtime | None = None) -> str:
    if runtime is not None:
        if runtime.context and runtime.context.get("thread_id"):
            return str(runtime.context["thread_id"])
        if runtime.config.get("configurable", {}).get("thread_id"):
            return str(runtime.config["configurable"]["thread_id"])
    return "default"


@tool
async def claude_code_task(
    task_description: str,
    session_id: str | None = None,
    working_directory: str | None = None,
    *,
    runtime: Runtime | None = None,
) -> str:
    """委派任务给 Claude Code 会话。创建新会话或续接已有会话，返回结果摘要。"""
    manager = get_claude_session_manager()
    if session_id is None:
        session = await manager.create_session(
            thread_id=_current_thread_id(runtime),
            working_directory=working_directory,
        )
        session_id = session.session_id
    else:
        session = await manager.get_session(session_id)

    await manager.send_message(session_id, task_description)

    result_parts: list[str] = []
    async for chunk in manager.stream_output(session_id):
        if chunk["type"] == "text":
            result_parts.append(chunk["content"])
        elif chunk["type"] == "end":
            break

    return f"Session {session_id}: {''.join(result_parts)[:2000]}"


@tool
async def list_claude_sessions(
    thread_id: str | None = None,
    *,
    runtime: Runtime | None = None,
) -> str:
    """列出当前线程或指定线程的 Claude Code 会话。"""
    manager = get_claude_session_manager()
    tid = thread_id or _current_thread_id(runtime)
    sessions = await manager.list_sessions(tid)
    if not sessions:
        return f"No Claude Code sessions for thread {tid}"
    lines = []
    for s in sessions:
        lines.append(f"- {s.session_id[:8]}… | status={s.status.value} | messages={s.message_count} | dir={s.working_directory or 'default'}")
    return "\n".join(lines)


@tool
async def terminate_claude_session(session_id: str) -> str:
    """终止指定的 Claude Code 会话。"""
    manager = get_claude_session_manager()
    await manager.terminate_session(session_id)
    return f"Session {session_id} terminated"
