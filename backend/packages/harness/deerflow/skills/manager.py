"""Skill lifecycle management: install, uninstall, enable/disable, update."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from deerflow.config.extensions_config import (
    ExtensionsConfig,
    SkillStateConfig,
    get_extensions_config,
    reload_extensions_config,
)
from deerflow.skills.installer import (
    SkillAlreadyExistsError,
    SkillInstaller,
    SkillSecurityScanError,
)
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.skills.types import SkillCategory

logger = logging.getLogger(__name__)


class SkillManager:
    """Manages the full lifecycle of skills.

    Delegates low-level install/uninstall to :class:`SkillInstaller` and
    persists enabled state in ``extensions_config.json``.
    """

    def __init__(self, skills_dir: Path | None = None):
        self._installer = SkillInstaller(skills_dir=skills_dir)
        self._installed: dict[str, dict] = {}

    async def install_skill(
        self,
        skill_id: str,
        archive_path: Path | None = None,
        version: str | None = None,
    ) -> dict:
        """Install a skill via *SkillInstaller* and register it."""
        result = await self._installer.install(skill_id, archive_path=archive_path)
        self._installed[skill_id] = {
            "version": version or "latest",
            "enabled": True,
            "installed_at": datetime.now(UTC).isoformat(),
        }
        await self._update_config(skill_id, enable=True)
        return result

    async def uninstall_skill(self, skill_id: str) -> None:
        """Uninstall a skill and remove it from config."""
        await self._installer.uninstall(skill_id)
        self._installed.pop(skill_id, None)
        await self._update_config(skill_id, enable=None)

    async def enable_skill(self, skill_id: str, agent_id: str | None = None) -> None:
        """Enable a skill globally or for a specific agent."""
        if skill_id in self._installed:
            self._installed[skill_id]["enabled"] = True
        await self._update_config(skill_id, enable=True, agent_id=agent_id)

    async def disable_skill(self, skill_id: str, agent_id: str | None = None) -> None:
        """Disable a skill globally or for a specific agent."""
        if skill_id in self._installed:
            self._installed[skill_id]["enabled"] = False
        await self._update_config(skill_id, enable=False, agent_id=agent_id)

    async def list_skills(self) -> list[dict]:
        """Return all skills with their lifecycle metadata."""
        storage = get_or_new_skill_storage()
        skills = storage.load_skills(enabled_only=False)
        result = []
        for skill in skills:
            meta = self._installed.get(skill.name, {})
            result.append({
                "name": skill.name,
                "description": skill.description,
                "category": skill.category,
                "enabled": skill.enabled,
                "version": meta.get("version"),
                "installed_at": meta.get("installed_at"),
            })
        return result

    async def get_skill_detail(self, skill_id: str) -> dict | None:
        """Return detailed info for a single skill, or *None* if not found."""
        storage = get_or_new_skill_storage()
        skills = storage.load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_id), None)
        if skill is None:
            return None
        meta = self._installed.get(skill_id, {})
        return {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "enabled": skill.enabled,
            "version": meta.get("version"),
            "installed_at": meta.get("installed_at"),
            "skill_dir": str(skill.skill_dir),
        }

    async def check_updates(self, skill_id: str | None = None) -> list[dict]:
        """Check for available updates.

        Currently returns an empty list — a remote marketplace is not yet
        connected.  The method is a placeholder so the API surface is ready.
        """
        return []

    async def update_skill(
        self,
        skill_id: str,
        archive_path: Path | None = None,
        version: str | None = None,
    ) -> dict:
        """Update a skill by reinstalling from a new archive.

        Performs an uninstall-then-reinstall cycle so the security scan
        and validation run against the new version.
        """
        await self._installer.uninstall(skill_id)
        result = await self._installer.install(skill_id, archive_path=archive_path)
        self._installed[skill_id] = {
            "version": version or "latest",
            "enabled": True,
            "installed_at": datetime.now(UTC).isoformat(),
        }
        await self._update_config(skill_id, enable=True)
        return result

    async def _update_config(
        self,
        skill_id: str,
        *,
        enable: bool | None,
        agent_id: str | None = None,
    ) -> None:
        """Persist enabled state to ``extensions_config.json``.

        When *enable* is ``None`` the skill entry is removed (used by
        uninstall).  When *agent_id* is given the change is scoped to
        that agent; otherwise it is global.
        """
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            config_path = self._skills_dir / "extensions_config.json"
            logger.info("No existing extensions config found. Creating new config at: %s", config_path)

        extensions_config = get_extensions_config()

        if enable is None:
            extensions_config.skills.pop(skill_id, None)
        else:
            extensions_config.skills[skill_id] = SkillStateConfig(enabled=enable)

        config_data = {
            "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
            "skills": {name: {"enabled": skill_config.enabled} for name, skill_config in extensions_config.skills.items()},
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        reload_extensions_config()

    @property
    def _skills_dir(self) -> Path:
        return self._installer.skills_dir
