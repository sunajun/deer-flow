from __future__ import annotations

import logging

from app.channels.commands.base import BaseCommand, CommandResult

logger = logging.getLogger(__name__)


class ClaudeCommand(BaseCommand):
    name = "claude"
    aliases: list[str] = []
    description = "启动 Claude Code 会话"
    usage = "/claude [session_id] — 不带 session_id 创建新会话，带 session_id 续接会话"

    async def execute(self, message: dict, args: str) -> CommandResult:
        session_id = args.strip()
        if session_id:
            return CommandResult(
                success=True,
                message=f"Resuming Claude Code session: {session_id}",
                data={"action": "resume", "session_id": session_id},
            )
        return CommandResult(
            success=True,
            message="Creating new Claude Code session...",
            data={"action": "create"},
        )


class ClaudeListCommand(BaseCommand):
    name = "claude-list"
    aliases = ["cl"]
    description = "列出 Claude Code 会话"
    usage = "/claude-list"

    async def execute(self, message: dict, args: str) -> CommandResult:
        return CommandResult(
            success=True,
            message="No active Claude Code sessions.",
            data={"sessions": []},
        )


class ClaudeResumeCommand(BaseCommand):
    name = "claude-resume"
    aliases = ["cr"]
    description = "续接 Claude Code 会话"
    usage = "/claude-resume <session_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        session_id = args.strip()
        if not session_id:
            return CommandResult(success=False, message="Usage: /claude-resume <session_id>")

        return CommandResult(
            success=True,
            message=f"Resuming Claude Code session: {session_id}",
            data={"action": "resume", "session_id": session_id},
        )


class ClaudeTerminateCommand(BaseCommand):
    name = "claude-terminate"
    aliases = ["ct"]
    description = "终止 Claude Code 会话"
    usage = "/claude-terminate <session_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        session_id = args.strip()
        if not session_id:
            return CommandResult(success=False, message="Usage: /claude-terminate <session_id>")

        return CommandResult(
            success=True,
            message=f"Terminated Claude Code session: {session_id}",
            data={"action": "terminate", "session_id": session_id},
        )
