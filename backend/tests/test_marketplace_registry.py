from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from deerflow.marketplace.models import (
    MarketplaceConfig,
    SkillCategory,
    SkillIndex,
    SkillManifest,
    SkillRegistryEntry,
)
from deerflow.marketplace.registry import (
    IndexFetchError,
    IndexVersionError,
    SkillRegistry,
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


class TestSkillManifest:
    def test_valid_manifest(self):
        m = SkillManifest(**_sample_manifest())
        assert m.skill_id == "web-search"
        assert m.category == SkillCategory.productivity
        assert m.tags == ["search", "web"]

    def test_missing_required_field(self):
        data = _sample_manifest()
        del data["skill_id"]
        with pytest.raises(Exception):
            SkillManifest(**data)

    def test_missing_name(self):
        data = _sample_manifest()
        del data["name"]
        with pytest.raises(Exception):
            SkillManifest(**data)

    def test_missing_description(self):
        data = _sample_manifest()
        del data["description"]
        with pytest.raises(Exception):
            SkillManifest(**data)

    def test_missing_version(self):
        data = _sample_manifest()
        del data["version"]
        with pytest.raises(Exception):
            SkillManifest(**data)

    def test_missing_category(self):
        data = _sample_manifest()
        del data["category"]
        with pytest.raises(Exception):
            SkillManifest(**data)

    def test_default_values(self):
        m = SkillManifest(
            skill_id="x",
            name="X",
            description="desc",
            version="0.1",
            category="other",
        )
        assert m.tags == []
        assert m.author == ""
        assert m.homepage == ""
        assert m.dependencies == []
        assert m.permissions == []
        assert m.created_at is None
        assert m.updated_at is None


class TestSkillIndex:
    def test_parse_valid_index(self):
        idx = SkillIndex(**_sample_index())
        assert idx.version == "1.0"
        assert len(idx.skills) == 1

    def test_parse_empty_skills(self):
        idx = SkillIndex(
            version="1.0", updated_at=datetime.now(), skills=[]
        )
        assert idx.skills == []

    def test_default_version(self):
        idx = SkillIndex(updated_at=datetime.now())
        assert idx.version == "1.0"


class TestSkillRegistryEntry:
    def test_defaults(self):
        m = SkillManifest(**_sample_manifest())
        entry = SkillRegistryEntry(manifest=m)
        assert entry.installed is False
        assert entry.installed_version is None
        assert entry.local_path is None


class TestMarketplaceConfig:
    def test_defaults(self):
        cfg = MarketplaceConfig()
        assert cfg.enabled is True
        assert cfg.index_url == ""
        assert cfg.cache_ttl == 3600
        assert cfg.auto_update_check is True
        assert cfg.trusted_sources == []

    def test_extra_fields_allowed(self):
        cfg = MarketplaceConfig(enabled=True, custom_field="hello")
        assert cfg.custom_field == "hello"


class TestSkillRegistryFetchIndex:
    def _make_registry(self, **config_overrides) -> SkillRegistry:
        cfg = MarketplaceConfig(
            index_url="https://example.com/skills-index.json",
            **config_overrides,
        )
        return SkillRegistry(cfg)

    @pytest.mark.anyio
    async def test_fetch_index_first_time(self):
        registry = self._make_registry()
        index_data = _sample_index()

        mock_resp = MagicMock()
        mock_resp.json.return_value = index_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            index = await registry.fetch_index()

        assert index.version == "1.0"
        assert len(index.skills) == 1
        assert registry._index_fetched_at is not None

    @pytest.mark.anyio
    async def test_fetch_index_cached(self):
        registry = self._make_registry(cache_ttl=3600)
        index_data = _sample_index()

        mock_resp = MagicMock()
        mock_resp.json.return_value = index_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            await registry.fetch_index()
            await registry.fetch_index()

        assert mock_client.get.call_count == 1

    @pytest.mark.anyio
    async def test_fetch_index_cache_expired(self):
        registry = self._make_registry(cache_ttl=0)
        index_data = _sample_index()

        mock_resp = MagicMock()
        mock_resp.json.return_value = index_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            await registry.fetch_index()

        registry._index_fetched_at = datetime.now() - timedelta(seconds=9999)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            await registry.fetch_index()

        assert mock_client.get.call_count == 2

    @pytest.mark.anyio
    async def test_fetch_index_no_url(self):
        registry = self._make_registry()
        registry._config.index_url = ""
        with pytest.raises(IndexFetchError, match="index_url is not configured"):
            await registry.fetch_index()

    @pytest.mark.anyio
    async def test_fetch_index_network_error(self):
        registry = self._make_registry()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(IndexFetchError, match="Failed to fetch"):
                await registry.fetch_index()

    @pytest.mark.anyio
    async def test_fetch_index_invalid_json(self):
        registry = self._make_registry()

        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("bad json")
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(IndexFetchError, match="Invalid JSON"):
                await registry.fetch_index()

    @pytest.mark.anyio
    async def test_fetch_index_unsupported_version(self):
        registry = self._make_registry()
        index_data = _sample_index(version="99.0")

        mock_resp = MagicMock()
        mock_resp.json.return_value = index_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(IndexVersionError, match="Unsupported index version"):
                await registry.fetch_index()


class TestSkillRegistrySearch:
    @pytest.mark.anyio
    async def test_search_by_keyword(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="web-search", name="Web Search", description="Search the web", tags=["search"]),
            _sample_manifest(skill_id="code-gen", name="Code Generator", description="Generate code", category="development", tags=["code"]),
        ]))
        registry._rebuild_entries()

        results = await registry.search("search")
        ids = [e.manifest.skill_id for e in results]
        assert "web-search" in ids
        assert "code-gen" not in ids

    @pytest.mark.anyio
    async def test_search_by_category(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="web-search", category="productivity"),
            _sample_manifest(skill_id="code-gen", name="Code Gen", description="gen", category="development"),
        ]))
        registry._rebuild_entries()

        results = await registry.search("gen", category=SkillCategory.development)
        ids = [e.manifest.skill_id for e in results]
        assert "code-gen" in ids
        assert "web-search" not in ids

    @pytest.mark.anyio
    async def test_search_no_results(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        results = await registry.search("nonexistent")
        assert results == []


class TestSkillRegistryGetAndList:
    @pytest.mark.anyio
    async def test_get_skill(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        entry = await registry.get_skill("web-search")
        assert entry is not None
        assert entry.manifest.skill_id == "web-search"

    @pytest.mark.anyio
    async def test_get_skill_not_found(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        entry = await registry.get_skill("nonexistent")
        assert entry is None

    @pytest.mark.anyio
    async def test_list_skills(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="a", category="productivity"),
            _sample_manifest(skill_id="b", name="B", description="b", category="development"),
        ]))
        registry._rebuild_entries()

        all_skills = await registry.list_skills()
        assert len(all_skills) == 2

    @pytest.mark.anyio
    async def test_list_skills_by_category(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="a", category="productivity"),
            _sample_manifest(skill_id="b", name="B", description="b", category="development"),
        ]))
        registry._rebuild_entries()

        dev_skills = await registry.list_skills(category=SkillCategory.development)
        assert len(dev_skills) == 1
        assert dev_skills[0].manifest.skill_id == "b"

    @pytest.mark.anyio
    async def test_get_categories(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="a", category="productivity"),
            _sample_manifest(skill_id="b", name="B", description="b", category="productivity"),
            _sample_manifest(skill_id="c", name="C", description="c", category="development"),
        ]))
        registry._rebuild_entries()

        cats = await registry.get_categories()
        cat_map = {c["category"]: c["count"] for c in cats}
        assert cat_map["productivity"] == 2
        assert cat_map["development"] == 1


class TestSkillRegistryInstall:
    @pytest.mark.anyio
    async def test_install_skill(self, tmp_path):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="demo-skill", archive_url="https://example.com/demo.skill"),
        ]))
        registry._rebuild_entries()

        mock_installer = AsyncMock()
        mock_installer.install = AsyncMock(return_value={"skill_id": "demo-skill", "install_path": "/tmp/demo"})
        mock_installer.is_installed = MagicMock(return_value=False)
        registry._installer = mock_installer

        mock_resp = MagicMock()
        mock_resp.content = b"fake-archive-content"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            result = await registry.install_skill("demo-skill")

        assert result["skill_id"] == "demo-skill"
        mock_installer.install.assert_called_once()
        entry = registry._entries["demo-skill"]
        assert entry.installed is True
        assert entry.installed_version == "1.0.0"

    @pytest.mark.anyio
    async def test_install_skill_not_found(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        with pytest.raises(ValueError, match="not found in registry"):
            await registry.install_skill("nonexistent")

    @pytest.mark.anyio
    async def test_install_skill_version_mismatch(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        with pytest.raises(ValueError, match="not available"):
            await registry.install_skill("web-search", version="2.0.0")

    @pytest.mark.anyio
    async def test_install_skill_empty_archive_url(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="no-url", archive_url=""),
        ]))
        registry._rebuild_entries()

        with pytest.raises(ValueError, match="archive_url is empty"):
            await registry.install_skill("no-url")


class TestSkillRegistryUninstall:
    @pytest.mark.anyio
    async def test_uninstall_skill(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        mock_installer = AsyncMock()
        mock_installer.uninstall = AsyncMock()
        registry._installer = mock_installer

        registry._entries["web-search"].installed = True
        registry._entries["web-search"].installed_version = "1.0.0"

        await registry.uninstall_skill("web-search")

        mock_installer.uninstall.assert_called_once_with("web-search")
        assert registry._entries["web-search"].installed is False
        assert registry._entries["web-search"].installed_version is None


class TestSkillRegistryCheckUpdates:
    @pytest.mark.anyio
    async def test_check_updates_available(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="web-search", version="2.0.0"),
        ]))
        registry._rebuild_entries()

        registry._entries["web-search"].installed = True
        registry._entries["web-search"].installed_version = "1.0.0"

        updates = await registry.check_updates()
        assert len(updates) == 1
        assert updates[0]["skill_id"] == "web-search"
        assert updates[0]["installed_version"] == "1.0.0"
        assert updates[0]["available_version"] == "2.0.0"

    @pytest.mark.anyio
    async def test_check_updates_none_available(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        registry._entries["web-search"].installed = True
        registry._entries["web-search"].installed_version = "1.0.0"

        updates = await registry.check_updates()
        assert updates == []

    @pytest.mark.anyio
    async def test_check_updates_not_installed(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        updates = await registry.check_updates()
        assert updates == []


class TestSkillRegistryUpdateSkill:
    @pytest.mark.anyio
    async def test_update_skill(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(skill_id="demo-skill", archive_url="https://example.com/demo.skill"),
        ]))
        registry._rebuild_entries()

        registry._entries["demo-skill"].installed = True
        registry._entries["demo-skill"].installed_version = "0.9.0"

        mock_installer = AsyncMock()
        mock_installer.install = AsyncMock(return_value={"skill_id": "demo-skill", "install_path": "/tmp/demo"})
        mock_installer.uninstall = AsyncMock()
        registry._installer = mock_installer

        mock_resp = MagicMock()
        mock_resp.content = b"fake-archive-content"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            result = await registry.update_skill("demo-skill")

        assert result["skill_id"] == "demo-skill"
        mock_installer.uninstall.assert_called_once_with("demo-skill")
        mock_installer.install.assert_called_once()

    @pytest.mark.anyio
    async def test_update_skill_not_installed(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        with pytest.raises(ValueError, match="not installed"):
            await registry.update_skill("web-search")

    @pytest.mark.anyio
    async def test_update_skill_not_found(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index())
        registry._rebuild_entries()

        with pytest.raises(ValueError, match="not found in registry"):
            await registry.update_skill("nonexistent")


class TestSkillRegistryChecksum:
    @pytest.mark.anyio
    async def test_download_archive_checksum_mismatch(self):
        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(
                skill_id="checked-skill",
                archive_url="https://example.com/checked.skill",
                checksum="0000000000000000000000000000000000000000000000000000000000000000",
            ),
        ]))
        registry._rebuild_entries()

        mock_resp = MagicMock()
        mock_resp.content = b"some-content"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="Checksum mismatch"):
                await registry.install_skill("checked-skill")

    @pytest.mark.anyio
    async def test_download_archive_checksum_match(self):
        import hashlib

        content = b"valid-archive-content"
        expected_checksum = hashlib.sha256(content).hexdigest()

        cfg = MarketplaceConfig(index_url="https://example.com/index.json")
        registry = SkillRegistry(cfg)
        registry._index = SkillIndex(**_sample_index([
            _sample_manifest(
                skill_id="checked-skill",
                archive_url="https://example.com/checked.skill",
                checksum=expected_checksum,
            ),
        ]))
        registry._rebuild_entries()

        mock_installer = AsyncMock()
        mock_installer.install = AsyncMock(return_value={"skill_id": "checked-skill", "install_path": "/tmp/checked"})
        mock_installer.is_installed = MagicMock(return_value=False)
        registry._installer = mock_installer

        mock_resp = MagicMock()
        mock_resp.content = content
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("deerflow.marketplace.registry.httpx.AsyncClient", return_value=mock_client):
            result = await registry.install_skill("checked-skill")

        assert result["skill_id"] == "checked-skill"
