from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.gateway.routers.marketplace import _get_registry, router
from deerflow.marketplace.models import (
    MarketplaceConfig,
    SkillCategory,
    SkillIndex,
    SkillManifest,
    SkillRegistryEntry,
)

from _router_auth_helpers import make_authed_test_app


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
    registry.get_skill = AsyncMock(
        side_effect=lambda sid: entries.get(sid)
    )
    registry.get_categories = AsyncMock(
        return_value=[
            {"category": "productivity", "count": len(manifests)},
        ]
    )
    registry.install_skill = AsyncMock(
        return_value={"skill_id": manifests[0].skill_id, "install_path": "/tmp/test"}
    )
    registry.uninstall_skill = AsyncMock()
    registry.check_updates = AsyncMock(return_value=[])
    registry.update_skill = AsyncMock(
        return_value={"skill_id": manifests[0].skill_id, "install_path": "/tmp/test"}
    )
    registry.fetch_index = AsyncMock()
    registry._index = None
    registry._index_fetched_at = None
    return registry


@contextmanager
def _make_client(registry: MagicMock):
    app = make_authed_test_app()
    app.include_router(router)
    client = TestClient(app)
    with patch("app.gateway.routers.marketplace._get_registry", return_value=registry):
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


class TestListMarketplaceSkills:
    def test_list_skills(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "skills" in data
        assert len(data["skills"]) == 2
        assert data["total"] == 2
        assert data["page"] == 1

    def test_list_skills_with_category_filter(self, sample_registry):
        sample_registry.list_skills = AsyncMock(
            return_value=[
                e for e in sample_registry._entries.values()
                if e.manifest.category == SkillCategory.development
            ]
        )
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills?category=development")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["skills"]) == 1
        assert data["skills"][0]["skill_id"] == "code-gen"

    def test_list_skills_with_search(self, sample_registry):
        sample_registry.search = AsyncMock(
            return_value=[sample_registry._entries["web-search"]]
        )
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills?query=search")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["skills"]) == 1

    def test_list_skills_invalid_category(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills?category=invalid")
        assert resp.status_code == 400

    def test_list_skills_pagination(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills?page=1&page_size=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["skills"]) == 1
        assert data["total"] == 2
        assert data["page_size"] == 1


class TestGetMarketplaceSkill:
    def test_get_skill_detail(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills/web-search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill_id"] == "web-search"
        assert data["name"] == "Web Search"
        assert data["repository"] == "https://github.com/example/web-search"
        assert data["dependencies"] == ["httpx"]
        assert data["permissions"] == ["network"]
        assert data["changelog"] == "Initial release"

    def test_get_skill_not_found(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/skills/nonexistent")
        assert resp.status_code == 404


class TestListCategories:
    def test_list_categories(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        assert len(data["categories"]) >= 1


class TestInstallSkill:
    def test_install_skill(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/skills/web-search/install")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_id"] == "web-search"

    def test_install_skill_not_found(self, sample_registry):
        sample_registry.install_skill = AsyncMock(
            side_effect=ValueError("Skill 'nonexistent' not found in registry")
        )
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/skills/nonexistent/install")
        assert resp.status_code == 404


class TestUninstallSkill:
    def test_uninstall_skill(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/skills/web-search/uninstall")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_id"] == "web-search"

    def test_uninstall_skill_not_found(self, sample_registry):
        sample_registry.uninstall_skill = AsyncMock(
            side_effect=FileNotFoundError("Skill not found")
        )
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/skills/nonexistent/uninstall")
        assert resp.status_code == 404


class TestCheckUpdates:
    def test_check_updates(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/updates")
        assert resp.status_code == 200
        data = resp.json()
        assert "updates" in data

    def test_check_updates_with_available(self, sample_registry):
        sample_registry.check_updates = AsyncMock(
            return_value=[
                {
                    "skill_id": "web-search",
                    "installed_version": "1.0.0",
                    "available_version": "2.0.0",
                }
            ]
        )
        with _make_client(sample_registry) as client:
            resp = client.get("/api/marketplace/updates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["updates"]) == 1


class TestUpdateSkill:
    def test_update_skill(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/skills/web-search/update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_id"] == "web-search"

    def test_update_skill_not_installed(self, sample_registry):
        sample_registry.update_skill = AsyncMock(
            side_effect=ValueError("Skill 'web-search' is not installed")
        )
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/skills/web-search/update")
        assert resp.status_code == 400


class TestRefreshIndex:
    def test_refresh_index(self, sample_registry):
        with _make_client(sample_registry) as client:
            resp = client.post("/api/marketplace/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Index refreshed"
