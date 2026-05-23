import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from deerflow.claude_session.models import ClaudeSession
from deerflow.config.acp_config import ACPAgentConfig
from deerflow.tools.builtins.invoke_acp_agent_tool import (
    _build_acp_mcp_servers,
    _build_permission_response,
    _get_work_dir,
)

logger = logging.getLogger(__name__)


class _StreamingClient:
    """Streaming ACP Client that pushes output chunks to an asyncio.Queue.

    Follows the _CollectingClient pattern from invoke_acp_agent_tool but
    routes each chunk to a queue instead of accumulating in a list.
    """

    def __init__(self, output_queue: asyncio.Queue) -> None:
        self._queue = output_queue
        self._chunks: list[str] = []

    @property
    def collected_text(self) -> str:
        return "".join(self._chunks)

    async def session_update(self, session_id: str, update, **kwargs) -> None:
        try:
            from acp.schema import TextContentBlock

            if hasattr(update, "content") and isinstance(update.content, TextContentBlock):
                chunk = {
                    "type": "text",
                    "content": update.content.text,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await self._queue.put(chunk)
                self._chunks.append(update.content.text)
        except Exception:
            logger.debug("session_update: skipping non-text update", exc_info=True)

    async def request_permission(self, options, session_id: str, tool_call, **kwargs):
        response = _build_permission_response(options, auto_approve=True)
        outcome = response.outcome.outcome
        if outcome == "selected":
            logger.info(
                "ACP permission auto-approved for tool call %s in session %s",
                tool_call.tool_call_id,
                session_id,
            )
        else:
            logger.warning(
                "ACP permission denied for tool call %s in session %s",
                tool_call.tool_call_id,
                session_id,
            )
        return response


class _Connection:
    """Holds all state for a single ACP connection."""

    __slots__ = (
        "connection_id",
        "conn",
        "proc",
        "context_mgr",
        "client",
        "queue",
        "acp_session_id",
        "prompt_task",
    )

    def __init__(
        self,
        connection_id: str,
        conn,
        proc,
        context_mgr,
        client: _StreamingClient,
        queue: asyncio.Queue,
        acp_session_id: str,
    ) -> None:
        self.connection_id = connection_id
        self.conn = conn
        self.proc = proc
        self.context_mgr = context_mgr
        self.client = client
        self.queue = queue
        self.acp_session_id = acp_session_id
        self.prompt_task: asyncio.Task | None = None


class ClaudeACPAdapter:
    """ACP communication adapter for Claude Code sessions.

    Reuses the existing ACP infrastructure (spawn_agent_process, Client,
    _build_acp_mcp_servers, _build_permission_response) to establish
    persistent ACP connections that survive across multiple prompt rounds.
    """

    def __init__(self, agent_config: ACPAgentConfig) -> None:
        self._agent_config = agent_config
        self._connections: dict[str, _Connection] = {}

    async def create_connection(self, session: ClaudeSession) -> str:
        """Spawn an ACP agent process and return a connection_id."""
        from acp import PROTOCOL_VERSION, spawn_agent_process
        from acp.schema import ClientCapabilities, Implementation

        connection_id = str(uuid.uuid4())
        output_queue: asyncio.Queue = asyncio.Queue()
        client = _StreamingClient(output_queue)

        cmd = self._agent_config.command
        args = self._agent_config.args or []
        cwd = session.working_directory or _get_work_dir(session.thread_id)

        try:
            mcp_servers = _build_acp_mcp_servers()
        except ValueError as exc:
            logger.warning("Invalid MCP server config for Claude session; continuing without MCP: %s", exc)
            mcp_servers = []

        agent_env: dict[str, str] | None = None
        if self._agent_config.env:
            agent_env = {k: (os.environ.get(v[1:], "") if v.startswith("$") else v) for k, v in self._agent_config.env.items()}

        context_mgr = spawn_agent_process(client, cmd, *args, env=agent_env, cwd=cwd)
        conn, proc = await context_mgr.__aenter__()

        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(
                name="deerflow-claude-session",
                title="DeerFlow Claude Session",
                version="0.1.0",
            ),
        )

        session_kwargs: dict = {"cwd": cwd, "mcp_servers": mcp_servers}
        if self._agent_config.model:
            session_kwargs["model"] = self._agent_config.model
        acp_session = await conn.new_session(**session_kwargs)

        self._connections[connection_id] = _Connection(
            connection_id=connection_id,
            conn=conn,
            proc=proc,
            context_mgr=context_mgr,
            client=client,
            queue=output_queue,
            acp_session_id=acp_session.session_id,
        )

        logger.info(
            "Created ACP connection %s (acp_session=%s) for Claude session %s",
            connection_id,
            acp_session.session_id,
            session.session_id,
        )
        return connection_id

    async def send_message(self, connection_id: str, message: str) -> None:
        """Send a prompt to the ACP agent via an existing connection.

        The prompt runs as a background task so that output can be consumed
        concurrently via receive_output.
        """
        from acp import text_block

        conn_info = self._connections.get(connection_id)
        if conn_info is None:
            raise KeyError(f"Connection '{connection_id}' not found")

        if conn_info.prompt_task is not None and not conn_info.prompt_task.done():
            raise RuntimeError(f"Connection '{connection_id}' already has an active prompt; wait for it to finish before sending a new message")

        async def _run_prompt() -> None:
            try:
                await conn_info.conn.prompt(
                    session_id=conn_info.acp_session_id,
                    prompt=[text_block(message)],
                )
            except Exception as e:
                await conn_info.queue.put(
                    {
                        "type": "error",
                        "content": str(e),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            finally:
                await conn_info.queue.put(None)

        conn_info.prompt_task = asyncio.create_task(_run_prompt())

    async def receive_output(self, connection_id: str) -> AsyncIterator[dict]:
        """Yield output chunks from the ACP connection until a None sentinel."""
        conn_info = self._connections.get(connection_id)
        if conn_info is None:
            raise KeyError(f"Connection '{connection_id}' not found")

        while True:
            chunk = await conn_info.queue.get()
            if chunk is None:
                break
            yield chunk

    async def close_connection(self, connection_id: str) -> None:
        """Gracefully close an ACP connection and release resources."""
        conn_info = self._connections.pop(connection_id, None)
        if conn_info is None:
            return

        if conn_info.prompt_task is not None and not conn_info.prompt_task.done():
            conn_info.prompt_task.cancel()
            try:
                await conn_info.prompt_task
            except asyncio.CancelledError:
                pass

        try:
            await conn_info.context_mgr.__aexit__(None, None, None)
        except Exception:
            logger.debug("Error closing ACP context manager for %s", connection_id, exc_info=True)

        logger.info("Closed ACP connection %s", connection_id)

    async def check_connection_health(self, connection_id: str) -> bool:
        """Return True if the ACP agent process is still alive."""
        conn_info = self._connections.get(connection_id)
        if conn_info is None:
            return False

        proc = conn_info.proc
        if proc is None:
            return True

        return proc.returncode is None

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)
