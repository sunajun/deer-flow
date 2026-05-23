from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deerflow.config.app_config import AppConfig
from deerflow.marketplace.models import (
    MarketplaceConfig,
    SkillIndex,
)
from deerflow.marketplace.registry import SkillRegistry
from deerflow.marketplace.updater import (
    SkillUpdater,
    is_security_update,
    is_update_available,
)


def _sample_manifest(**overrides) -> dict:
    base = {
        "skill_id": "web-search",
        "name": "Web Search",
        "description": "Search the web",
        "version": "1.0.0",
        "category": "productivity",
        "tags": ["search", "web"],
        "author": "deerflow",
        "repository": "https://github.com/example/web-search",
        "archive_url": "https://example.com/web-search.skill",
        "checksum": "",
    }
    base.update(overrides)
    return base


def _sample_index(skills=None, **overrides) -> dict:
    base = {
        "version": "1.0",
        "updated_at": "2025-01-01T00:00:00Z",
        "skills": skills or [_sample_manifest()],
    }
    base.update(overrides)
    return base


class TestFullFlowInstallCheckUpdateUninstall:
    @pytest.mark.anyio
    async def test_full_lifecycle(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json", cache_ttl=3600)
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(
            **_sample_index(
                [
                    _sample_manifest(skill_id="skill-a", version="1.0.0", archive_url="https://example.com/a.skill"),
                ]
            )
        )
        registry._rebuild_entries()

        mock_installer = AsyncMock()
        mock_installer.is_installed = MagicMock(return_value=False)
        mock_installer.install = AsyncMock(return_value={"skill_id": "skill-a", "install_path": "/tmp/a"})
        mock_installer.uninstall = AsyncMock()
        registry._installer = mock_installer

        mock_resp = MagicMock()
        mock_resp.content = b"fake-archive"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            result = await registry.install_skill("skill-a")
        assert result["skill_id"] == "skill-a"
        assert registry._entries["skill-a"].installed is True
        assert registry._entries["skill-a"].installed_version == "1.0.0"

        registry._index = SkillIndex(
            **_sample_index(
                [
                    _sample_manifest(skill_id="skill-a", version="1.1.0", archive_url="https://example.com/a.skill"),
                ]
            )
        )
        registry._rebuild_entries()
        registry._entries["skill-a"].installed = True
        registry._entries["skill-a"].installed_version = "1.0.0"

        updates = await registry.check_updates()
        assert len(updates) == 1
        assert updates[0]["available_version"] == "1.1.0"

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            result = await registry.update_skill("skill-a")
        assert result["skill_id"] == "skill-a"

        await registry.uninstall_skill("skill-a")
        assert registry._entries["skill-a"].installed is False


class TestUpdateFlowVersionUpgrade:
    @pytest.mark.anyio
    async def test_update_from_v1_to_v1_1(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json", cache_ttl=3600)
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(
            **_sample_index(
                [
                    _sample_manifest(skill_id="skill-a", version="1.1.0", archive_url="https://example.com/a.skill"),
                ]
            )
        )
        registry._rebuild_entries()
        registry._entries["skill-a"].installed = True
        registry._entries["skill-a"].installed_version = "1.0.0"

        updates = await registry.check_updates()
        assert len(updates) == 1
        assert updates[0]["installed_version"] == "1.0.0"
        assert updates[0]["available_version"] == "1.1.0"
        assert is_update_available("1.0.0", "1.1.0") is True
        assert is_security_update("1.0.0", "1.1.0") is False


class TestSecurityUpdateDetection:
    @pytest.mark.anyio
    async def test_detect_security_update(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json", cache_ttl=3600)
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(
            **_sample_index(
                [
                    _sample_manifest(skill_id="skill-a", version="1.0.1", archive_url="https://example.com/a.skill"),
                ]
            )
        )
        registry._rebuild_entries()
        registry._entries["skill-a"].installed = True
        registry._entries["skill-a"].installed_version = "1.0.0"

        updates = await registry.check_updates()
        assert len(updates) == 1
        assert is_security_update("1.0.0", "1.0.1") is True
        assert is_update_available("1.0.0", "1.0.1") is True


class TestUpdateAllMultipleSkills:
    @pytest.mark.anyio
    async def test_update_all_three_skills(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
                {"skill_id": "skill-b", "installed_version": "2.0.0", "available_version": "2.0.1"},
                {"skill_id": "skill-c", "installed_version": "3.0.0", "available_version": "3.1.0"},
            ]
        )
        mock_registry.update_skill = AsyncMock(return_value={"install_path": "/tmp/updated"})
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        results = await updater.update_all()
        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert mock_registry.update_skill.call_count == 3


class TestUpdateAllPartialFailure:
    @pytest.mark.anyio
    async def test_update_all_with_one_failure(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
                {"skill_id": "skill-b", "installed_version": "2.0.0", "available_version": "2.0.1"},
            ]
        )
        mock_registry.update_skill = AsyncMock()
        mock_registry.update_skill.side_effect = [
            {"install_path": "/tmp/a"},
            ValueError("download failed"),
        ]
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        results = await updater.update_all()
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert "download failed" in results[1]["error"]


class TestAppConfigMarketplaceParsing:
    def test_marketplace_from_yaml_dict(self):
        config = AppConfig(
            sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            models=[],
            marketplace={
                "enabled": True,
                "index_url": "https://example.com/skills-index.json",
                "cache_ttl": 7200,
                "auto_update_check": False,
                "trusted_sources": ["github.com/example", "github.com/trusted"],
            },
        )
        assert config.marketplace.enabled is True
        assert config.marketplace.index_url == "https://example.com/skills-index.json"
        assert config.marketplace.cache_ttl == 7200
        assert config.marketplace.auto_update_check is False
        assert config.marketplace.trusted_sources == ["github.com/example", "github.com/trusted"]

    def test_marketplace_defaults_when_absent(self):
        config = AppConfig(
            sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            models=[],
        )
        assert config.marketplace.enabled is True
        assert config.marketplace.cache_ttl == 3600
        assert config.marketplace.auto_update_check is True
        assert config.marketplace.index_url == ""
        assert config.marketplace.trusted_sources == []
