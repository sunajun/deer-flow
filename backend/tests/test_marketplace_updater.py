from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from deerflow.config.app_config import AppConfig
from deerflow.marketplace.models import MarketplaceConfig
from deerflow.marketplace.updater import (
    SkillUpdater,
    compare_versions,
    is_security_update,
    is_update_available,
)


class TestCompareVersions:
    def test_older_version(self):
        assert compare_versions("1.0.0", "1.0.1") == -1

    def test_newer_version(self):
        assert compare_versions("1.1.0", "1.0.1") == 1

    def test_same_version(self):
        assert compare_versions("1.0.0", "1.0.0") == 0

    def test_major_difference(self):
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_minor_difference(self):
        assert compare_versions("1.0.0", "1.1.0") == -1

    def test_patch_difference(self):
        assert compare_versions("1.0.0", "1.0.1") == -1

    def test_two_part_version(self):
        assert compare_versions("1.0", "1.1") == -1

    def test_single_part_version(self):
        assert compare_versions("1", "2") == -1


class TestIsUpdateAvailable:
    def test_update_available(self):
        assert is_update_available("1.0.0", "1.0.1") is True

    def test_no_update_same_version(self):
        assert is_update_available("1.0.0", "1.0.0") is False

    def test_no_update_older_available(self):
        assert is_update_available("1.1.0", "1.0.1") is False

    def test_major_update(self):
        assert is_update_available("1.0.0", "2.0.0") is True

    def test_invalid_version(self):
        assert is_update_available("abc", "1.0.0") is False

    def test_none_version(self):
        assert is_update_available(None, "1.0.0") is False


class TestIsSecurityUpdate:
    def test_security_update_patch_bump(self):
        assert is_security_update("1.0.0", "1.0.1") is True

    def test_not_security_update_minor_bump(self):
        assert is_security_update("1.0.0", "1.1.0") is False

    def test_not_security_update_major_bump(self):
        assert is_security_update("1.0.0", "2.0.0") is False

    def test_not_security_update_same_version(self):
        assert is_security_update("1.0.0", "1.0.0") is False

    def test_not_security_update_downgrade(self):
        assert is_security_update("1.0.1", "1.0.0") is False

    def test_two_part_version(self):
        assert is_security_update("1.0", "1.0.1") is False

    def test_invalid_version(self):
        assert is_security_update("abc", "1.0.1") is False

    def test_none_version(self):
        assert is_security_update(None, "1.0.1") is False


class TestSkillUpdaterCheckUpdates:
    @pytest.mark.anyio
    async def test_check_updates_returns_updates(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
            ]
        )
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        updates = await updater.check_updates()
        assert len(updates) == 1
        assert updates[0]["skill_id"] == "skill-a"
        mock_registry.fetch_index.assert_called_once()
        mock_registry.check_updates.assert_called_once()

    @pytest.mark.anyio
    async def test_check_updates_caches_result(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
            ]
        )
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        await updater.check_updates()
        await updater.check_updates()
        mock_registry.fetch_index.assert_called_once()
        mock_registry.check_updates.assert_called_once()

    @pytest.mark.anyio
    async def test_check_updates_force_bypasses_cache(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
            ]
        )
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        await updater.check_updates()
        await updater.check_updates(force=True)
        assert mock_registry.fetch_index.call_count == 2
        assert mock_registry.check_updates.call_count == 2

    @pytest.mark.anyio
    async def test_check_updates_cache_expired(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
            ]
        )
        config = MarketplaceConfig(cache_ttl=0)
        updater = SkillUpdater(mock_registry, config)

        await updater.check_updates()
        assert updater._last_check is not None
        updater._last_check = datetime.now() - timedelta(seconds=9999)

        await updater.check_updates()
        assert mock_registry.fetch_index.call_count == 2
        assert mock_registry.check_updates.call_count == 2

    @pytest.mark.anyio
    async def test_check_updates_empty(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(return_value=[])
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        updates = await updater.check_updates()
        assert updates == []


class TestSkillUpdaterUpdateSkill:
    @pytest.mark.anyio
    async def test_update_skill(self):
        mock_registry = AsyncMock()
        mock_registry.update_skill = AsyncMock(return_value={"skill_id": "skill-a", "install_path": "/tmp/a"})
        config = MarketplaceConfig()
        updater = SkillUpdater(mock_registry, config)

        result = await updater.update_skill("skill-a")
        assert result["skill_id"] == "skill-a"
        mock_registry.update_skill.assert_called_once_with("skill-a")


class TestSkillUpdaterUpdateAll:
    @pytest.mark.anyio
    async def test_update_all_success(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(
            return_value=[
                {"skill_id": "skill-a", "installed_version": "1.0.0", "available_version": "1.1.0"},
                {"skill_id": "skill-b", "installed_version": "2.0.0", "available_version": "2.0.1"},
            ]
        )
        mock_registry.update_skill = AsyncMock(return_value={"install_path": "/tmp/updated"})
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        results = await updater.update_all()
        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert updater._available_updates == []

    @pytest.mark.anyio
    async def test_update_all_partial_failure(self):
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
            ValueError("update failed"),
        ]
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        results = await updater.update_all()
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert "update failed" in results[1]["error"]

    @pytest.mark.anyio
    async def test_update_all_no_updates(self):
        mock_registry = AsyncMock()
        mock_registry.fetch_index = AsyncMock()
        mock_registry.check_updates = AsyncMock(return_value=[])
        config = MarketplaceConfig(cache_ttl=3600)
        updater = SkillUpdater(mock_registry, config)

        results = await updater.update_all()
        assert results == []


class TestSkillUpdaterCacheFreshness:
    def test_is_check_fresh_no_last_check(self):
        config = MarketplaceConfig(cache_ttl=3600)
        mock_registry = MagicMock()
        updater = SkillUpdater(mock_registry, config)
        assert updater._is_check_fresh() is False

    def test_is_check_fresh_within_ttl(self):
        config = MarketplaceConfig(cache_ttl=3600)
        mock_registry = MagicMock()
        updater = SkillUpdater(mock_registry, config)
        updater._last_check = datetime.now()
        assert updater._is_check_fresh() is True

    def test_is_check_fresh_expired(self):
        config = MarketplaceConfig(cache_ttl=3600)
        mock_registry = MagicMock()
        updater = SkillUpdater(mock_registry, config)
        updater._last_check = datetime.now() - timedelta(seconds=9999)
        assert updater._is_check_fresh() is False


class TestAppConfigMarketplaceField:
    def test_default_marketplace_config(self):
        config = AppConfig(
            sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            models=[],
        )
        assert config.marketplace.enabled is True
        assert config.marketplace.cache_ttl == 3600
        assert config.marketplace.auto_update_check is True
        assert config.marketplace.index_url == ""
        assert config.marketplace.trusted_sources == []

    def test_marketplace_config_from_dict(self):
        config = AppConfig(
            sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            models=[],
            marketplace={
                "enabled": False,
                "index_url": "https://example.com/index.json",
                "cache_ttl": 7200,
                "auto_update_check": False,
                "trusted_sources": ["github.com/example"],
            },
        )
        assert config.marketplace.enabled is False
        assert config.marketplace.index_url == "https://example.com/index.json"
        assert config.marketplace.cache_ttl == 7200
        assert config.marketplace.auto_update_check is False
        assert config.marketplace.trusted_sources == ["github.com/example"]

    def test_marketplace_config_partial_override(self):
        config = AppConfig(
            sandbox={"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            models=[],
            marketplace={
                "index_url": "https://example.com/index.json",
            },
        )
        assert config.marketplace.enabled is True
        assert config.marketplace.index_url == "https://example.com/index.json"
        assert config.marketplace.cache_ttl == 3600
