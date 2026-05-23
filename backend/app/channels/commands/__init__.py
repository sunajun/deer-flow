from __future__ import annotations

from app.channels.commands.base import BaseCommand
from app.channels.commands.base import CommandResult as CommandResult
from app.channels.commands.claude import (
    ClaudeCommand,
    ClaudeListCommand,
    ClaudeResumeCommand,
    ClaudeTerminateCommand,
)
from app.channels.commands.conversation import (
    ClearCommand,
    LeadCommand,
    NewCommand,
    ResumeCommand,
    StatusCommand,
)
from app.channels.commands.help import HelpCommand
from app.channels.commands.schedule import (
    ScheduleCreateCommand,
    ScheduleDeleteCommand,
    ScheduleListCommand,
    SchedulePauseCommand,
    ScheduleResumeCommand,
)
from app.channels.commands.skill import (
    SkillDisableCommand,
    SkillEnableCommand,
    SkillInstallCommand,
    SkillListCommand,
    SkillUpdateCommand,
)
from app.channels.commands.task import (
    TaskCancelCommand,
    TaskListCommand,
    TaskRetryCommand,
)

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

ALL_COMMANDS: list[BaseCommand] = [
    NewCommand(),
    StatusCommand(),
    LeadCommand(),
    ResumeCommand(),
    ClearCommand(),
    ClaudeCommand(),
    ClaudeListCommand(),
    ClaudeResumeCommand(),
    ClaudeTerminateCommand(),
    TaskListCommand(),
    TaskRetryCommand(),
    TaskCancelCommand(),
    ScheduleListCommand(),
    ScheduleCreateCommand(),
    SchedulePauseCommand(),
    ScheduleResumeCommand(),
    ScheduleDeleteCommand(),
    SkillListCommand(),
    SkillEnableCommand(),
    SkillDisableCommand(),
    SkillInstallCommand(),
    SkillUpdateCommand(),
    HelpCommand(),
]

COMMAND_REGISTRY: dict[str, BaseCommand] = {}
for _cmd in ALL_COMMANDS:
    COMMAND_REGISTRY[_cmd.name] = _cmd
    for _alias in _cmd.aliases:
        COMMAND_REGISTRY[_alias] = _cmd


def find_command(name: str) -> BaseCommand | None:
    return COMMAND_REGISTRY.get(name)
