from datetime import datetime

from pydantic import BaseModel, Field

from deerflow.config.agents_config import AgentConfig


class AgentConfigVersion(AgentConfig):
    version: str = "1.0.0"
    allowed_scenes: list[str] = Field(default_factory=list)
    skill_whitelist: list[str] | None = None
    skill_blacklist: list[str] | None = None
    max_retries: int = 3
    temperature: float = 0.7
    system_prompt_suffix: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AgentConfigVersionSnapshot(BaseModel):
    agent_name: str
    version: str
    snapshot: AgentConfigVersion
    created_at: datetime = Field(default_factory=datetime.now)
    change_summary: str = ""
