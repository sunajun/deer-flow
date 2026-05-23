from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.routers.marketplace import router
from deerflow.marketplace.models import (
    MarketplaceConfig,
    SkillCategory,
    SkillManifest,
    SkillRegistryEntry,
)
from deerflow.marketplace.updater import SkillUpdater


def _sample_manifest(**overrides) -> SkillManifest:
    base = {
        "skill_id": "web-search",
        "name": "Web Search",
        "description": "Search the web",
        "version": "1.0.0",
        "category": SkillCategory.productivity,
        "tags": ["search", "web"],
        "author": "deerflow",
        "repository": "https://github.com/example/web-search",
        "homepage": "https://example.com",
        "archive_url": "https://example.com/web-search.skill",
        "checksum": "",
        "dependencies": ["httpx"],
        "permissions": ["network"],
        "changelog": "Initial release",
    }
    base.update(overrides)
    return SkillManifest(**base)


def _make_registry_with_entries(*manifests: SkillManifest) -> MagicMock:
    registry = MagicMock(spec=[])
    entries = {}
    for m in manifests:
        entries[m.skill_id] = SkillRegistryEntry(
            manifest=m,
            installed=False,
            installed_version=None,
        )
    registry._entries = entries
    registry.list_skills = AsyncMock(return_value=list(entries.values()))
    registry.search = AsyncMock(return_value=list(entries.values()))
    registry.get_skill = AsyncMock(side_effect=lambda sid: entries.get(sid))
    registry.get_categories = AsyncMock(
        return_value=[
            {"category": "productivity", "count": len(manifests)},
        ]
    )
    registry.install_skill = AsyncMock(return_value={"skill_id": manifests[0].skill_id, "install_path": "/tmp/test"})
    registry.uninstall_skill = AsyncMock()
    registry.check_updates = AsyncMock(return_value=[])
    registry.update_skill = AsyncMock(return_value={"skill_id": manifests[0].skill_id, "install_path": "/tmp/test"})
    registry.fetch_index = AsyncMock()
    registry._index = None
    registry._index_fetched_at = None
    return registry


def _make_updater(registry: MagicMock, config: MarketplaceConfig | None = None) -> SkillUpdater:
    cfg = config or MarketplaceConfig(cache_ttl=3600)
    updater = SkillUpdater(registry, cfg)
    return updater


@contextmanager
def _make_client(registry: MagicMock, updater: SkillUpdater | None = None):
    app = make_authed_test_app()
    app.include_router(router)
    client = TestClient(app)
    with patch("app.gateway.routers.marketplace._get_registry", return_value=registry):
        if updater is not None:
            with patch("app.gateway.routers.marketplace._get_updater", return_value=updater):
                yield client
        else:
            yield client


@pytest.fixture
def sample_registry():
    return _make_registry_with_entries(
        _sample_manifest(),
        _sample_manifest(
            skill_id="code-gen",
            name="Code Generator",
            description="Generate code",
            category=SkillCategory.development,
            tags=["code"],
        ),
    )


class TestE2EBrowseInstallUpdateUninstall:
    def test_full_api_lifecycle(self, sample_registry):
        sample_registry.install_skill = AsyncMock(return_value={"skill_id": "web-search", "install_path": "/tmp/web-search"})
        sample_registry.check_updates = AsyncMock(
            return_value=[
                {
                    "skill_id": "web-search",
                    "installed_version": "1.0.0",
                    "available_version": "2.0.0",
                }
            ]
        )
        sample_registry.update_skill = AsyncMock(return_value={"skill_id": "web-search", "install_path": "/tmp/web-search"})
        sample_registry.uninstall_skill = AsyncMock()

        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills")
            assert resp.status_code == 200
            assert len(resp.json()["skills"]) == 2

            resp = client.get("/api/marketplace/skills/web-search")
            assert resp.status_code == 200
            assert resp.json()["skill_id"] == "web-search"

            resp = client.post("/api/marketplace/skills/web-search/install")
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            resp = client.get("/api/marketplace/updates")
            assert resp.status_code == 200
            updates = resp.json()["updates"]
            assert len(updates) == 1
            assert updates[0]["available_version"] == "2.0.0"

            resp = client.post("/api/marketplace/skills/web-search/update")
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            resp = client.post("/api/marketplace/skills/web-search/uninstall")
            assert resp.status_code == 200
            assert resp.json()["success"] is True


class TestE2ESearchInstallCheckUpdate:
    def test_search_to_update_flow(self, sample_registry):
        sample_registry.search = AsyncMock(return_value=[sample_registry._entries["web-search"]])
        sample_registry.get_skill = AsyncMock(return_value=sample_registry._entries["web-search"])
        sample_registry.install_skill = AsyncMock(return_value={"skill_id": "web-search", "install_path": "/tmp/web-search"})
        sample_registry.check_updates = AsyncMock(
            return_value=[
                {
                    "skill_id": "web-search",
                    "installed_version": "1.0.0",
                    "available_version": "1.1.0",
                }
            ]
        )
        sample_registry.update_skill = AsyncMock(return_value={"skill_id": "web-search", "install_path": "/tmp/web-search"})

        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills?query=search")
            assert resp.status_code == 200
            assert len(resp.json()["skills"]) >= 1

            resp = client.get("/api/marketplace/skills/web-search")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["name"] == "Web Search"

            resp = client.post("/api/marketplace/skills/web-search/install")
            assert resp.status_code == 200

            resp = client.get("/api/marketplace/updates")
            assert resp.status_code == 200
            assert len(resp.json()["updates"]) == 1

            resp = client.post("/api/marketplace/skills/web-search/update")
            assert resp.status_code == 200


class TestE2EUpdateAll:
    def test_update_all_endpoint(self, sample_registry):
        updater = _make_updater(sample_registry)
        sample_registry.fetch_index = AsyncMock()
        sample_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "web-search", "installed_version": "1.0.0", "available_version": "1.1.0"},
                {"skill_id": "code-gen", "installed_version": "1.0.0", "available_version": "1.0.1"},
            ]
        )
        sample_registry.update_skill = AsyncMock(return_value={"install_path": "/tmp/updated"})

        with _make_client(sample_registry, updater) as client:
            resp = client.post("/api/marketplace/update-all")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["results"]) == 2
            assert all(r["success"] for r in data["results"])


class TestE2EUpdateStatus:
    def test_update_status_endpoint(self, sample_registry):
        updater = _make_updater(sample_registry)
        updater._last_check = datetime(2025, 1, 1, 12, 0, 0)
        updater._available_updates = [
            {"skill_id": "web-search", "installed_version": "1.0.0", "available_version": "1.1.0"},
        ]

        with _make_client(sample_registry, updater) as client:
            resp = client.get("/api/marketplace/update-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["last_check"] is not None
            assert data["available_updates"] == 1
            assert len(data["updates"]) == 1

    def test_update_status_no_updates(self, sample_registry):
        updater = _make_updater(sample_registry)

        with _make_client(sample_registry, updater) as client:
            resp = client.get("/api/marketplace/update-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["last_check"] is None
            assert data["available_updates"] == 0
            assert data["updates"] == []


class TestE2EUpdateNotification:
    @pytest.mark.anyio
    async def test_check_and_notify_sends_notification(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
                {"skill_id": "skill-b", "installed_version": "2.0.0", "available_version": "2.0.1"},
            ]
        )
        config = MarketplaceConfig(cache_ttl=3600, auto_update_check=True)
        updater = SkillUpdater(mock_registry, config)

        mock_bus = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.name = "test-channel"
        mock_cs = MagicMock()
        mock_cs.list_channels.return_value = [mock_channel]
        mock_cs.bus = mock_bus

        from app.channels.message_bus import OutboundMessage

        mock_message_bus_mod = MagicMock()
        mock_message_bus_mod.OutboundMessage = OutboundMessage
        mock_service_mod = MagicMock()
        mock_service_mod.get_channel_service.return_value = mock_cs

        fake_modules = {
            "app.channels.message_bus": mock_message_bus_mod,
            "app.channels.service": mock_service_mod,
        }
        original_modules = {}
        for mod_name, mod in fake_modules.items():
            original_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = mod

        try:
            updates = await updater.check_and_notify()
            assert len(updates) == 2
            mock_bus.publish_outbound.assert_called_once()
            call_args = mock_bus.publish_outbound.call_args
            msg = call_args[0][0]
            assert "2 个技能可更新" in msg.text
            assert "skill-a (1.0.0→1.1.0)" in msg.text
            assert "skill-b (2.0.0→2.0.1)" in msg.text
        finally:
            for mod_name, orig in original_modules.items():
                if orig is None:
                    sys.modules.pop(mod_name, None)
                else:
                    sys.modules[mod_name] = orig

    @pytest.mark.anyio
    async def test_check_and_notify_disabled(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
            ]
        )
        config = MarketplaceConfig(cache_ttl=3600, auto_update_check=False)
        updater = SkillUpdater(mock_registry, config)

        with patch.object(updater, "_send_update_notification", new_callable=AsyncMock) as mock_notify:
            updates = await updater.check_and_notify()
            assert len(updates) == 1
            mock_notify.assert_not_called()

    @pytest.mark.anyio
    async def test_check_and_notify_no_updates(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(return_value=[])
        config = MarketplaceConfig(cache_ttl=3600, auto_update_check=True)
        updater = SkillUpdater(mock_registry, config)

        with patch.object(updater, "_send_update_notification", new_callable=AsyncMock) as mock_notify:
            updates = await updater.check_and_notify()
            assert updates == []
            mock_notify.assert_not_called()
