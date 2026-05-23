from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ClaudeSession(BaseModel):
    session_id: str
    thread_id: str
    parent_node_id: str | None = None
    status: SessionStatus = SessionStatus.IDLE
    working_directory: str | None = None
    created_at: datetime
    last_active_at: datetime
    message_count: int = 0
    system_prompt_suffix: str = ""
    tool_permissions: list[str] = Field(default_factory=list)
    error: str | None = None
    timeout_seconds: int = 3600


class SessionMessage(BaseModel):
    session_id: str
    role: str
    content: str
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)


class ClaudeSessionPool(BaseModel):
    thread_id: str
    sessions: dict[str, ClaudeSession] = Field(default_factory=dict)
    max_parallel: int = 3


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    max_parallel: int = 3
    default_timeout: int = 3600
    auto_terminate_idle: int = 1800
    working_directory: str | None = None
