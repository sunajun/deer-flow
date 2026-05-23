from __future__ import annotations

import logging

from app.channels.commands.base import BaseCommand, CommandResult

logger = logging.getLogger(__name__)


class TaskListCommand(BaseCommand):
    name = "task-list"
    aliases = ["tl"]
    description = "列出任务"
    usage = "/task-list"

    async def execute(self, message: dict, args: str) -> CommandResult:
        return CommandResult(
            success=True,
            message="No tasks found.",
            data={"tasks": []},
        )


class TaskRetryCommand(BaseCommand):
    name = "task-retry"
    aliases = ["tr"]
    description = "重试任务"
    usage = "/task-retry <task_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        task_id = args.strip()
        if not task_id:
            return CommandResult(success=False, message="Usage: /task-retry <task_id>")

        return CommandResult(
            success=True,
            message=f"Retrying task: {task_id}",
            data={"task_id": task_id, "action": "retry"},
        )


class TaskCancelCommand(BaseCommand):
    name = "task-cancel"
    aliases = ["tc"]
    description = "取消任务"
    usage = "/task-cancel <task_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        task_id = args.strip()
        if not task_id:
            return CommandResult(success=False, message="Usage: /task-cancel <task_id>")

        return CommandResult(
            success=True,
            message=f"Cancelled task: {task_id}",
            data={"task_id": task_id, "action": "cancel"},
        )
