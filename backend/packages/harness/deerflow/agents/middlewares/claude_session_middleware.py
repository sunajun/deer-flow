from __future__ import annotations

import logging
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import ThreadState
from deerflow.claude_session.models import SessionConfig
from deerflow.tools.claude_session_tools import get_claude_session_manager

logger = logging.getLogger(__name__)


class ClaudeSessionMiddlewareState(dict):
    pass


class ClaudeSessionMiddleware(AgentMiddleware[ThreadState]):
    """Claude Code 会话中间件：拦截 claude_code_task 工具调用，注入当前 thread_id，
    检查并行会话数限制，检查权限。

    钩子策略：
    - after_model: 检查 AI 响应中的 claude_code_task tool_calls，注入 thread_id
      上下文信息，拒绝超出并行上限的调用
    """

    def __init__(
        self,
        config: SessionConfig | None = None,
        allowed_roles: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._config = config or SessionConfig()
        self._allowed_roles = allowed_roles

    def _get_thread_id(self, runtime: Runtime) -> str:
        if runtime.context and runtime.context.get("thread_id"):
            return str(runtime.context["thread_id"])
        if runtime.config.get("configurable", {}).get("thread_id"):
            return str(runtime.config["configurable"]["thread_id"])
        return "default"

    def _check_permission(self, runtime: Runtime) -> bool:
        if self._allowed_roles is None:
            return True
        if runtime.context is None:
            return False
        user_role = runtime.context.get("user_role", "guest")
        return user_role in self._allowed_roles

    def _check_parallel_limit(self, thread_id: str) -> bool:
        manager = get_claude_session_manager()
        pool = manager.pools.get(thread_id)
        if pool is None:
            return True
        from deerflow.claude_session.models import SessionStatus

        active_count = sum(
            1 for s in pool.sessions.values()
            if s.status in (SessionStatus.RUNNING, SessionStatus.IDLE, SessionStatus.PAUSED)
        )
        return active_count < pool.max_parallel

    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        claude_calls = [tc for tc in tool_calls if tc["name"] == "claude_code_task"]
        if not claude_calls:
            return None

        if not self._check_permission(runtime):
            filtered = [tc for tc in tool_calls if tc["name"] != "claude_code_task"]
            if not filtered:
                stripped_msg = last_msg.model_copy(update={
                    "tool_calls": [],
                    "content": (last_msg.content or "") + "\n\n[权限限制] 当前角色无权使用 Claude Code 会话功能。",
                })
                return {"messages": [stripped_msg]}
            filtered_msg = last_msg.model_copy(update={"tool_calls": filtered})
            return {"messages": [filtered_msg]}

        thread_id = self._get_thread_id(runtime)

        if not self._check_parallel_limit(thread_id):
            filtered = [tc for tc in tool_calls if tc["name"] != "claude_code_task"]
            if not filtered:
                stripped_msg = last_msg.model_copy(update={
                    "tool_calls": [],
                    "content": (last_msg.content or "") + f"\n\n[并行限制] 线程 {thread_id} 已达到最大并行会话数 ({self._config.max_parallel})，请等待已有会话完成后再试。",
                })
                return {"messages": [stripped_msg]}
            filtered_msg = last_msg.model_copy(update={"tool_calls": filtered})
            return {"messages": [filtered_msg]}

        return None

    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self.after_model(state, runtime)
