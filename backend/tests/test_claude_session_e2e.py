import asyncio
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deerflow.claude_session.manager import ClaudeSessionManager
from deerflow.claude_session.models import (
    ClaudeSession,
    SessionConfig,
    SessionStatus,
)
from deerflow.tools.claude_session_tools import (
    get_claude_session_manager,
    set_claude_session_manager,
)


class MockACPAdapter:
    def __init__(self, *, responses: list[str] | None = None):
        self._connections: dict[str, ClaudeSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._responses = responses or []
        self._response_index = 0

    async def create_connection(self, session: ClaudeSession) -> str:
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = session
        self._queues[connection_id] = asyncio.Queue()
        return connection_id

    async def send_message(self, connection_id: str, message: str) -> None:
        queue = self._queues.get(connection_id)
        if queue is None:
            raise KeyError(f"Connection '{connection_id}' not found")

        if self._response_index < len(self._responses):
            response_text = self._responses[self._response_index]
            self._response_index += 1
        else:
            response_text = f"Echo: {message}"

        async def _simulate_output():
            for word in response_text.split(" "):
                await queue.put(
                    {
                        "type": "text",
                        "content": word,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            await queue.put(None)

        asyncio.create_task(_simulate_output())

    async def receive_output(self, connection_id: str):
        queue = self._queues.get(connection_id)
        if queue is None:
            raise KeyError(f"Connection '{connection_id}' not found")
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    async def close_connection(self, connection_id: str) -> None:
        self._connections.pop(connection_id, None)
        self._queues.pop(connection_id, None)

    async def check_connection_health(self, connection_id: str) -> bool:
        return connection_id in self._connections

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)


def _make_manager(*, max_parallel: int = 3, responses: list[str] | None = None) -> ClaudeSessionManager:
    adapter = MockACPAdapter(responses=responses)
    mgr = ClaudeSessionManager(
        config=SessionConfig(max_parallel=max_parallel, auto_terminate_idle=9999),
        acp_adapter=adapter,
    )
    original = mgr._start_idle_monitor

    async def _noop(session_id):
        pass

    mgr._start_idle_monitor = _noop
    return mgr


def _make_test_app() -> FastAPI:
    from app.gateway.routers.claude_sessions import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def manager():
    return _make_manager(responses=["Hello from Claude", "Context-aware response"])


@pytest.fixture(autouse=True)
def _reset_manager_singleton():
    yield
    set_claude_session_manager(None)


@pytest.mark.asyncio
async def test_claude_code_task_tool():
    mgr = _make_manager(responses=["Task result from Claude"])
    set_claude_session_manager(mgr)

    from deerflow.tools.claude_session_tools import claude_code_task

    result = await claude_code_task.ainvoke({
        "task_description": "Do something",
    })
    assert "Session" in result
    assert "Task" in result or "result" in result.lower() or "Echo" in result


@pytest.mark.asyncio
async def test_list_claude_sessions_tool():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    await mgr.create_session(thread_id="t1")
    await mgr.create_session(thread_id="t1")

    from deerflow.tools.claude_session_tools import list_claude_sessions

    result = await list_claude_sessions.ainvoke({"thread_id": "t1"})
    assert "idle" in result
    assert result.count("status=idle") == 2


@pytest.mark.asyncio
async def test_terminate_claude_session_tool():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")

    from deerflow.tools.claude_session_tools import terminate_claude_session

    result = await terminate_claude_session.ainvoke({"session_id": session.session_id})
    assert "terminated" in result.lower()

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_multi_session_parallel_dispatch():
    mgr = _make_manager(responses=["Result A", "Result B", "Result C"])
    set_claude_session_manager(mgr)

    sessions = []
    for i in range(3):
        s = await mgr.create_session(thread_id="t1")
        sessions.append(s)

    for s in sessions:
        await mgr.send_message(s.session_id, f"Task for session {s.session_id[:8]}")

    for _ in range(50):
        all_done = all(
            s.session_id not in mgr._dispatch_tasks or mgr._dispatch_tasks[s.session_id].done()
            for s in sessions
        )
        if all_done:
            break
        await asyncio.sleep(0.05)

    for s in sessions:
        updated = await mgr.get_session(s.session_id)
        assert updated.status == SessionStatus.IDLE
        assert updated.message_count == 1


@pytest.mark.asyncio
async def test_session_continuation():
    mgr = _make_manager(responses=["First response", "Second response"])
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "First message")
    await mgr._dispatch_tasks[session.session_id]

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.IDLE
    assert updated.message_count == 1

    await mgr.send_message(session.session_id, "Second message")
    await mgr._dispatch_tasks[session.session_id]

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.IDLE
    assert updated.message_count == 2

    messages = await mgr.get_messages(session.session_id)
    assert len(messages) == 2
    assert messages[0].content == "First message"
    assert messages[1].content == "Second message"


@pytest.mark.asyncio
async def test_session_terminate():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")
    await mgr.terminate_session(session.session_id)

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_parallel_limit():
    mgr = _make_manager(max_parallel=2)
    set_claude_session_manager(mgr)

    await mgr.create_session(thread_id="t1")
    await mgr.create_session(thread_id="t1")

    with pytest.raises(RuntimeError, match="max_parallel=2"):
        await mgr.create_session(thread_id="t1")


@pytest.mark.asyncio
async def test_api_create_session():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/claude-sessions/",
            json={"thread_id": "t1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "idle"
        assert data["thread_id"] == "t1"


@pytest.mark.asyncio
async def test_api_list_sessions():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    await mgr.create_session(thread_id="t1")
    await mgr.create_session(thread_id="t1")

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/claude-sessions/", params={"thread_id": "t1"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


@pytest.mark.asyncio
async def test_api_get_session():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/claude-sessions/{session.session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session.session_id


@pytest.mark.asyncio
async def test_api_get_session_not_found():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/claude-sessions/nonexistent")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_send_message():
    mgr = _make_manager(responses=["Response from Claude"])
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/claude-sessions/{session.session_id}/send",
            json={"message": "Hello Claude"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message_count"] == 1


@pytest.mark.asyncio
async def test_api_pause_resume_session():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")
    session.status = SessionStatus.RUNNING

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/claude-sessions/{session.session_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        resp = await client.post(f"/api/claude-sessions/{session.session_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_api_terminate_session():
    mgr = _make_manager()
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(f"/api/claude-sessions/{session.session_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_api_get_messages():
    mgr = _make_manager(responses=["Response"])
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")
    await mgr.send_message(session.session_id, "Hello")
    await mgr._dispatch_tasks[session.session_id]

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/claude-sessions/{session.session_id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["role"] == "user"
        assert data[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_api_sse_stream():
    mgr = _make_manager(responses=["Streaming output from Claude"])
    set_claude_session_manager(mgr)

    session = await mgr.create_session(thread_id="t1")
    await mgr.send_message(session.session_id, "Stream this")

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", f"/api/claude-sessions/{session.session_id}/stream") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            chunks = []
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    chunks.append(line)
                if len(chunks) >= 10:
                    break

            assert len(chunks) > 0


@pytest.mark.asyncio
async def test_middleware_rejects_no_permission():
    from deerflow.agents.middlewares.claude_session_middleware import ClaudeSessionMiddleware

    mgr = _make_manager()
    set_claude_session_manager(mgr)

    middleware = ClaudeSessionMiddleware(allowed_roles={"admin"})

    runtime = MagicMock()
    runtime.context = {"thread_id": "t1", "user_role": "guest"}
    runtime.config = {}

    ai_msg = MagicMock()
    ai_msg.content = "I will use claude_code_task"
    ai_msg.type = "ai"
    ai_msg.tool_calls = [{"name": "claude_code_task", "args": {"task_description": "test"}, "id": "tc1"}]
    ai_msg.model_copy = MagicMock(return_value=MagicMock(
        content="I will use claude_code_task\n\n[权限限制] 当前角色无权使用 Claude Code 会话功能。",
        tool_calls=[],
    ))

    state = {"messages": [ai_msg]}
    result = middleware.after_model(state, runtime)
    assert result is not None
    assert "messages" in result


@pytest.mark.asyncio
async def test_middleware_rejects_parallel_limit():
    from deerflow.agents.middlewares.claude_session_middleware import ClaudeSessionMiddleware

    mgr = _make_manager(max_parallel=1)
    set_claude_session_manager(mgr)

    await mgr.create_session(thread_id="t1")

    middleware = ClaudeSessionMiddleware(config=SessionConfig(max_parallel=1))

    runtime = MagicMock()
    runtime.context = {"thread_id": "t1"}
    runtime.config = {}

    ai_msg = MagicMock()
    ai_msg.content = "I will use claude_code_task"
    ai_msg.type = "ai"
    ai_msg.tool_calls = [{"name": "claude_code_task", "args": {"task_description": "test"}, "id": "tc1"}]
    ai_msg.model_copy = MagicMock(return_value=MagicMock(
        content="I will use claude_code_task\n\n[并行限制]",
        tool_calls=[],
    ))

    state = {"messages": [ai_msg]}
    result = middleware.after_model(state, runtime)
    assert result is not None
    assert "messages" in result


@pytest.mark.asyncio
async def test_middleware_allows_permitted():
    from deerflow.agents.middlewares.claude_session_middleware import ClaudeSessionMiddleware

    mgr = _make_manager()
    set_claude_session_manager(mgr)

    middleware = ClaudeSessionMiddleware(allowed_roles={"admin", "user"})

    runtime = MagicMock()
    runtime.context = {"thread_id": "t1", "user_role": "user"}
    runtime.config = {}

    ai_msg = MagicMock()
    ai_msg.content = "I will use claude_code_task"
    ai_msg.type = "ai"
    ai_msg.tool_calls = [{"name": "claude_code_task", "args": {"task_description": "test"}, "id": "tc1"}]

    state = {"messages": [ai_msg]}
    result = middleware.after_model(state, runtime)
    assert result is None


@pytest.mark.asyncio
async def test_middleware_no_claude_calls_passes_through():
    from deerflow.agents.middlewares.claude_session_middleware import ClaudeSessionMiddleware

    mgr = _make_manager()
    set_claude_session_manager(mgr)

    middleware = ClaudeSessionMiddleware()

    runtime = MagicMock()
    runtime.context = {"thread_id": "t1"}
    runtime.config = {}

    ai_msg = MagicMock()
    ai_msg.content = "Using other tools"
    ai_msg.type = "ai"
    ai_msg.tool_calls = [{"name": "bash", "args": {"command": "ls"}, "id": "tc1"}]

    state = {"messages": [ai_msg]}
    result = middleware.after_model(state, runtime)
    assert result is None


@pytest.mark.asyncio
async def test_api_full_lifecycle():
    mgr = _make_manager(responses=["Step 1 result", "Step 2 result"])
    set_claude_session_manager(mgr)

    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/claude-sessions/",
            json={"thread_id": "lifecycle-test"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["session_id"]

        resp = await client.get(f"/api/claude-sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

        resp = await client.post(
            f"/api/claude-sessions/{session_id}/send",
            json={"message": "Step 1"},
        )
        assert resp.status_code == 200
        assert resp.json()["message_count"] == 1

        await mgr._dispatch_tasks[session_id]

        resp = await client.get(f"/api/claude-sessions/{session_id}/messages")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        session = await mgr.get_session(session_id)
        session.status = SessionStatus.RUNNING

        resp = await client.post(f"/api/claude-sessions/{session_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        resp = await client.post(f"/api/claude-sessions/{session_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        resp = await client.delete(f"/api/claude-sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
