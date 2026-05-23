import asyncio
import collections
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from deerflow.claude_session.acp_adapter import ClaudeACPAdapter
from deerflow.claude_session.models import (
    ClaudeSession,
    ClaudeSessionPool,
    SessionConfig,
    SessionMessage,
    SessionStatus,
)

logger = logging.getLogger(__name__)

_OUTPUT_BUFFER_SIZE = 64


class ClaudeSessionManager:
    def __init__(
        self,
        config: SessionConfig | None = None,
        acp_adapter: ClaudeACPAdapter | None = None,
    ):
        self.config = config or SessionConfig()
        self.pools: dict[str, ClaudeSessionPool] = {}
        self._output_streams: dict[str, asyncio.Queue[dict | None]] = {}
        self._session_messages: dict[str, list[SessionMessage]] = {}
        self._idle_timer: dict[str, asyncio.Task] = {}
        self._connection_map: dict[str, str] = {}
        self._output_buffer: dict[str, collections.deque[dict]] = {}
        self._dispatch_tasks: dict[str, asyncio.Task] = {}
        self.max_parallel = self.config.max_parallel
        self._acp_adapter = acp_adapter

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
        active_count = sum(1 for s in pool.sessions.values() if s.status in (SessionStatus.RUNNING, SessionStatus.IDLE, SessionStatus.PAUSED))
        if active_count >= pool.max_parallel:
            raise RuntimeError(f"Thread '{thread_id}' already has {active_count} active sessions (max_parallel={pool.max_parallel})")

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
        self._output_buffer[session.session_id] = collections.deque(maxlen=_OUTPUT_BUFFER_SIZE)
        await self._start_idle_monitor(session.session_id)

        logger.info("Created session %s for thread %s", session.session_id, thread_id)
        return session

    async def send_message(self, session_id: str, message: str) -> None:
        session, _ = self._find_session(session_id)

        if session.status == SessionStatus.PAUSED:
            raise RuntimeError(f"Session '{session_id}' is paused; resume it first")

        if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED):
            raise RuntimeError(f"Session '{session_id}' is {session.status.value}; cannot send message")

        if session_id in self._dispatch_tasks and not self._dispatch_tasks[session_id].done():
            raise RuntimeError(f"Session '{session_id}' already has an active dispatch")

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

        self._dispatch_tasks[session_id] = asyncio.create_task(self._dispatch_to_claude(session, message))

    async def continue_session(self, session_id: str, message: str) -> None:
        await self.send_message(session_id, message)

    async def terminate_session(self, session_id: str) -> None:
        session, _ = self._find_session(session_id)

        session.status = SessionStatus.COMPLETED
        session.last_active_at = datetime.now(UTC)

        await self._cleanup_session(session_id)

        logger.info("Terminated session %s", session_id)

    async def pause_session(self, session_id: str) -> None:
        session, _ = self._find_session(session_id)

        if session.status != SessionStatus.RUNNING:
            raise RuntimeError(f"Cannot pause session '{session_id}' in state {session.status.value}; only RUNNING sessions can be paused")

        session.status = SessionStatus.PAUSED
        session.last_active_at = datetime.now(UTC)

        if session_id in self._idle_timer:
            self._idle_timer[session_id].cancel()
            del self._idle_timer[session_id]

        logger.info("Paused session %s", session_id)

    async def resume_session(self, session_id: str) -> None:
        session, _ = self._find_session(session_id)

        if session.status != SessionStatus.PAUSED:
            raise RuntimeError(f"Cannot resume session '{session_id}' in state {session.status.value}; only PAUSED sessions can be resumed")

        session.status = SessionStatus.RUNNING
        session.last_active_at = datetime.now(UTC)

        await self._start_idle_monitor(session_id)

        logger.info("Resumed session %s", session_id)

    async def get_output_stream(self, session_id: str) -> asyncio.Queue[dict | None]:
        if session_id not in self._output_streams:
            raise KeyError(f"No output stream for session '{session_id}'")
        return self._output_streams[session_id]

    async def stream_output(self, session_id: str) -> AsyncIterator[dict]:
        """Yield structured output chunks from a session's output stream.

        Each chunk is a dict with keys: ``type`` (``text`` | ``error`` |
        ``tool_use`` | ``end``), ``content``, and ``timestamp``.  The
        iterator terminates when a ``None`` sentinel is read from the
        underlying queue.
        """
        self._find_session(session_id)
        queue = self._output_streams.get(session_id)
        if queue is None:
            return

        while True:
            chunk = await queue.get()
            if chunk is None:
                yield {"type": "end", "content": "", "timestamp": datetime.now(UTC).isoformat()}
                break
            yield chunk
            buf = self._output_buffer.get(session_id)
            if buf is not None:
                buf.append(chunk)

    async def get_buffered_output(self, session_id: str) -> list[dict]:
        """Return the recent output buffer for a session."""
        self._find_session(session_id)
        buf = self._output_buffer.get(session_id)
        if buf is None:
            return []
        return list(buf)

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

    async def _ensure_connection(self, session: ClaudeSession) -> str:
        """Ensure the session has an active ACP connection; create one if needed."""
        existing = self._connection_map.get(session.session_id)
        if existing is not None:
            healthy = await self._acp_adapter.check_connection_health(existing)
            if healthy:
                return existing
            logger.warning(
                "ACP connection %s for session %s is unhealthy; recreating",
                existing,
                session.session_id,
            )
            await self._acp_adapter.close_connection(existing)
            del self._connection_map[session.session_id]

        connection_id = await self._acp_adapter.create_connection(session)
        self._connection_map[session.session_id] = connection_id
        return connection_id

    async def _dispatch_to_claude(self, session: ClaudeSession, message: str) -> None:
        """Send a message to Claude via ACP and pipe output to the session stream."""
        try:
            connection_id = await self._ensure_connection(session)
        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error = str(e)
            queue = self._output_streams.get(session.session_id)
            if queue is not None:
                await queue.put(None)
            logger.error("Failed to establish ACP connection for session %s: %s", session.session_id, e)
            return

        try:
            await self._acp_adapter.send_message(connection_id, message)
        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error = str(e)
            queue = self._output_streams.get(session.session_id)
            if queue is not None:
                await queue.put(None)
            logger.error("Failed to send message via ACP for session %s: %s", session.session_id, e)
            return

        queue = self._output_streams[session.session_id]
        try:
            async for chunk in self._acp_adapter.receive_output(connection_id):
                await queue.put(chunk)
                session.last_active_at = datetime.now(UTC)
        except Exception as e:
            session.status = SessionStatus.FAILED
            session.error = str(e)
            await queue.put({"type": "error", "content": str(e), "timestamp": datetime.now(UTC).isoformat()})
            await queue.put(None)
        else:
            if session.status == SessionStatus.RUNNING:
                session.status = SessionStatus.IDLE
            await queue.put(None)
        finally:
            self._dispatch_tasks.pop(session.session_id, None)

    async def _cleanup_session(self, session_id: str) -> None:
        """Release all resources associated with a session."""
        if session_id in self._idle_timer:
            self._idle_timer[session_id].cancel()
            del self._idle_timer[session_id]

        dispatch_task = self._dispatch_tasks.pop(session_id, None)
        if dispatch_task is not None and not dispatch_task.done():
            dispatch_task.cancel()
            try:
                await dispatch_task
            except asyncio.CancelledError:
                pass

        connection_id = self._connection_map.pop(session_id, None)
        if connection_id is not None and self._acp_adapter is not None:
            await self._acp_adapter.close_connection(connection_id)

        queue = self._output_streams.get(session_id)
        if queue is not None:
            await queue.put(None)

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
                    await self._cleanup_session(session_id)
                    logger.info("Auto-terminated idle session %s", session_id)
            except asyncio.CancelledError:
                pass
            except KeyError:
                pass

        self._idle_timer[session_id] = asyncio.create_task(_monitor())

    async def _reset_idle_timer(self, session_id: str) -> None:
        await self._start_idle_monitor(session_id)
