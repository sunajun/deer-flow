import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deerflow.config.agent_config_manager import get_agent_config_manager
from deerflow.config.agent_config_version import AgentConfigVersion, AgentConfigVersionSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-configs", tags=["agent-configs"])


class AgentConfigCreateRequest(BaseModel):
    name: str = Field(..., description="Agent name")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    skills: list[str] | None = Field(default=None, description="Optional skill whitelist")
    version: str = Field(default="1.0.0", description="Initial version")
    allowed_scenes: list[str] = Field(default_factory=list, description="Allowed scene IDs")
    skill_whitelist: list[str] | None = Field(default=None, description="Skill whitelist override")
    skill_blacklist: list[str] | None = Field(default=None, description="Skill blacklist override")
    max_retries: int = Field(default=3, description="Max retries for the agent")
    temperature: float = Field(default=0.7, description="Temperature for the agent")
    system_prompt_suffix: str = Field(default="", description="Suffix appended to system prompt")


class AgentConfigUpdateRequest(BaseModel):
    description: str | None = Field(default=None, description="Updated description")
    model: str | None = Field(default=None, description="Updated model override")
    tool_groups: list[str] | None = Field(default=None, description="Updated tool group whitelist")
    skills: list[str] | None = Field(default=None, description="Updated skill whitelist")
    allowed_scenes: list[str] | None = Field(default=None, description="Updated allowed scene IDs")
    skill_whitelist: list[str] | None = Field(default=None, description="Updated skill whitelist")
    skill_blacklist: list[str] | None = Field(default=None, description="Updated skill blacklist")
    max_retries: int | None = Field(default=None, description="Updated max retries")
    temperature: float | None = Field(default=None, description="Updated temperature")
    system_prompt_suffix: str | None = Field(default=None, description="Updated system prompt suffix")
    change_summary: str = Field(default="", description="Summary of changes")


class RollbackRequest(BaseModel):
    version: str = Field(..., description="Target version to rollback to")


class AgentConfigListResponse(BaseModel):
    configs: list[AgentConfigVersion]


class VersionHistoryResponse(BaseModel):
    versions: list[AgentConfigVersionSnapshot]


@router.get(
    "/",
    response_model=AgentConfigListResponse,
    summary="List Agent Configs",
    description="List all agent configurations with version info.",
)
async def list_agent_configs() -> AgentConfigListResponse:
    manager = get_agent_config_manager()
    configs = await manager.list_agents()
    return AgentConfigListResponse(configs=configs)


@router.post(
    "/",
    response_model=AgentConfigVersion,
    status_code=201,
    summary="Create Agent Config",
    description="Create a new agent configuration with version tracking.",
)
async def create_agent_config(request: AgentConfigCreateRequest) -> AgentConfigVersion:
    manager = get_agent_config_manager()
    config = AgentConfigVersion(
        name=request.name,
        description=request.description,
        model=request.model,
        tool_groups=request.tool_groups,
        skills=request.skills,
        version=request.version,
        allowed_scenes=request.allowed_scenes,
        skill_whitelist=request.skill_whitelist,
        skill_blacklist=request.skill_blacklist,
        max_retries=request.max_retries,
        temperature=request.temperature,
        system_prompt_suffix=request.system_prompt_suffix,
    )
    try:
        return await manager.create(config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put(
    "/{agent_name}",
    response_model=AgentConfigVersion,
    summary="Update Agent Config",
    description="Update an agent configuration. Automatically saves the previous version to history and increments the patch version.",
)
async def update_agent_config(agent_name: str, request: AgentConfigUpdateRequest) -> AgentConfigVersion:
    manager = get_agent_config_manager()
    updates = {k: v for k, v in request.model_dump(exclude={"change_summary"}).items() if v is not None}
    try:
        return await manager.update(agent_name, updates, change_summary=request.change_summary)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{agent_name}",
    status_code=204,
    summary="Delete Agent Config",
    description="Delete an agent configuration and its version history.",
)
async def delete_agent_config(agent_name: str) -> None:
    manager = get_agent_config_manager()
    try:
        await manager.delete(agent_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{agent_name}/versions",
    response_model=VersionHistoryResponse,
    summary="Get Version History",
    description="Retrieve the version history for an agent configuration.",
)
async def get_version_history(agent_name: str) -> VersionHistoryResponse:
    manager = get_agent_config_manager()
    config = await manager.get(agent_name)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Agent config '{agent_name}' not found")
    versions = await manager.get_version_history(agent_name)
    return VersionHistoryResponse(versions=versions)


@router.post(
    "/{agent_name}/rollback",
    response_model=AgentConfigVersion,
    summary="Rollback Agent Config",
    description="Rollback an agent configuration to a specific version.",
)
async def rollback_agent_config(agent_name: str, request: RollbackRequest) -> AgentConfigVersion:
    manager = get_agent_config_manager()
    try:
        return await manager.rollback(agent_name, request.version)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
