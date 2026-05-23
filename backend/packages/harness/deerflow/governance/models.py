from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RoleType(str, Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class PermissionRule(BaseModel):
    allowed_scenes: list[str] = Field(default_factory=lambda: ["conversation"])
    allowed_tools: list[str] = Field(default_factory=lambda: ["chat", "clarify"])
    max_parallel_sessions: int = 1
    can_create_agents: bool = False
    can_manage_skills: bool = False
    can_schedule_tasks: bool = False


class Role(BaseModel):
    role_type: RoleType
    name: str
    description: str = ""
    permissions: PermissionRule
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceConfig(BaseModel):
    enabled: bool = True
    default_role: RoleType = RoleType.USER
    roles: dict[RoleType, Role] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")
