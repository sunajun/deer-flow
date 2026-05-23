from __future__ import annotations

import logging
import re

from app.channels.commands.base import BaseCommand, CommandResult

logger = logging.getLogger(__name__)

_CRON_PATTERN = re.compile(
    r"^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
)


class ScheduleListCommand(BaseCommand):
    name = "schedule-list"
    aliases = ["sl"]
    description = "列出定时任务"
    usage = "/schedule-list"

    async def execute(self, message: dict, args: str) -> CommandResult:
        return CommandResult(
            success=True,
            message="No scheduled tasks found.",
            data={"schedules": []},
        )


class ScheduleCreateCommand(BaseCommand):
    name = "schedule-create"
    aliases = ["sc"]
    description = "创建定时任务"
    usage = '/schedule-create <cron_expression> <prompt> — 例: /schedule-create "0 9 * * 1-5" 每日站会提醒'

    async def execute(self, message: dict, args: str) -> CommandResult:
        args = args.strip()
        if not args:
            return CommandResult(
                success=False,
                message='Usage: /schedule-create <cron_expression> <prompt>\n例: /schedule-create "0 9 * * 1-5" 每日站会提醒',
            )

        cron_match = re.match(r'^"([^"]+)"\s+(.+)$', args)
        if not cron_match:
            cron_match = re.match(r"^((?:\S+\s+){4}\S+)\s+(.+)$", args)

        if not cron_match:
            return CommandResult(
                success=False,
                message='Invalid format. Usage: /schedule-create <cron_expression> <prompt>',
            )

        cron_expr = cron_match.group(1)
        prompt = cron_match.group(2).strip()

        if not _CRON_PATTERN.match(cron_expr):
            return CommandResult(
                success=False,
                message=f"Invalid cron expression: {cron_expr}\nExpected format: minute hour day-of-month month day-of-week",
            )

        return CommandResult(
            success=True,
            message=f"Scheduled task created.\nCron: `{cron_expr}`\nPrompt: {prompt}",
            data={"cron": cron_expr, "prompt": prompt, "action": "create"},
        )


class SchedulePauseCommand(BaseCommand):
    name = "schedule-pause"
    aliases = ["sp"]
    description = "暂停定时任务"
    usage = "/schedule-pause <task_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        task_id = args.strip()
        if not task_id:
            return CommandResult(success=False, message="Usage: /schedule-pause <task_id>")

        return CommandResult(
            success=True,
            message=f"Paused scheduled task: {task_id}",
            data={"task_id": task_id, "action": "pause"},
        )


class ScheduleResumeCommand(BaseCommand):
    name = "schedule-resume"
    aliases = ["sr"]
    description = "恢复定时任务"
    usage = "/schedule-resume <task_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        task_id = args.strip()
        if not task_id:
            return CommandResult(success=False, message="Usage: /schedule-resume <task_id>")

        return CommandResult(
            success=True,
            message=f"Resumed scheduled task: {task_id}",
            data={"task_id": task_id, "action": "resume"},
        )


class ScheduleDeleteCommand(BaseCommand):
    name = "schedule-delete"
    aliases = ["sd"]
    description = "删除定时任务"
    usage = "/schedule-delete <task_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        task_id = args.strip()
        if not task_id:
            return CommandResult(success=False, message="Usage: /schedule-delete <task_id>")

        return CommandResult(
            success=True,
            message=f"Deleted scheduled task: {task_id}",
            data={"task_id": task_id, "action": "delete"},
        )
