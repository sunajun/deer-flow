import asyncio
import logging
from datetime import datetime

from deerflow.config.agent_config_version import (
    AgentConfigVersion,
    AgentConfigVersionSnapshot,
)

logger = logging.getLogger(__name__)

MAX_VERSION_HISTORY = 100


class AgentConfigManager:
    def __init__(self) -> None:
        self._configs: dict[str, AgentConfigVersion] = {}
        self._versions: dict[str, list[AgentConfigVersionSnapshot]] = {}
        self._lock = asyncio.Lock()

    async def create(self, config: AgentConfigVersion) -> AgentConfigVersion:
        async with self._lock:
            if config.name in self._configs:
                raise ValueError(f"Agent config '{config.name}' already exists")
            self._configs[config.name] = config
            logger.info("Created agent config '%s' version %s", config.name, config.version)
            return config

    async def get(self, agent_name: str) -> AgentConfigVersion | None:
        return self._configs.get(agent_name)

    async def update(self, agent_name: str, updates: dict, *, change_summary: str = "") -> AgentConfigVersion:
        async with self._lock:
            current = self._configs.get(agent_name)
            if current is None:
                raise KeyError(f"Agent config '{agent_name}' not found")

            if agent_name not in self._versions:
                self._versions[agent_name] = []
            self._versions[agent_name].append(
                AgentConfigVersionSnapshot(
                    agent_name=agent_name,
                    version=current.version,
                    snapshot=current.model_copy(),
                    change_summary=change_summary,
                )
            )

            if len(self._versions[agent_name]) > MAX_VERSION_HISTORY:
                self._versions[agent_name] = self._versions[agent_name][-MAX_VERSION_HISTORY:]

            updated = current.model_copy(update={**updates, "updated_at": datetime.now()})
            parts = updated.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            updated.version = ".".join(parts)

            self._configs[agent_name] = updated
            logger.info("Updated agent config '%s' to version %s", agent_name, updated.version)
            return updated

    async def delete(self, agent_name: str) -> None:
        async with self._lock:
            if agent_name not in self._configs:
                raise KeyError(f"Agent config '{agent_name}' not found")
            del self._configs[agent_name]
            self._versions.pop(agent_name, None)
            logger.info("Deleted agent config '%s'", agent_name)

    async def list_agents(self) -> list[AgentConfigVersion]:
        return list(self._configs.values())

    async def get_version_history(self, agent_name: str) -> list[AgentConfigVersionSnapshot]:
        return list(self._versions.get(agent_name, []))

    async def rollback(self, agent_name: str, version: str) -> AgentConfigVersion:
        async with self._lock:
            current = self._configs.get(agent_name)
            if current is None:
                raise KeyError(f"Agent config '{agent_name}' not found")

            history = self._versions.get(agent_name, [])
            target_snapshot = None
            for snap in history:
                if snap.version == version:
                    target_snapshot = snap
                    break

            if target_snapshot is None:
                raise ValueError(f"Version '{version}' not found for agent '{agent_name}'")

            self._versions[agent_name].append(
                AgentConfigVersionSnapshot(
                    agent_name=agent_name,
                    version=current.version,
                    snapshot=current.model_copy(),
                    change_summary=f"Rollback to version {version}",
                )
            )

            if len(self._versions[agent_name]) > MAX_VERSION_HISTORY:
                self._versions[agent_name] = self._versions[agent_name][-MAX_VERSION_HISTORY:]

            rolled_back = target_snapshot.snapshot.model_copy(update={"updated_at": datetime.now()})
            parts = current.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            rolled_back.version = ".".join(parts)

            self._configs[agent_name] = rolled_back
            logger.info("Rolled back agent config '%s' to version %s (new version %s)", agent_name, version, rolled_back.version)
            return rolled_back


_manager: AgentConfigManager | None = None


def get_agent_config_manager() -> AgentConfigManager:
    global _manager
    if _manager is None:
        _manager = AgentConfigManager()
    return _manager


def reset_agent_config_manager() -> None:
    global _manager
    _manager = None
