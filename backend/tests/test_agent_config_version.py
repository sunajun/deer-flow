from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deerflow.config.agent_config_manager import (
    AgentConfigManager,
    get_agent_config_manager,
    reset_agent_config_manager,
)
from deerflow.config.agent_config_version import AgentConfigVersion


# ===========================================================================
# 1. AgentConfigVersion model
# ===========================================================================


class TestAgentConfigVersionModel:
    def test_inherits_agent_config_fields(self):
        cfg = AgentConfigVersion(name="test-agent")
        assert cfg.name == "test-agent"
        assert cfg.description == ""
        assert cfg.model is None
        assert cfg.tool_groups is None
        assert cfg.skills is None

    def test_default_version(self):
        cfg = AgentConfigVersion(name="test-agent")
        assert cfg.version == "1.0.0"

    def test_custom_version(self):
        cfg = AgentConfigVersion(name="test-agent", version="2.3.5")
        assert cfg.version == "2.3.5"

    def test_extended_fields_defaults(self):
        cfg = AgentConfigVersion(name="test-agent")
        assert cfg.allowed_scenes == []
        assert cfg.skill_whitelist is None
        assert cfg.skill_blacklist is None
        assert cfg.max_retries == 3
        assert cfg.temperature == 0.7
        assert cfg.system_prompt_suffix == ""
        assert cfg.created_at is not None
        assert cfg.updated_at is not None

    def test_full_config(self):
        cfg = AgentConfigVersion(
            name="code-reviewer",
            description="Code review agent",
            model="deepseek-v3",
            tool_groups=["file:read", "bash"],
            skills=["review"],
            version="1.2.0",
            allowed_scenes=["code-review"],
            skill_whitelist=["review"],
            skill_blacklist=["deploy"],
            max_retries=5,
            temperature=0.3,
            system_prompt_suffix="Be thorough.",
        )
        assert cfg.name == "code-reviewer"
        assert cfg.model == "deepseek-v3"
        assert cfg.allowed_scenes == ["code-review"]
        assert cfg.max_retries == 5
        assert cfg.temperature == 0.3
        assert cfg.system_prompt_suffix == "Be thorough."


# ===========================================================================
# 2. AgentConfigManager CRUD
# ===========================================================================


class TestAgentConfigManagerCRUD:
    @pytest.fixture()
    def manager(self):
        m = AgentConfigManager()
        return m

    @pytest.mark.asyncio
    async def test_create_and_get(self, manager):
        cfg = AgentConfigVersion(name="my-agent", description="Test")
        await manager.create(cfg)
        result = await manager.get("my-agent")
        assert result is not None
        assert result.name == "my-agent"
        assert result.description == "Test"

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, manager):
        cfg = AgentConfigVersion(name="dup-agent")
        await manager.create(cfg)
        with pytest.raises(ValueError, match="already exists"):
            await manager.create(cfg)

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, manager):
        result = await manager.get("no-such-agent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, manager):
        result = await manager.list_agents()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_agents(self, manager):
        await manager.create(AgentConfigVersion(name="agent-a"))
        await manager.create(AgentConfigVersion(name="agent-b"))
        result = await manager.list_agents()
        names = [c.name for c in result]
        assert "agent-a" in names
        assert "agent-b" in names

    @pytest.mark.asyncio
    async def test_delete(self, manager):
        await manager.create(AgentConfigVersion(name="del-me"))
        await manager.delete("del-me")
        assert await manager.get("del-me") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            await manager.delete("no-such-agent")


# ===========================================================================
# 3. Version tracking
# ===========================================================================


class TestVersionTracking:
    @pytest.fixture()
    def manager(self):
        return AgentConfigManager()

    @pytest.mark.asyncio
    async def test_update_increments_patch_version(self, manager):
        cfg = AgentConfigVersion(name="versioned-agent", version="1.0.0")
        await manager.create(cfg)
        updated = await manager.update("versioned-agent", {"description": "updated"})
        assert updated.version == "1.0.1"

    @pytest.mark.asyncio
    async def test_update_saves_history(self, manager):
        cfg = AgentConfigVersion(name="hist-agent", version="1.0.0", description="original")
        await manager.create(cfg)
        await manager.update("hist-agent", {"description": "v1"})
        await manager.update("hist-agent", {"description": "v2"})

        history = await manager.get_version_history("hist-agent")
        assert len(history) == 2
        assert history[0].version == "1.0.0"
        assert history[0].snapshot.description == "original"
        assert history[1].version == "1.0.1"
        assert history[1].snapshot.description == "v1"

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            await manager.update("no-agent", {"description": "x"})

    @pytest.mark.asyncio
    async def test_rollback(self, manager):
        cfg = AgentConfigVersion(name="rb-agent", version="1.0.0", description="original", temperature=0.7)
        await manager.create(cfg)
        await manager.update("rb-agent", {"description": "updated", "temperature": 0.3})
        current = await manager.get("rb-agent")
        assert current.description == "updated"
        assert current.temperature == 0.3

        rolled_back = await manager.rollback("rb-agent", "1.0.0")
        assert rolled_back.description == "original"
        assert rolled_back.temperature == 0.7
        assert rolled_back.version == "1.0.2"

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_version_raises(self, manager):
        cfg = AgentConfigVersion(name="rb-no-ver", version="1.0.0")
        await manager.create(cfg)
        with pytest.raises(ValueError, match="not found"):
            await manager.rollback("rb-no-ver", "9.9.9")

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_agent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            await manager.rollback("no-agent", "1.0.0")

    @pytest.mark.asyncio
    async def test_version_history_empty_for_new_agent(self, manager):
        await manager.create(AgentConfigVersion(name="new-agent"))
        history = await manager.get_version_history("new-agent")
        assert history == []

    @pytest.mark.asyncio
    async def test_delete_clears_history(self, manager):
        await manager.create(AgentConfigVersion(name="temp-agent"))
        await manager.update("temp-agent", {"description": "changed"})
        assert len(await manager.get_version_history("temp-agent")) == 1

        await manager.delete("temp-agent")
        await manager.create(AgentConfigVersion(name="temp-agent"))
        history = await manager.get_version_history("temp-agent")
        assert history == []

    @pytest.mark.asyncio
    async def test_max_version_history_limit(self, manager):
        cfg = AgentConfigVersion(name="limit-agent", version="1.0.0")
        await manager.create(cfg)
        for i in range(110):
            await manager.update("limit-agent", {"description": f"change-{i}"})
        history = await manager.get_version_history("limit-agent")
        assert len(history) <= 100


# ===========================================================================
# 4. API endpoints
# ===========================================================================


def _make_test_app():
    from fastapi import FastAPI

    from app.gateway.routers.agent_configs import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(autouse=True)
def _reset_manager():
    reset_agent_config_manager()
    yield
    reset_agent_config_manager()


@pytest.fixture()
def client():
    app = _make_test_app()
    with TestClient(app) as c:
        yield c


class TestAgentConfigsAPI:
    def test_list_empty(self, client):
        response = client.get("/api/agent-configs/")
        assert response.status_code == 200
        assert response.json()["configs"] == []

    def test_create_agent_config(self, client):
        payload = {
            "name": "code-reviewer",
            "description": "Reviews code",
            "model": "deepseek-v3",
            "tool_groups": ["file:read"],
            "version": "1.0.0",
        }
        response = client.post("/api/agent-configs/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "code-reviewer"
        assert data["description"] == "Reviews code"
        assert data["model"] == "deepseek-v3"
        assert data["version"] == "1.0.0"

    def test_create_duplicate_returns_409(self, client):
        payload = {"name": "dup-agent"}
        client.post("/api/agent-configs/", json=payload)
        response = client.post("/api/agent-configs/", json=payload)
        assert response.status_code == 409

    def test_update_agent_config(self, client):
        client.post("/api/agent-configs/", json={"name": "update-me", "description": "original"})
        response = client.put("/api/agent-configs/update-me", json={"description": "updated"})
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "updated"
        assert data["version"] == "1.0.1"

    def test_update_nonexistent_returns_404(self, client):
        response = client.put("/api/agent-configs/ghost", json={"description": "x"})
        assert response.status_code == 404

    def test_delete_agent_config(self, client):
        client.post("/api/agent-configs/", json={"name": "del-me"})
        response = client.delete("/api/agent-configs/del-me")
        assert response.status_code == 204

        response = client.get("/api/agent-configs/")
        assert all(c["name"] != "del-me" for c in response.json()["configs"])

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/agent-configs/no-such")
        assert response.status_code == 404

    def test_get_version_history(self, client):
        client.post("/api/agent-configs/", json={"name": "hist-agent", "description": "v1"})
        client.put("/api/agent-configs/hist-agent", json={"description": "v2"})
        client.put("/api/agent-configs/hist-agent", json={"description": "v3"})

        response = client.get("/api/agent-configs/hist-agent/versions")
        assert response.status_code == 200
        versions = response.json()["versions"]
        assert len(versions) == 2
        assert versions[0]["version"] == "1.0.0"
        assert versions[1]["version"] == "1.0.1"

    def test_get_version_history_nonexistent_returns_404(self, client):
        response = client.get("/api/agent-configs/no-agent/versions")
        assert response.status_code == 404

    def test_rollback_agent_config(self, client):
        client.post("/api/agent-configs/", json={"name": "rb-agent", "description": "original", "temperature": 0.7})
        client.put("/api/agent-configs/rb-agent", json={"description": "changed", "temperature": 0.3})

        response = client.post("/api/agent-configs/rb-agent/rollback", json={"version": "1.0.0"})
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "original"
        assert data["temperature"] == 0.7
        assert data["version"] == "1.0.2"

    def test_rollback_nonexistent_version_returns_422(self, client):
        client.post("/api/agent-configs/", json={"name": "rb-no-ver"})
        response = client.post("/api/agent-configs/rb-no-ver/rollback", json={"version": "9.9.9"})
        assert response.status_code == 422

    def test_rollback_nonexistent_agent_returns_404(self, client):
        response = client.post("/api/agent-configs/no-agent/rollback", json={"version": "1.0.0"})
        assert response.status_code == 404

    def test_full_crud_lifecycle(self, client):
        client.post("/api/agent-configs/", json={"name": "lifecycle", "description": "v1"})
        client.put("/api/agent-configs/lifecycle", json={"description": "v2"})
        client.put("/api/agent-configs/lifecycle", json={"description": "v3"})

        versions_resp = client.get("/api/agent-configs/lifecycle/versions")
        assert len(versions_resp.json()["versions"]) == 2

        rollback_resp = client.post("/api/agent-configs/lifecycle/rollback", json={"version": "1.0.0"})
        assert rollback_resp.json()["description"] == "v1"

        client.delete("/api/agent-configs/lifecycle")
        list_resp = client.get("/api/agent-configs/")
        assert all(c["name"] != "lifecycle" for c in list_resp.json()["configs"])
