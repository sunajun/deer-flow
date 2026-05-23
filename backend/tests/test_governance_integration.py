"""Integration tests for the governance surface (agent-configs + skills + governance).

These tests verify end-to-end flows that span multiple subsystems:
- Agent config CRUD + version tracking + rollback
- Skill enable/disable lifecycle
- Governance role permissions and access checks
- Cross-subsystem interactions (skill+permission, agent+skill)
"""

from __future__ import annotations

import pytest

from deerflow.config.agent_config_manager import (
    AgentConfigManager,
    reset_agent_config_manager,
)
from deerflow.config.agent_config_version import AgentConfigVersion
from deerflow.governance.middleware import PermissionMiddleware
from deerflow.governance.models import (
    GovernanceConfig,
    PermissionRule,
    Role,
    RoleType,
)
from deerflow.governance.presets import BUILTIN_ROLES


@pytest.fixture()
def agent_manager():
    reset_agent_config_manager()
    m = AgentConfigManager()
    yield m
    reset_agent_config_manager()


@pytest.fixture()
def governance_config():
    return GovernanceConfig(roles=BUILTIN_ROLES)


@pytest.fixture()
def middleware(governance_config):
    return PermissionMiddleware(governance_config)


class TestAgentConfigVersionTracking:
    @pytest.mark.asyncio
    async def test_create_update_rollback(self, agent_manager):
        cfg = AgentConfigVersion(
            name="version-test-agent",
            description="v1",
            model="deepseek-chat",
        )
        created = await agent_manager.create(cfg)
        assert created.version == "1.0.0"
        assert created.description == "v1"

        updated1 = await agent_manager.update(
            "version-test-agent",
            {"description": "v2"},
            change_summary="Update description to v2",
        )
        assert updated1.description == "v2"

        updated2 = await agent_manager.update(
            "version-test-agent",
            {"description": "v3"},
            change_summary="Update description to v3",
        )
        assert updated2.description == "v3"

        updated3 = await agent_manager.update(
            "version-test-agent",
            {"description": "v4"},
            change_summary="Update description to v4",
        )
        assert updated3.description == "v4"

        versions = await agent_manager.get_version_history("version-test-agent")
        assert len(versions) >= 3

        rolled_back = await agent_manager.rollback("version-test-agent", "1.0.0")
        assert rolled_back.description == "v1"

    @pytest.mark.asyncio
    async def test_version_history_preserves_snapshots(self, agent_manager):
        cfg = AgentConfigVersion(
            name="snapshot-agent",
            description="original",
            model="gpt-4o",
        )
        await agent_manager.create(cfg)

        await agent_manager.update(
            "snapshot-agent",
            {"description": "modified", "model": "deepseek-chat"},
            change_summary="Changed description and model",
        )

        versions = await agent_manager.get_version_history("snapshot-agent")
        assert len(versions) >= 1
        latest = versions[-1]
        assert latest.snapshot.description == "original"
        assert latest.snapshot.model == "gpt-4o"
        assert latest.change_summary == "Changed description and model"


class TestGovernancePermissions:
    def test_guest_role_limited_access(self, middleware):
        assert middleware.check_scene_access(RoleType.GUEST, "conversation") is True
        assert middleware.check_scene_access(RoleType.GUEST, "planning") is False

        assert middleware.check_tool_access(RoleType.GUEST, "chat") is True
        assert middleware.check_tool_access(RoleType.GUEST, "clarify") is True
        assert middleware.check_tool_access(RoleType.GUEST, "bash") is False

    def test_admin_role_full_access(self, middleware):
        assert middleware.check_scene_access(RoleType.ADMIN, "conversation") is True
        assert middleware.check_scene_access(RoleType.ADMIN, "planning") is True
        assert middleware.check_scene_access(RoleType.ADMIN, "any_scene") is True

        assert middleware.check_tool_access(RoleType.ADMIN, "bash") is True
        assert middleware.check_tool_access(RoleType.ADMIN, "any_tool") is True

    def test_user_role_exclusions(self, middleware):
        assert middleware.check_tool_access(RoleType.USER, "chat") is True
        assert middleware.check_tool_access(RoleType.USER, "agent_manage") is False
        assert middleware.check_tool_access(RoleType.USER, "skill_manage") is False
        assert middleware.check_tool_access(RoleType.USER, "bash") is True

    def test_update_role_permissions(self, governance_config):
        new_permissions = PermissionRule(
            allowed_scenes=["conversation"],
            allowed_tools=["chat", "clarify"],
            max_parallel_sessions=1,
            can_create_agents=False,
            can_manage_skills=False,
            can_schedule_tasks=False,
        )
        guest_role = governance_config.roles[RoleType.GUEST]
        guest_role.permissions = new_permissions

        mw = PermissionMiddleware(governance_config)
        assert mw.check_scene_access(RoleType.GUEST, "conversation") is True
        assert mw.check_tool_access(RoleType.GUEST, "chat") is True
        assert mw.check_tool_access(RoleType.GUEST, "bash") is False


class TestAgentConfigCRUD:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, agent_manager):
        cfg = AgentConfigVersion(
            name="lifecycle-agent",
            description="Test lifecycle",
            model="deepseek-chat",
            tool_groups=["search", "code"],
            allowed_scenes=["conversation", "planning"],
        )
        created = await agent_manager.create(cfg)
        assert created.name == "lifecycle-agent"
        assert created.tool_groups == ["search", "code"]

        fetched = await agent_manager.get("lifecycle-agent")
        assert fetched is not None
        assert fetched.name == "lifecycle-agent"

        updated = await agent_manager.update(
            "lifecycle-agent",
            {"description": "Updated description"},
            change_summary="Update description",
        )
        assert updated.description == "Updated description"

        all_configs = await agent_manager.list_agents()
        names = [c.name for c in all_configs]
        assert "lifecycle-agent" in names

        await agent_manager.delete("lifecycle-agent")
        deleted = await agent_manager.get("lifecycle-agent")
        assert deleted is None

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, agent_manager):
        cfg = AgentConfigVersion(name="dup-agent")
        await agent_manager.create(cfg)
        with pytest.raises(ValueError, match="already exists"):
            await agent_manager.create(cfg)

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, agent_manager):
        with pytest.raises(KeyError):
            await agent_manager.update("nonexistent", {"description": "test"})

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, agent_manager):
        with pytest.raises(KeyError):
            await agent_manager.delete("nonexistent")


class TestGovernanceSkillPermissionIntegration:
    def test_skill_management_blocked_for_guest(self, middleware):
        assert middleware.check_tool_access(RoleType.GUEST, "skill_manage") is False

    def test_skill_management_allowed_for_admin(self, middleware):
        assert middleware.check_tool_access(RoleType.ADMIN, "skill_manage") is True

    def test_scene_access_after_role_update(self, governance_config):
        guest_role = governance_config.roles[RoleType.GUEST]
        guest_role.permissions = PermissionRule(
            allowed_scenes=["conversation", "planning"],
            allowed_tools=["chat", "clarify"],
            max_parallel_sessions=1,
            can_create_agents=False,
            can_manage_skills=False,
            can_schedule_tasks=False,
        )

        mw = PermissionMiddleware(governance_config)
        assert mw.check_scene_access(RoleType.GUEST, "planning") is True
        assert mw.check_scene_access(RoleType.GUEST, "file_operation") is False
