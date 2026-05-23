from __future__ import annotations

import hashlib
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import httpx

from deerflow.marketplace.models import (
    MarketplaceConfig,
    SkillCategory,
    SkillIndex,
    SkillRegistryEntry,
)
from deerflow.skills.installer import SkillInstaller

logger = logging.getLogger(__name__)

_SUPPORTED_INDEX_VERSIONS = {"1.0"}


class IndexVersionError(ValueError):
    pass


class IndexFetchError(RuntimeError):
    pass


class SkillRegistry:
    def __init__(self, config: MarketplaceConfig):
        self._config = config
        self._index: SkillIndex | None = None
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._index_fetched_at: datetime | None = None
        self._installer: SkillInstaller | None = None

    async def fetch_index(self) -> SkillIndex:
        if self._index is not None and self._is_cache_valid():
            return self._index

        if not self._config.index_url:
            raise IndexFetchError("index_url is not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._config.index_url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise IndexFetchError(f"Failed to fetch skill index: {exc}") from exc
        except ValueError as exc:
            raise IndexFetchError(f"Invalid JSON in skill index: {exc}") from exc

        index = SkillIndex.model_validate(data)

        if index.version not in _SUPPORTED_INDEX_VERSIONS:
            raise IndexVersionError(
                f"Unsupported index version {index.version!r}; "
                f"supported: {_SUPPORTED_INDEX_VERSIONS}"
            )

        self._index = index
        self._index_fetched_at = datetime.now()
        self._rebuild_entries()
        return self._index

    async def search(
        self,
        query: str,
        category: SkillCategory | None = None,
    ) -> list[SkillRegistryEntry]:
        if self._index is None:
            await self.fetch_index()

        query_lower = query.lower()
        results: list[SkillRegistryEntry] = []
        for entry in self._entries.values():
            if category is not None and entry.manifest.category != category:
                continue
            m = entry.manifest
            searchable = " ".join(
                [m.name, m.description, m.author, " ".join(m.tags)]
            ).lower()
            if query_lower in searchable:
                results.append(entry)
        return results

    async def get_skill(self, skill_id: str) -> SkillRegistryEntry | None:
        if self._index is None:
            await self.fetch_index()
        return self._entries.get(skill_id)

    async def list_skills(
        self,
        category: SkillCategory | None = None,
    ) -> list[SkillRegistryEntry]:
        if self._index is None:
            await self.fetch_index()

        if category is None:
            return list(self._entries.values())
        return [
            e for e in self._entries.values() if e.manifest.category == category
        ]

    async def get_categories(self) -> list[dict]:
        if self._index is None:
            await self.fetch_index()

        seen: dict[str, int] = {}
        for entry in self._entries.values():
            cat = entry.manifest.category
            seen[cat.value] = seen.get(cat.value, 0) + 1
        return [
            {"category": cat, "count": count} for cat, count in sorted(seen.items())
        ]

    async def install_skill(
        self, skill_id: str, version: str | None = None
    ) -> dict:
        entry = self._entries.get(skill_id)
        if entry is None:
            raise ValueError(f"Skill '{skill_id}' not found in registry")

        manifest = entry.manifest
        if version is not None and manifest.version != version:
            raise ValueError(
                f"Requested version {version!r} not available; "
                f"registry has {manifest.version!r}"
            )

        archive_path = await self._download_archive(
            manifest.archive_url, manifest.checksum
        )
        installer = self._get_installer()
        result = await installer.install(skill_id, archive_path=archive_path)
        entry.installed = True
        entry.installed_version = manifest.version
        return result

    async def uninstall_skill(self, skill_id: str) -> None:
        installer = self._get_installer()
        await installer.uninstall(skill_id)
        if skill_id in self._entries:
            self._entries[skill_id].installed = False
            self._entries[skill_id].installed_version = None

    async def check_updates(self) -> list[dict]:
        if self._index is None:
            await self.fetch_index()

        updates: list[dict] = []
        for entry in self._entries.values():
            if not entry.installed or entry.installed_version is None:
                continue
            if entry.manifest.version != entry.installed_version:
                updates.append(
                    {
                        "skill_id": entry.manifest.skill_id,
                        "installed_version": entry.installed_version,
                        "available_version": entry.manifest.version,
                    }
                )
        return updates

    async def update_skill(self, skill_id: str) -> dict:
        entry = self._entries.get(skill_id)
        if entry is None:
            raise ValueError(f"Skill '{skill_id}' not found in registry")
        if not entry.installed:
            raise ValueError(f"Skill '{skill_id}' is not installed")

        await self.uninstall_skill(skill_id)
        return await self.install_skill(skill_id)

    def _get_installer(self) -> SkillInstaller:
        if self._installer is None:
            self._installer = SkillInstaller()
        return self._installer

    def _is_cache_valid(self) -> bool:
        if self._index_fetched_at is None:
            return False
        elapsed = (datetime.now() - self._index_fetched_at).total_seconds()
        return elapsed < self._config.cache_ttl

    def _rebuild_entries(self) -> None:
        if self._index is None:
            return
        installer = self._installer
        new_entries: dict[str, SkillRegistryEntry] = {}
        for manifest in self._index.skills:
            is_installed = installer.is_installed(manifest.skill_id) if installer else False
            new_entries[manifest.skill_id] = SkillRegistryEntry(
                manifest=manifest,
                installed=is_installed,
                installed_version=manifest.version if is_installed else None,
            )
        self._entries = new_entries

    async def _download_archive(
        self, archive_url: str, checksum: str
    ) -> Path:
        if not archive_url:
            raise ValueError("archive_url is empty; cannot download skill archive")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(archive_url)
                resp.raise_for_status()
                content = resp.content
        except httpx.HTTPError as exc:
            raise IndexFetchError(
                f"Failed to download skill archive from {archive_url}: {exc}"
            ) from exc

        if checksum:
            actual = hashlib.sha256(content).hexdigest()
            if actual != checksum:
                raise ValueError(
                    f"Checksum mismatch for archive: expected {checksum}, got {actual}"
                )

        tmp_dir = tempfile.mkdtemp(prefix="deerflow-marketplace-")
        archive_path = Path(tmp_dir) / "skill.skill"
        archive_path.write_bytes(content)
        return archive_path
