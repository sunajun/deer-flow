import logging
from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.governance.models import GovernanceConfig, PermissionRule, RoleType
from deerflow.governance.presets import BUILTIN_ROLES

logger = logging.getLogger(__name__)


class PermissionMiddlewareState(AgentState):
    pass


class PermissionMiddleware(AgentMiddleware[PermissionMiddlewareState]):
    state_schema = PermissionMiddlewareState

    def __init__(self, config: GovernanceConfig):
        self._config = config

    def resolve_permissions(self, user_role: RoleType) -> PermissionRule:
        role = self._config.roles.get(user_role) or BUILTIN_ROLES.get(user_role)
        if role is None:
            return BUILTIN_ROLES[RoleType.GUEST].permissions
        return role.permissions

    def check_scene_access(self, user_role: RoleType, scene: str) -> bool:
        permissions = self.resolve_permissions(user_role)
        if "*" in permissions.allowed_scenes:
            return True
        return scene in permissions.allowed_scenes

    def check_tool_access(self, user_role: RoleType, tool: str) -> bool:
        permissions = self.resolve_permissions(user_role)
        allowed = permissions.allowed_tools
        excluded = {t[1:] for t in allowed if t.startswith("!")}
        positive = [t for t in allowed if not t.startswith("!")]
        if tool in excluded:
            return False
        if "*" in positive:
            return True
        return tool in positive

    def _get_role_from_state(self, request: ToolCallRequest) -> RoleType:
        state = getattr(request, "state", None) or {}
        role_str = state.get("user_role", "") if isinstance(state, dict) else ""
        if isinstance(state, dict) and "config" in state:
            configurable = state["config"].get("configurable", {})
            role_str = configurable.get("user_role", role_str)
        try:
            return RoleType(role_str)
        except (ValueError, TypeError):
            return self._config.default_role

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        tool_name = request.tool_call.get("name", "")
        user_role = self._get_role_from_state(request)
        if not self.check_tool_access(user_role, tool_name):
            logger.warning("Permission denied: role=%s tool=%s", user_role.value, tool_name)
            return ToolMessage(
                content=f"权限不足：角色 '{user_role.value}' 无权使用工具 '{tool_name}'",
                tool_call_id=request.tool_call.get("id", ""),
                name=tool_name,
            )
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        tool_name = request.tool_call.get("name", "")
        user_role = self._get_role_from_state(request)
        if not self.check_tool_access(user_role, tool_name):
            logger.warning("Permission denied: role=%s tool=%s", user_role.value, tool_name)
            return ToolMessage(
                content=f"权限不足：角色 '{user_role.value}' 无权使用工具 '{tool_name}'",
                tool_call_id=request.tool_call.get("id", ""),
                name=tool_name,
            )
        return await handler(request)

    def get_allowed_tools(self, user_role: RoleType) -> set[str]:
        permissions = self.resolve_permissions(user_role)
        allowed = permissions.allowed_tools
        excluded = {t[1:] for t in allowed if t.startswith("!")}
        positive = [t for t in allowed if not t.startswith("!")]
        if "*" in positive:
            return excluded
        return set(positive) - excluded
