import asyncio
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage

from deerflow.governance.middleware import PermissionMiddleware
from deerflow.governance.models import GovernanceConfig, PermissionRule, Role, RoleType
from deerflow.governance.presets import BUILTIN_ROLES


def _make_tool_call_request(name: str = "bash", args: dict | None = None, call_id: str = "call_1"):
    req = MagicMock()
    req.tool_call = {"name": name, "args": args or {}, "id": call_id}
    return req


def _default_config() -> GovernanceConfig:
    return GovernanceConfig(roles=BUILTIN_ROLES)


class TestRoleType:
    def test_values(self):
        assert RoleType.ADMIN.value == "admin"
        assert RoleType.USER.value == "user"
        assert RoleType.GUEST.value == "guest"

    def test_from_string(self):
        assert RoleType("admin") is RoleType.ADMIN
        assert RoleType("user") is RoleType.USER
        assert RoleType("guest") is RoleType.GUEST

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            RoleType("superadmin")


class TestPermissionRule:
    def test_defaults(self):
        rule = PermissionRule()
        assert rule.allowed_scenes == ["conversation"]
        assert rule.allowed_tools == ["chat", "clarify"]
        assert rule.max_parallel_sessions == 1
        assert rule.can_create_agents is False
        assert rule.can_manage_skills is False
        assert rule.can_schedule_tasks is False

    def test_custom_values(self):
        rule = PermissionRule(
            allowed_scenes=["*"],
            allowed_tools=["*", "!agent_manage"],
            max_parallel_sessions=10,
            can_create_agents=True,
            can_manage_skills=True,
            can_schedule_tasks=True,
        )
        assert rule.allowed_scenes == ["*"]
        assert rule.allowed_tools == ["*", "!agent_manage"]
        assert rule.max_parallel_sessions == 10


class TestBuiltinRoles:
    def test_all_role_types_present(self):
        assert set(BUILTIN_ROLES.keys()) == {RoleType.ADMIN, RoleType.USER, RoleType.GUEST}

    def test_admin_permissions(self):
        admin = BUILTIN_ROLES[RoleType.ADMIN]
        assert admin.permissions.allowed_scenes == ["*"]
        assert admin.permissions.allowed_tools == ["*"]
        assert admin.permissions.can_create_agents is True
        assert admin.permissions.can_manage_skills is True
        assert admin.permissions.can_schedule_tasks is True

    def test_user_permissions(self):
        user = BUILTIN_ROLES[RoleType.USER]
        assert "conversation" in user.permissions.allowed_scenes
        assert "*" in user.permissions.allowed_tools
        assert "!agent_manage" in user.permissions.allowed_tools
        assert user.permissions.can_create_agents is False

    def test_guest_permissions(self):
        guest = BUILTIN_ROLES[RoleType.GUEST]
        assert guest.permissions.allowed_scenes == ["conversation"]
        assert guest.permissions.allowed_tools == ["chat", "clarify"]
        assert guest.permissions.max_parallel_sessions == 1

    def test_permission_level_decreasing(self):
        admin = BUILTIN_ROLES[RoleType.ADMIN]
        user = BUILTIN_ROLES[RoleType.USER]
        guest = BUILTIN_ROLES[RoleType.GUEST]
        assert admin.permissions.max_parallel_sessions >= user.permissions.max_parallel_sessions
        assert user.permissions.max_parallel_sessions >= guest.permissions.max_parallel_sessions


class TestPermissionMiddlewareToolAccess:
    def setup_method(self):
        self.mw = PermissionMiddleware(_default_config())

    def test_admin_all_tools_allowed(self):
        assert self.mw.check_tool_access(RoleType.ADMIN, "bash") is True
        assert self.mw.check_tool_access(RoleType.ADMIN, "agent_manage") is True
        assert self.mw.check_tool_access(RoleType.ADMIN, "anything") is True

    def test_guest_only_chat_clarify(self):
        assert self.mw.check_tool_access(RoleType.GUEST, "chat") is True
        assert self.mw.check_tool_access(RoleType.GUEST, "clarify") is True
        assert self.mw.check_tool_access(RoleType.GUEST, "bash") is False
        assert self.mw.check_tool_access(RoleType.GUEST, "web_search") is False

    def test_user_wildcard_with_exclusion(self):
        assert self.mw.check_tool_access(RoleType.USER, "chat") is True
        assert self.mw.check_tool_access(RoleType.USER, "bash") is True
        assert self.mw.check_tool_access(RoleType.USER, "agent_manage") is False
        assert self.mw.check_tool_access(RoleType.USER, "skill_manage") is False

    def test_wildcard_only_allows_all(self):
        config = GovernanceConfig(
            roles={RoleType.ADMIN: Role(role_type=RoleType.ADMIN, name="admin", description="", permissions=PermissionRule(allowed_tools=["*"]))}
        )
        mw = PermissionMiddleware(config)
        assert mw.check_tool_access(RoleType.ADMIN, "anything") is True

    def test_exclusion_overrides_wildcard(self):
        config = GovernanceConfig(
            roles={RoleType.USER: Role(role_type=RoleType.USER, name="user", description="", permissions=PermissionRule(allowed_tools=["*", "!dangerous"]))}
        )
        mw = PermissionMiddleware(config)
        assert mw.check_tool_access(RoleType.USER, "chat") is True
        assert mw.check_tool_access(RoleType.USER, "dangerous") is False


class TestPermissionMiddlewareSceneAccess:
    def setup_method(self):
        self.mw = PermissionMiddleware(_default_config())

    def test_admin_all_scenes(self):
        assert self.mw.check_scene_access(RoleType.ADMIN, "conversation") is True
        assert self.mw.check_scene_access(RoleType.ADMIN, "governance") is True

    def test_user_limited_scenes(self):
        assert self.mw.check_scene_access(RoleType.USER, "conversation") is True
        assert self.mw.check_scene_access(RoleType.USER, "planning") is True
        assert self.mw.check_scene_access(RoleType.USER, "governance") is False

    def test_guest_conversation_only(self):
        assert self.mw.check_scene_access(RoleType.GUEST, "conversation") is True
        assert self.mw.check_scene_access(RoleType.GUEST, "planning") is False


class TestPermissionMiddlewareWrapToolCall:
    def setup_method(self):
        self.mw = PermissionMiddleware(_default_config())

    def test_allowed_tool_passes_through(self):
        req = _make_tool_call_request("chat")
        expected = MagicMock()
        handler = MagicMock(return_value=expected)
        result = self.mw.wrap_tool_call(req, handler)
        handler.assert_called_once_with(req)
        assert result is expected

    def test_denied_tool_returns_error_message(self):
        req = _make_tool_call_request("bash")
        req.state = {"user_role": "guest"}
        handler = MagicMock()
        result = self.mw.wrap_tool_call(req, handler)
        handler.assert_not_called()
        assert isinstance(result, ToolMessage)
        assert "权限不足" in result.content
        assert "guest" in result.content
        assert "bash" in result.content
        assert result.name == "bash"

    def test_user_excluded_tool_denied(self):
        req = _make_tool_call_request("agent_manage")
        mw = PermissionMiddleware(_default_config())
        req.state = {"user_role": "user"}
        handler = MagicMock()
        result = mw.wrap_tool_call(req, handler)
        handler.assert_not_called()
        assert isinstance(result, ToolMessage)
        assert "权限不足" in result.content

    def test_admin_tool_always_passes(self):
        req = _make_tool_call_request("agent_manage")
        mw = PermissionMiddleware(_default_config())
        req.state = {"user_role": "admin"}
        expected = MagicMock()
        handler = MagicMock(return_value=expected)
        result = mw.wrap_tool_call(req, handler)
        handler.assert_called_once_with(req)
        assert result is expected


class TestPermissionMiddlewareAwrapToolCall:
    def setup_method(self):
        self.mw = PermissionMiddleware(_default_config())

    def test_async_allowed(self):
        req = _make_tool_call_request("chat")
        expected = MagicMock()

        async def handler(r):
            return expected

        result = asyncio.run(self.mw.awrap_tool_call(req, handler))
        assert result is expected

    def test_async_denied(self):
        req = _make_tool_call_request("bash")
        req.state = {"user_role": "guest"}

        async def handler(r):
            return MagicMock()

        result = asyncio.run(self.mw.awrap_tool_call(req, handler))
        assert isinstance(result, ToolMessage)
        assert "权限不足" in result.content

    def test_async_user_excluded_tool(self):
        req = _make_tool_call_request("agent_manage")
        mw = PermissionMiddleware(_default_config())
        req.state = {"user_role": "user"}

        async def handler(r):
            return MagicMock()

        result = asyncio.run(mw.awrap_tool_call(req, handler))
        assert isinstance(result, ToolMessage)
        assert "权限不足" in result.content


class TestPermissionMiddlewareGetAllowedTools:
    def test_admin_wildcard_returns_excluded_set(self):
        mw = PermissionMiddleware(_default_config())
        result = mw.get_allowed_tools(RoleType.ADMIN)
        assert result == set()

    def test_user_wildcard_with_exclusions(self):
        mw = PermissionMiddleware(_default_config())
        result = mw.get_allowed_tools(RoleType.USER)
        assert "agent_manage" in result
        assert "skill_manage" in result

    def test_guest_explicit_list(self):
        mw = PermissionMiddleware(_default_config())
        result = mw.get_allowed_tools(RoleType.GUEST)
        assert result == {"chat", "clarify"}


class TestPermissionMiddlewareResolvePermissions:
    def test_resolve_builtin_role(self):
        mw = PermissionMiddleware(_default_config())
        perms = mw.resolve_permissions(RoleType.ADMIN)
        assert perms.allowed_tools == ["*"]

    def test_resolve_missing_role_falls_back_to_guest(self):
        config = GovernanceConfig(roles={})
        mw = PermissionMiddleware(config)
        perms = mw.resolve_permissions(RoleType.GUEST)
        assert perms.allowed_tools == ["chat", "clarify"]

    def test_resolve_config_role_overrides_builtin(self):
        custom = Role(
            role_type=RoleType.ADMIN,
            name="受限管理员",
            description="",
            permissions=PermissionRule(allowed_tools=["read_file"], allowed_scenes=["conversation"]),
        )
        config = GovernanceConfig(roles={RoleType.ADMIN: custom})
        mw = PermissionMiddleware(config)
        perms = mw.resolve_permissions(RoleType.ADMIN)
        assert perms.allowed_tools == ["read_file"]


class TestGovernanceConfig:
    def test_defaults(self):
        config = GovernanceConfig()
        assert config.enabled is True
        assert config.default_role == RoleType.USER
        assert config.roles == {}

    def test_custom_config(self):
        config = GovernanceConfig(
            enabled=False,
            default_role=RoleType.GUEST,
            roles=BUILTIN_ROLES,
        )
        assert config.enabled is False
        assert config.default_role == RoleType.GUEST
        assert RoleType.ADMIN in config.roles

    def test_model_validate_from_dict(self):
        data = {
            "enabled": True,
            "default_role": "user",
            "roles": {
                "admin": {
                    "role_type": "admin",
                    "name": "管理员",
                    "description": "完全控制权限",
                    "permissions": {
                        "allowed_scenes": ["*"],
                        "allowed_tools": ["*"],
                        "max_parallel_sessions": 10,
                        "can_create_agents": True,
                        "can_manage_skills": True,
                        "can_schedule_tasks": True,
                    },
                },
            },
        }
        config = GovernanceConfig.model_validate(data)
        assert config.enabled is True
        assert RoleType.ADMIN in config.roles
        assert config.roles[RoleType.ADMIN].permissions.allowed_tools == ["*"]


class TestGovernanceAPI:
    def test_list_roles(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/api/governance/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data
        assert "admin" in data["roles"]
        assert "user" in data["roles"]
        assert "guest" in data["roles"]

    def test_get_permissions(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/api/governance/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert "role" in data
        assert "permissions" in data

    def test_check_access_scene(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/governance/check-access", json={"role": "admin", "resource_type": "scene", "resource_id": "conversation"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True

    def test_check_access_tool(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/governance/check-access", json={"role": "guest", "resource_type": "tool", "resource_id": "bash"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False

    def test_check_access_invalid_role(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/governance/check-access", json={"role": "superadmin", "resource_type": "tool", "resource_id": "bash"})
        assert resp.status_code == 400

    def test_check_access_invalid_resource_type(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/governance/check-access", json={"role": "admin", "resource_type": "unknown", "resource_id": "x"})
        assert resp.status_code == 400

    def test_update_role(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        new_perms = {
            "allowed_scenes": ["conversation"],
            "allowed_tools": ["chat"],
            "max_parallel_sessions": 1,
            "can_create_agents": False,
            "can_manage_skills": False,
            "can_schedule_tasks": False,
        }
        resp = client.put("/api/governance/roles/user", json=new_perms)
        assert resp.status_code == 200
        data = resp.json()
        assert data["permissions"]["allowed_tools"] == ["chat"]

    def test_update_invalid_role(self):
        from fastapi.testclient import TestClient

        from app.gateway.routers.governance import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.put("/api/governance/roles/nonexistent", json={"allowed_scenes": [], "allowed_tools": [], "max_parallel_sessions": 1})
        assert resp.status_code == 400
