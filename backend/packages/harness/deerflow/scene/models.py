from enum import Enum

from pydantic import BaseModel, Field


class SceneType(str, Enum):
    CONVERSATION = "conversation"
    PLANNING = "planning"
    FILE_OPERATION = "file_operation"
    WEB_SEARCH = "web_search"
    GOVERNANCE = "governance"
    AUTOMATION = "automation"
    SANDBOX_RUNTIME = "sandbox"


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL = "full"


class ToolGroup(BaseModel):
    name: str
    tool_ids: list[str]
    permission: PermissionLevel = PermissionLevel.READ_ONLY


class Scene(BaseModel):
    type: SceneType
    name: str
    description: str
    tool_groups: list[ToolGroup]
    auto_deactivate_after: int = 300
    activates_plan_mode: bool = False
    priority: int = 0
