from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from deerflow.marketplace.models import MarketplaceConfig
from deerflow.marketplace.registry import SkillRegistry

logger = logging.getLogger(__name__)


def compare_versions(current: str, available: str) -> int:
    """Compare two semantic versions. Returns -1/0/1."""

    def parse(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split("."))

    c, a = parse(current), parse(available)
    return (c > a) - (c < a)


def is_update_available(current_version: str, available_version: str) -> bool:
    """Check if an update is available (available > current)."""
    try:
        return compare_versions(current_version, available_version) < 0
    except (ValueError, TypeError, AttributeError):
        return False


def is_security_update(current_version: str, available_version: str) -> bool:
    """Check if the update is a security/patch update (same major.minor, higher patch)."""
    try:
        c = tuple(int(x) for x in current_version.split("."))
        a = tuple(int(x) for x in available_version.split("."))
        if len(c) < 3 or len(a) < 3:
            return False
        return c[0] == a[0] and c[1] == a[1] and a[2] > c[2]
    except (ValueError, TypeError, AttributeError):
        return False


class SkillUpdater:
    def __init__(self, registry: SkillRegistry, config: MarketplaceConfig):
        self._registry = registry
        self._config = config
        self._last_check: datetime | None = None
        self._available_updates: list[dict[str, Any]] = []

    async def check_updates(self, force: bool = False) -> list[dict[str, Any]]:
        """Check for available skill updates, reusing SkillRegistry.check_updates()."""
        if not force and self._available_updates and self._is_check_fresh():
            return self._available_updates
        await self._registry.fetch_index()
        self._available_updates = await self._registry.check_updates()
        self._last_check = datetime.now()
        return self._available_updates

    async def update_skill(self, skill_id: str) -> dict:
        """Update a single skill."""
        return await self._registry.update_skill(skill_id)

    async def update_all(self) -> list[dict[str, Any]]:
        """Update all skills that have available updates."""
        updates = await self.check_updates()
        results: list[dict[str, Any]] = []
        for update in updates:
            try:
                result = await self._registry.update_skill(update["skill_id"])
                results.append({"skill_id": update["skill_id"], "success": True, "result": result})
            except Exception as e:
                results.append({"skill_id": update["skill_id"], "success": False, "error": str(e)})
        self._available_updates = []
        return results

    async def check_and_notify(self) -> list[dict[str, Any]]:
        """Check for updates and send notification via MessageBus if auto_update_check is enabled."""
        updates = await self.check_updates()
        if not updates or not self._config.auto_update_check:
            return updates
        await self._send_update_notification(updates)
        return updates

    async def _send_update_notification(self, updates: list[dict[str, Any]]) -> None:
        """Send update notification through MessageBus."""
        try:
            import importlib

            message_bus_mod = importlib.import_module("app.channels.message_bus")
            service_mod = importlib.import_module("app.channels.service")
        except ImportError:
            logger.debug("app.channels not available, skipping marketplace update notification")
            return

        OutboundMessage = message_bus_mod.OutboundMessage
        get_channel_service = service_mod.get_channel_service

        channel_service = get_channel_service()
        if channel_service is None:
            logger.debug("ChannelService not available, skipping marketplace update notification")
            return

        channels = channel_service.list_channels()
        if not channels:
            logger.debug("No channels available for marketplace update notification")
            return

        update_descriptions = []
        for u in updates:
            update_descriptions.append(f"{u['skill_id']} ({u['installed_version']}→{u['available_version']})")
        message = f"有 {len(updates)} 个技能可更新：{', '.join(update_descriptions)}"

        for channel in channels:
            try:
                outbound = OutboundMessage(
                    channel_name=channel.name,
                    chat_id="",
                    thread_id="",
                    text=message,
                )
                await channel_service.bus.publish_outbound(outbound)
            except Exception:
                logger.exception("Failed to send marketplace update notification via %s", channel.name)

    def _is_check_fresh(self) -> bool:
        if not self._last_check:
            return False
        elapsed = (datetime.now() - self._last_check).total_seconds()
        return elapsed < self._config.cache_ttl
