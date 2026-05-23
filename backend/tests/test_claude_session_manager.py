import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from deerflow.claude_session.manager import ClaudeSessionManager
from deerflow.claude_session.models import (
    ClaudeSession,
    SessionConfig,
    SessionStatus,
)


class MockACPAdapter:
    """Mock ACP adapter that simulates ACP communication for testing."""

    def __init__(self, *, responses: list[str] | None = None, fail_on_send: bool = False):
        self._connections: dict[str, ClaudeSession] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._responses = responses or []
        self._response_index = 0
        self._fail_on_send = fail_on_send
        self._closed_connections: list[str] = []

    async def create_connection(self, session: ClaudeSession) -> str:
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = session
        self._queues[connection_id] = asyncio.Queue()
        return connection_id

    async def send_message(self, connection_id: str, message: str) -> None:
        if self._fail_on_send:
            raise ConnectionError("Simulated ACP connection failure")

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
        self._closed_connections.append(connection_id)

    async def check_connection_health(self, connection_id: str) -> bool:
        return connection_id in self._connections

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)


@pytest.fixture
def manager():
    return ClaudeSessionManager(config=SessionConfig(max_parallel=3, auto_terminate_idle=9999))


@pytest.fixture
def manager_no_idle_monitor(manager):
    original = manager._start_idle_monitor

    async def _noop(session_id):
        pass

    manager._start_idle_monitor = _noop
    yield manager
    manager._start_idle_monitor = original


@pytest.fixture
def manager_with_adapter():
    adapter = MockACPAdapter(responses=["Hello from Claude", "Context-aware response"])
    mgr = ClaudeSessionManager(
        config=SessionConfig(max_parallel=3, auto_terminate_idle=9999),
        acp_adapter=adapter,
    )
    original = mgr._start_idle_monitor

    async def _noop(session_id):
        pass

    mgr._start_idle_monitor = _noop
    yield mgr
    mgr._start_idle_monitor = original


@pytest.fixture
def manager_with_failing_adapter():
    adapter = MockACPAdapter(fail_on_send=True)
    mgr = ClaudeSessionManager(
        config=SessionConfig(max_parallel=3, auto_terminate_idle=9999),
        acp_adapter=adapter,
    )
    original = mgr._start_idle_monitor

    async def _noop(session_id):
        pass

    mgr._start_idle_monitor = _noop
    yield mgr
    mgr._start_idle_monitor = original


@pytest.mark.asyncio
async def test_create_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")
    assert session.session_id
    assert session.thread_id == "t1"
    assert session.status == SessionStatus.IDLE
    assert session.message_count == 0

    pool = mgr.pools["t1"]
    assert session.session_id in pool.sessions


@pytest.mark.asyncio
async def test_create_session_with_options(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(
        thread_id="t1",
        parent_node_id="node-1",
        working_directory="/tmp/work",
        system_prompt_suffix="Be concise",
        tool_permissions=["bash"],
        timeout_seconds=7200,
    )
    assert session.parent_node_id == "node-1"
    assert session.working_directory == "/tmp/work"
    assert session.system_prompt_suffix == "Be concise"
    assert session.tool_permissions == ["bash"]
    assert session.timeout_seconds == 7200


@pytest.mark.asyncio
async def test_create_session_parallel_limit(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    for i in range(3):
        await mgr.create_session(thread_id="t1")

    with pytest.raises(RuntimeError, match="max_parallel=3"):
        await mgr.create_session(thread_id="t1")


@pytest.mark.asyncio
async def test_send_message_with_mock_adapter(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "Hello")

    dispatch_task = mgr._dispatch_tasks.get(session.session_id)
    assert dispatch_task is not None
    await dispatch_task

    updated = await mgr.get_session(session.session_id)
    assert updated.message_count == 1
    assert updated.status == SessionStatus.IDLE

    messages = await mgr.get_messages(session.session_id)
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"


@pytest.mark.asyncio
async def test_send_message_to_paused_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    session.status = SessionStatus.PAUSED

    with pytest.raises(RuntimeError, match="paused"):
        await mgr.send_message(session.session_id, "Hello")


@pytest.mark.asyncio
async def test_send_message_to_completed_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    session.status = SessionStatus.COMPLETED

    with pytest.raises(RuntimeError, match="completed"):
        await mgr.send_message(session.session_id, "Hello")


@pytest.mark.asyncio
async def test_pause_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    session.status = SessionStatus.RUNNING
    await mgr.pause_session(session.session_id)

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.PAUSED


@pytest.mark.asyncio
async def test_pause_non_running_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    with pytest.raises(RuntimeError, match="only RUNNING"):
        await mgr.pause_session(session.session_id)


@pytest.mark.asyncio
async def test_resume_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    session.status = SessionStatus.RUNNING
    await mgr.pause_session(session.session_id)
    await mgr.resume_session(session.session_id)

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.RUNNING


@pytest.mark.asyncio
async def test_resume_non_paused_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    with pytest.raises(RuntimeError, match="only PAUSED"):
        await mgr.resume_session(session.session_id)


@pytest.mark.asyncio
async def test_terminate_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    await mgr.terminate_session(session.session_id)

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_continue_session(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.continue_session(session.session_id, "Continue")

    dispatch_task = mgr._dispatch_tasks.get(session.session_id)
    assert dispatch_task is not None
    await dispatch_task

    updated = await mgr.get_session(session.session_id)
    assert updated.message_count == 1


@pytest.mark.asyncio
async def test_list_sessions(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    s1 = await mgr.create_session(thread_id="t1")
    s2 = await mgr.create_session(thread_id="t1")

    sessions = await mgr.list_sessions("t1")
    ids = {s.session_id for s in sessions}
    assert s1.session_id in ids
    assert s2.session_id in ids


@pytest.mark.asyncio
async def test_list_sessions_empty(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    sessions = await mgr.list_sessions("nonexistent")
    assert sessions == []


@pytest.mark.asyncio
async def test_get_messages(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "msg1")
    task1 = mgr._dispatch_tasks[session.session_id]
    await task1

    await mgr.send_message(session.session_id, "msg2")
    task2 = mgr._dispatch_tasks[session.session_id]
    await task2

    messages = await mgr.get_messages(session.session_id)
    assert len(messages) == 2
    assert messages[0].content == "msg1"
    assert messages[1].content == "msg2"


@pytest.mark.asyncio
async def test_get_output_stream(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    stream = await mgr.get_output_stream(session.session_id)
    assert isinstance(stream, asyncio.Queue)


@pytest.mark.asyncio
async def test_get_output_stream_nonexistent(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor

    with pytest.raises(KeyError, match="No output stream"):
        await mgr.get_output_stream("nonexistent")


@pytest.mark.asyncio
async def test_operation_on_nonexistent_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor

    with pytest.raises(KeyError, match="not found"):
        await mgr.get_session("nonexistent")

    with pytest.raises(KeyError, match="not found"):
        await mgr.send_message("nonexistent", "Hello")

    with pytest.raises(KeyError, match="not found"):
        await mgr.pause_session("nonexistent")

    with pytest.raises(KeyError, match="not found"):
        await mgr.resume_session("nonexistent")

    with pytest.raises(KeyError, match="not found"):
        await mgr.terminate_session("nonexistent")

    with pytest.raises(KeyError, match="not found"):
        await mgr.get_messages("nonexistent")


@pytest.mark.asyncio
async def test_send_message_sets_failed_on_acp_error(manager_with_failing_adapter):
    mgr = manager_with_failing_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "Hello")

    dispatch_task = mgr._dispatch_tasks.get(session.session_id)
    assert dispatch_task is not None
    await dispatch_task

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.FAILED
    assert "Simulated ACP connection failure" in updated.error


@pytest.mark.asyncio
async def test_multiple_threads_independent_pools(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    s1 = await mgr.create_session(thread_id="t1")
    s2 = await mgr.create_session(thread_id="t2")

    assert s1.thread_id == "t1"
    assert s2.thread_id == "t2"

    t1_sessions = await mgr.list_sessions("t1")
    t2_sessions = await mgr.list_sessions("t2")
    assert len(t1_sessions) == 1
    assert len(t2_sessions) == 1


@pytest.mark.asyncio
async def test_config_defaults():
    mgr = ClaudeSessionManager()
    assert mgr.max_parallel == 3
    assert mgr.config.default_timeout == 3600
    assert mgr.config.auto_terminate_idle == 1800


@pytest.mark.asyncio
async def test_idle_monitor_cancels_on_terminate():
    mgr = ClaudeSessionManager(config=SessionConfig(max_parallel=3, auto_terminate_idle=9999))

    session = await mgr.create_session(thread_id="t1")
    assert session.session_id in mgr._idle_timer

    await mgr.terminate_session(session.session_id)
    assert session.session_id not in mgr._idle_timer


@pytest.mark.asyncio
async def test_dispatch_to_claude_with_adapter(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr._dispatch_to_claude(session, "Test message")

    assert session.status == SessionStatus.IDLE
    assert session.session_id in mgr._connection_map


@pytest.mark.asyncio
async def test_dispatch_creates_connection(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    assert session.session_id not in mgr._connection_map

    await mgr._dispatch_to_claude(session, "Test")

    assert session.session_id in mgr._connection_map


@pytest.mark.asyncio
async def test_dispatch_reuses_connection(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr._dispatch_to_claude(session, "First")
    connection_id_1 = mgr._connection_map[session.session_id]

    await mgr._dispatch_to_claude(session, "Second")
    connection_id_2 = mgr._connection_map[session.session_id]

    assert connection_id_1 == connection_id_2


@pytest.mark.asyncio
async def test_stream_output_yields_structured_chunks(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "Hello")

    chunks = []
    async for chunk in mgr.stream_output(session.session_id):
        chunks.append(chunk)

    text_chunks = [c for c in chunks if c["type"] == "text"]
    end_chunks = [c for c in chunks if c["type"] == "end"]

    assert len(text_chunks) > 0
    assert len(end_chunks) == 1

    for c in text_chunks:
        assert "type" in c
        assert "content" in c
        assert "timestamp" in c
        assert c["type"] == "text"

    assert end_chunks[0]["type"] == "end"


@pytest.mark.asyncio
async def test_stream_output_buffered(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "Hello")

    async for _ in mgr.stream_output(session.session_id):
        pass

    buffered = await mgr.get_buffered_output(session.session_id)
    assert len(buffered) > 0
    assert all("type" in c and "content" in c for c in buffered)


@pytest.mark.asyncio
async def test_terminate_session_closes_acp_connection(manager_with_adapter):
    mgr = manager_with_adapter
    adapter = mgr._acp_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr._dispatch_to_claude(session, "Test")
    connection_id = mgr._connection_map.get(session.session_id)
    assert connection_id is not None

    await mgr.terminate_session(session.session_id)

    assert session.session_id not in mgr._connection_map
    assert connection_id in adapter._closed_connections


@pytest.mark.asyncio
async def test_terminate_session_sends_none_sentinel(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.terminate_session(session.session_id)

    queue = mgr._output_streams.get(session.session_id)
    assert queue is not None
    sentinel = queue.get_nowait()
    assert sentinel is None


@pytest.mark.asyncio
async def test_terminate_cancels_dispatch_task(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    async def _slow_dispatch(session, message):
        await asyncio.sleep(10)

    mgr._dispatch_to_claude = _slow_dispatch

    await mgr.send_message(session.session_id, "Hello")
    assert session.session_id in mgr._dispatch_tasks
    assert not mgr._dispatch_tasks[session.session_id].done()

    await mgr.terminate_session(session.session_id)

    assert mgr._dispatch_tasks.get(session.session_id) is None


@pytest.mark.asyncio
async def test_multiple_sessions_parallel(manager_with_adapter):
    mgr = manager_with_adapter
    sessions = []
    for i in range(3):
        s = await mgr.create_session(thread_id="t1")
        sessions.append(s)

    for s in sessions:
        await mgr.send_message(s.session_id, f"Message to session {s.session_id[:8]}")

    for _ in range(50):
        all_done = all(s.session_id not in mgr._dispatch_tasks or mgr._dispatch_tasks[s.session_id].done() for s in sessions)
        if all_done:
            break
        await asyncio.sleep(0.05)

    for s in sessions:
        updated = await mgr.get_session(s.session_id)
        assert updated.status == SessionStatus.IDLE
        assert updated.message_count == 1


@pytest.mark.asyncio
async def test_session_continuation(manager_with_adapter):
    mgr = manager_with_adapter
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
async def test_send_message_rejects_concurrent_dispatch(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    async def _slow_dispatch(session, message):
        await asyncio.sleep(10)

    mgr._dispatch_to_claude = _slow_dispatch

    await mgr.send_message(session.session_id, "Hello")

    with pytest.raises(RuntimeError, match="active dispatch"):
        await mgr.send_message(session.session_id, "Hello again")


@pytest.mark.asyncio
async def test_idle_timeout_auto_terminates():
    mgr = ClaudeSessionManager(
        config=SessionConfig(max_parallel=3, auto_terminate_idle=0),
    )
    session = await mgr.create_session(thread_id="t1")

    await asyncio.sleep(0.1)

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.COMPLETED
    assert "idle timeout" in updated.error


@pytest.mark.asyncio
async def test_acp_connection_health_check(manager_with_adapter):
    mgr = manager_with_adapter
    adapter = mgr._acp_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr._dispatch_to_claude(session, "Test")
    connection_id = mgr._connection_map[session.session_id]

    healthy = await adapter.check_connection_health(connection_id)
    assert healthy is True

    unknown_healthy = await adapter.check_connection_health("nonexistent")
    assert unknown_healthy is False


@pytest.mark.asyncio
async def test_acp_adapter_close_connection():
    adapter = MockACPAdapter()
    session = ClaudeSession(
        session_id="test-s",
        thread_id="t1",
        created_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
    )
    conn_id = await adapter.create_connection(session)
    assert adapter.active_connection_count == 1

    await adapter.close_connection(conn_id)
    assert adapter.active_connection_count == 0

    healthy = await adapter.check_connection_health(conn_id)
    assert healthy is False


@pytest.mark.asyncio
async def test_acp_adapter_send_message_unknown_connection():
    adapter = MockACPAdapter()
    with pytest.raises(KeyError, match="not found"):
        await adapter.send_message("nonexistent", "Hello")


@pytest.mark.asyncio
async def test_acp_adapter_receive_output_unknown_connection():
    adapter = MockACPAdapter()
    with pytest.raises(KeyError, match="not found"):
        async for _ in adapter.receive_output("nonexistent"):
            pass


@pytest.mark.asyncio
async def test_manager_without_adapter_dispatch_handles_gracefully():
    mgr = ClaudeSessionManager(config=SessionConfig(max_parallel=3, auto_terminate_idle=9999))

    original = mgr._start_idle_monitor

    async def _noop(session_id):
        pass

    mgr._start_idle_monitor = _noop

    session = await mgr.create_session(thread_id="t1")

    await mgr._dispatch_to_claude(session, "Test")

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.FAILED

    mgr._start_idle_monitor = original


@pytest.mark.asyncio
async def test_dispatch_failure_puts_none_sentinel(manager_with_failing_adapter):
    mgr = manager_with_failing_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "Hello")

    dispatch_task = mgr._dispatch_tasks[session.session_id]
    await dispatch_task

    queue = mgr._output_streams[session.session_id]
    assert queue.empty() or queue.get_nowait() is None


@pytest.mark.asyncio
async def test_stream_output_on_terminated_session(manager_with_adapter):
    mgr = manager_with_adapter
    session = await mgr.create_session(thread_id="t1")

    await mgr.send_message(session.session_id, "Hello")
    await mgr._dispatch_tasks[session.session_id]

    await mgr.terminate_session(session.session_id)

    chunks = []
    queue = mgr._output_streams[session.session_id]
    while not queue.empty():
        chunk = queue.get_nowait()
        if chunk is None:
            chunks.append({"type": "end", "content": "", "timestamp": datetime.now(UTC).isoformat()})
            break
        chunks.append(chunk)

    assert any(c["type"] == "end" for c in chunks)
