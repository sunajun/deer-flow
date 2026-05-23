import asyncio
import logging
import uuid
from datetime import UTC, datetime

from deerflow.claude_session.models import (
    ClaudeSession,
    ClaudeSessionPool,
    SessionConfig,
    SessionMessage,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class ClaudeSessionManager:
    def __init__(self, config: SessionConfig | None = None):
        self.config = config or SessionConfig()
        self.pools: dict[str, ClaudeSessionPool] = {}
        self._output_streams: dict[str, asyncio.Queue[str]] = {}
        self._session_messages: dict[str, list[SessionMessage]] = {}
        self._idle_timer: dict[str, asyncio.Task] = {}
        self.max_parallel = self.config.max_parallel

    def _get_or_create_pool(self, thread_id: str) -> ClaudeSessionPool:
        if thread_id not in self.pools:
            self.pools[thread_id] = ClaudeSessionPool(
                thread_id=thread_id,
                max_parallel=self.max_parallel,
            )
        return self.pools[thread_id]

    def _find_session(self, session_id: str) -> tuple[ClaudeSession, ClaudeSessionPool]:
        for pool in self.pools.values():
            if session_id in pool.sessions:
                return pool.sessions[session_id], pool
        raise KeyError(f"Session '{session_id}' not found")

    async def create_session(
        self,
        thread_id: str,
        parent_node_id: str | None = None,
        working_directory: str | None = None,
        system_prompt_suffix: str = "",
        tool_permissions: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> ClaudeSession:
        pool = self._get_or_create_pool(thread_id)
        active_count = sum(
            1
            for s in pool.sessions.values()
            if s.status in (SessionStatus.RUNNING, SessionStatus.IDLE, SessionStatus.PAUSED)
        )
        if active_count >= pool.max_parallel:
            raise RuntimeError(
                f"Thread '{thread_id}' already has {active_count} active sessions "
                f"(max_parallel={pool.max_parallel})"
            )

        now = datetime.now(UTC)
        session = ClaudeSession(
            session_id=str(uuid.uuid4()),
            thread_id=thread_id,
            parent_node_id=parent_node_id,
            working_directory=working_directory or self.config.working_directory,
            created_at=now,
            last_active_at=now,
            system_prompt_suffix=system_prompt_suffix,
            tool_permissions=tool_permissions or [],
            timeout_seconds=timeout_seconds or self.config.default_timeout,
        )

        pool.sessions[session.session_id] = session
        self._output_streams[session.session_id] = asyncio.Queue()
        self._session_messages[session.session_id] = []
        await self._start_idle_monitor(session.session_id)

        logger.info("Created session %s for thread %s", session.session_id, thread_id)
        return session

    async def send_message(self, session_id: str, message: str) -> None:
        session, _ = self._find_session(session_id)

        if session.status == SessionStatus.PAUSED:
            raise RuntimeError(f"Session '{session_id}' is paused; resume it first")

        if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED):
            raise RuntimeError(f"Session '{session_id}' is {session.status.value}; cannot send message")

        now = datetime.now(UTC)
        user_msg = SessionMessage(
            session_id=session_id,
            role="user",
            content=message,
            timestamp=now,
        )
        self._session_messages[session_id].append(user_msg)

        session.status = SessionStatus.RUNNING
        session.message_count += 1
        session.last_active_at = now

        await self._reset_idle_timer(session_id)

        try:
            await self._dispatch_to_claude(session, message)
        except NotImplementedError:
            raise
        except Exception as exc:
            session.status = SessionStatus.FAILED
            session.error = str(exc)
            logger.error("Error dispatching to Claude in session %s: %s", session_id, exc)
            raise

    async def continue_session(self, session_id: str, message: str) -> None:
        await self.send_message(session_id, message)

    async def terminate_session(self, session_id: str) -> None:
        session, _ = self._find_session(session_id)

        session.status = SessionStatus.COMPLETED
        session.last_active_at = datetime.now(UTC)

        if session_id in self._idle_timer:
            self._idle_timer[session_id].cancel()
            del self._idle_timer[session_id]

        logger.info("Terminated session %s", session_id)

    async def pause_session(self, session_id: str) -> None:
        session, _ = self._find_session(session_id)

        if session.status != SessionStatus.RUNNING:
            raise RuntimeError(
                f"Cannot pause session '{session_id}' in state {session.status.value}; "
                f"only RUNNING sessions can be paused"
            )

        session.status = SessionStatus.PAUSED
        session.last_active_at = datetime.now(UTC)

        if session_id in self._idle_timer:
            self._idle_timer[session_id].cancel()
            del self._idle_timer[session_id]

        logger.info("Paused session %s", session_id)

    async def resume_session(self, session_id: str) -> None:
        session, _ = self._find_session(session_id)

        if session.status != SessionStatus.PAUSED:
            raise RuntimeError(
                f"Cannot resume session '{session_id}' in state {session.status.value}; "
                f"only PAUSED sessions can be resumed"
            )

        session.status = SessionStatus.RUNNING
        session.last_active_at = datetime.now(UTC)

        await self._start_idle_monitor(session_id)

        logger.info("Resumed session %s", session_id)

    async def get_output_stream(self, session_id: str) -> asyncio.Queue[str]:
        if session_id not in self._output_streams:
            raise KeyError(f"No output stream for session '{session_id}'")
        return self._output_streams[session_id]

    async def get_session(self, session_id: str) -> ClaudeSession:
        session, _ = self._find_session(session_id)
        return session

    async def list_sessions(self, thread_id: str) -> list[ClaudeSession]:
        pool = self.pools.get(thread_id)
        if pool is None:
            return []
        return list(pool.sessions.values())

    async def get_messages(self, session_id: str) -> list[SessionMessage]:
        self._find_session(session_id)
        return list(self._session_messages.get(session_id, []))

    async def _dispatch_to_claude(self, session: ClaudeSession, message: str) -> None:
        raise NotImplementedError(
            "_dispatch_to_claude is a skeleton; actual implementation deferred to T21. "
            "Claude Code sessions will reuse the ACP communication layer "
            "(spawn_agent_process, Client, new_session, prompt)."
        )

    async def _start_idle_monitor(self, session_id: str) -> None:
        if session_id in self._idle_timer:
            self._idle_timer[session_id].cancel()

        async def _monitor():
            try:
                await asyncio.sleep(self.config.auto_terminate_idle)
                session, _ = self._find_session(session_id)
                if session.status in (SessionStatus.IDLE, SessionStatus.RUNNING):
                    session.status = SessionStatus.COMPLETED
                    session.error = "Auto-terminated due to idle timeout"
                    logger.info("Auto-terminated idle session %s", session_id)
            except asyncio.CancelledError:
                pass
            except KeyError:
                pass

        self._idle_timer[session_id] = asyncio.create_task(_monitor())

    async def _reset_idle_timer(self, session_id: str) -> None:
        await self._start_idle_monitor(session_id)
