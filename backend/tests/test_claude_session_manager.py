import asyncio

import pytest

from deerflow.claude_session.manager import ClaudeSessionManager
from deerflow.claude_session.models import SessionConfig, SessionStatus


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
async def test_send_message_raises_not_implemented(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    with pytest.raises(NotImplementedError, match="_dispatch_to_claude"):
        await mgr.send_message(session.session_id, "Hello")


@pytest.mark.asyncio
async def test_send_message_updates_state(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor

    async def _fake_dispatch(session, message):
        pass

    mgr._dispatch_to_claude = _fake_dispatch

    session = await mgr.create_session(thread_id="t1")
    await mgr.send_message(session.session_id, "Hello")

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.RUNNING
    assert updated.message_count == 1

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
async def test_continue_session(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor

    async def _fake_dispatch(session, message):
        pass

    mgr._dispatch_to_claude = _fake_dispatch

    session = await mgr.create_session(thread_id="t1")
    await mgr.continue_session(session.session_id, "Continue")

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.RUNNING
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
async def test_get_messages(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor

    async def _fake_dispatch(session, message):
        pass

    mgr._dispatch_to_claude = _fake_dispatch

    session = await mgr.create_session(thread_id="t1")
    await mgr.send_message(session.session_id, "msg1")
    await mgr.send_message(session.session_id, "msg2")

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
async def test_dispatch_to_claude_skeleton(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor
    session = await mgr.create_session(thread_id="t1")

    with pytest.raises(NotImplementedError, match="T21"):
        await mgr._dispatch_to_claude(session, "test")


@pytest.mark.asyncio
async def test_send_message_sets_failed_on_dispatch_error(manager_no_idle_monitor):
    mgr = manager_no_idle_monitor

    async def _failing_dispatch(session, message):
        raise ConnectionError("Connection lost")

    mgr._dispatch_to_claude = _failing_dispatch

    session = await mgr.create_session(thread_id="t1")

    with pytest.raises(ConnectionError):
        await mgr.send_message(session.session_id, "Hello")

    updated = await mgr.get_session(session.session_id)
    assert updated.status == SessionStatus.FAILED
    assert updated.error == "Connection lost"


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
