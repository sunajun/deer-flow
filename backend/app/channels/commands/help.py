from __future__ import annotations

from app.channels.commands.base import BaseCommand, CommandResult


class HelpCommand(BaseCommand):
    name = "help"
    aliases = ["h", "?"]
    description = "显示帮助信息"
    usage = "/help"

    async def execute(self, message: dict, args: str) -> CommandResult:
        from app.channels.commands import ALL_COMMANDS

        categories: dict[str, list[BaseCommand]] = {
            "对话管理": [],
            "Claude Code": [],
            "任务管理": [],
            "定时任务": [],
            "技能管理": [],
            "帮助": [],
        }

        category_map = {
            "new": "对话管理",
            "status": "对话管理",
            "lead": "对话管理",
            "resume": "对话管理",
            "clear": "对话管理",
            "claude": "Claude Code",
            "claude-list": "Claude Code",
            "claude-resume": "Claude Code",
            "claude-terminate": "Claude Code",
            "task-list": "任务管理",
            "task-retry": "任务管理",
            "task-cancel": "任务管理",
            "schedule-list": "定时任务",
            "schedule-create": "定时任务",
            "schedule-pause": "定时任务",
            "schedule-resume": "定时任务",
            "schedule-delete": "定时任务",
            "skill-list": "技能管理",
            "skill-enable": "技能管理",
            "skill-disable": "技能管理",
            "skill-install": "技能管理",
            "skill-update": "技能管理",
            "help": "帮助",
        }

        for cmd in ALL_COMMANDS:
            cat = category_map.get(cmd.name, "帮助")
            if cat in categories:
                categories[cat].append(cmd)

        lines = ["**可用命令**\n"]
        for category, cmds in categories.items():
            if not cmds:
                continue
            lines.append(f"**{category}**")
            for cmd in cmds:
                alias_str = ""
                if cmd.aliases:
                    alias_str = " (" + ", ".join(f"/{a}" for a in cmd.aliases) + ")"
                lines.append(f"  /{cmd.name}{alias_str} — {cmd.description}")
            lines.append("")

        return CommandResult(
            success=True,
            message="\n".join(lines).strip(),
        )
