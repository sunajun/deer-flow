"""Shared command definitions used by all channel implementations.

Keeping the authoritative command set in one place ensures that channel
parsers (e.g. Feishu) and the ChannelManager dispatcher stay in sync
automatically — adding or removing a command here is the single edit
required.
"""

from __future__ import annotations

KNOWN_CHANNEL_COMMANDS: frozenset[str] = frozenset(
    {
        "/bootstrap",
        "/new",
        "/status",
        "/models",
        "/memory",
        "/help",
        "/lead",
        "/resume",
        "/clear",
        "/claude",
        "/claude-list",
        "/claude-resume",
        "/claude-terminate",
        "/task-list",
        "/task-retry",
        "/task-cancel",
        "/schedule-list",
        "/schedule-create",
        "/schedule-pause",
        "/schedule-resume",
        "/schedule-delete",
        "/skill-list",
        "/skill-enable",
        "/skill-disable",
        "/skill-install",
        "/skill-update",
    }
)
