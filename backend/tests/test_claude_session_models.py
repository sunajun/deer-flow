from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.claude_session.models import (
    ClaudeSession,
    ClaudeSessionPool,
    SessionConfig,
    SessionMessage,
    SessionStatus,
)


def test_session_status_values():
    assert SessionStatus.IDLE == "idle"
    assert SessionStatus.RUNNING == "running"
    assert SessionStatus.PAUSED == "paused"
    assert SessionStatus.COMPLETED == "completed"
    assert SessionStatus.FAILED == "failed"


def test_claude_session_defaults():
    now = datetime.now(UTC)
    session = ClaudeSession(
        session_id="test-id",
        thread_id="thread-1",
        created_at=now,
        last_active_at=now,
    )
    assert session.session_id == "test-id"
    assert session.thread_id == "thread-1"
    assert session.parent_node_id is None
    assert session.status == SessionStatus.IDLE
    assert session.working_directory is None
    assert session.message_count == 0
    assert session.system_prompt_suffix == ""
    assert session.tool_permissions == []
    assert session.error is None
    assert session.timeout_seconds == 3600


def test_claude_session_with_all_fields():
    now = datetime.now(UTC)
    session = ClaudeSession(
        session_id="s1",
        thread_id="t1",
        parent_node_id="node-1",
        status=SessionStatus.RUNNING,
        working_directory="/tmp/work",
        created_at=now,
        last_active_at=now,
        message_count=5,
        system_prompt_suffix="Be concise",
        tool_permissions=["bash", "write_file"],
        error=None,
        timeout_seconds=7200,
    )
    assert session.status == SessionStatus.RUNNING
    assert session.working_directory == "/tmp/work"
    assert session.tool_permissions == ["bash", "write_file"]
    assert session.timeout_seconds == 7200


def test_claude_session_missing_required_fields():
    with pytest.raises(ValidationError):
        ClaudeSession(session_id="s1")

    with pytest.raises(ValidationError):
        ClaudeSession(thread_id="t1")


def test_session_message_serialization():
    now = datetime.now(UTC)
    msg = SessionMessage(
        session_id="s1",
        role="user",
        content="Hello",
        timestamp=now,
        metadata={"key": "value"},
    )
    data = msg.model_dump()
    assert data["session_id"] == "s1"
    assert data["role"] == "user"
    assert data["content"] == "Hello"
    assert data["metadata"] == {"key": "value"}

    restored = SessionMessage(**data)
    assert restored == msg


def test_session_message_default_metadata():
    now = datetime.now(UTC)
    msg = SessionMessage(
        session_id="s1",
        role="assistant",
        content="Hi",
        timestamp=now,
    )
    assert msg.metadata == {}


def test_claude_session_pool_defaults():
    pool = ClaudeSessionPool(thread_id="t1")
    assert pool.thread_id == "t1"
    assert pool.sessions == {}
    assert pool.max_parallel == 3


def test_claude_session_pool_with_sessions():
    now = datetime.now(UTC)
    s1 = ClaudeSession(session_id="s1", thread_id="t1", created_at=now, last_active_at=now)
    s2 = ClaudeSession(session_id="s2", thread_id="t1", created_at=now, last_active_at=now)
    pool = ClaudeSessionPool(thread_id="t1", sessions={"s1": s1, "s2": s2}, max_parallel=5)
    assert len(pool.sessions) == 2
    assert pool.max_parallel == 5


def test_session_config_defaults():
    config = SessionConfig()
    assert config.enabled is True
    assert config.max_parallel == 3
    assert config.default_timeout == 3600
    assert config.auto_terminate_idle == 1800
    assert config.working_directory is None


def test_session_config_custom():
    config = SessionConfig(
        enabled=False,
        max_parallel=5,
        default_timeout=7200,
        auto_terminate_idle=900,
        working_directory="/tmp/claude",
    )
    assert config.enabled is False
    assert config.max_parallel == 5
    assert config.default_timeout == 7200
    assert config.auto_terminate_idle == 900
    assert config.working_directory == "/tmp/claude"


def test_session_config_extra_allow():
    config = SessionConfig(custom_field="custom_value")
    assert config.model_extra is not None
    assert config.model_extra.get("custom_field") == "custom_value"


def test_claude_session_json_round_trip():
    now = datetime.now(UTC)
    session = ClaudeSession(
        session_id="s1",
        thread_id="t1",
        created_at=now,
        last_active_at=now,
        tool_permissions=["bash"],
    )
    json_str = session.model_dump_json()
    restored = ClaudeSession.model_validate_json(json_str)
    assert restored.session_id == "s1"
    assert restored.tool_permissions == ["bash"]
