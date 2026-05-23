from __future__ import annotations

import logging

from app.channels.commands.base import BaseCommand, CommandResult

logger = logging.getLogger(__name__)


class SkillListCommand(BaseCommand):
    name = "skill-list"
    aliases = ["skl"]
    description = "列出技能"
    usage = "/skill-list"

    async def execute(self, message: dict, args: str) -> CommandResult:
        return CommandResult(
            success=True,
            message="No skills found.",
            data={"skills": []},
        )


class SkillEnableCommand(BaseCommand):
    name = "skill-enable"
    aliases = ["ske"]
    description = "启用技能"
    usage = "/skill-enable <skill_name>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        skill_name = args.strip()
        if not skill_name:
            return CommandResult(success=False, message="Usage: /skill-enable <skill_name>")

        return CommandResult(
            success=True,
            message=f"Enabled skill: {skill_name}",
            data={"skill_name": skill_name, "action": "enable"},
        )


class SkillDisableCommand(BaseCommand):
    name = "skill-disable"
    aliases = ["skd"]
    description = "禁用技能"
    usage = "/skill-disable <skill_name>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        skill_name = args.strip()
        if not skill_name:
            return CommandResult(success=False, message="Usage: /skill-disable <skill_name>")

        return CommandResult(
            success=True,
            message=f"Disabled skill: {skill_name}",
            data={"skill_name": skill_name, "action": "disable"},
        )


class SkillInstallCommand(BaseCommand):
    name = "skill-install"
    aliases = ["ski"]
    description = "安装技能"
    usage = "/skill-install <skill_id> [version]"

    async def execute(self, message: dict, args: str) -> CommandResult:
        args = args.strip()
        if not args:
            return CommandResult(success=False, message="Usage: /skill-install <skill_id> [version]")

        parts = args.split(maxsplit=1)
        skill_id = parts[0]
        version = parts[1] if len(parts) > 1 else None

        detail = f"Installing skill: {skill_id}"
        if version:
            detail += f" (version: {version})"

        return CommandResult(
            success=True,
            message=detail,
            data={"skill_id": skill_id, "version": version, "action": "install"},
        )


class SkillUpdateCommand(BaseCommand):
    name = "skill-update"
    aliases = ["sku"]
    description = "更新技能"
    usage = "/skill-update <skill_name> [version]"

    async def execute(self, message: dict, args: str) -> CommandResult:
        args = args.strip()
        if not args:
            return CommandResult(success=False, message="Usage: /skill-update <skill_name> [version]")

        parts = args.split(maxsplit=1)
        skill_name = parts[0]
        version = parts[1] if len(parts) > 1 else None

        detail = f"Updating skill: {skill_name}"
        if version:
            detail += f" to version: {version}"

        return CommandResult(
            success=True,
            message=detail,
            data={"skill_name": skill_name, "version": version, "action": "update"},
        )
