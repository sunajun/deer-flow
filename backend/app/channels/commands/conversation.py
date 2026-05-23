from __future__ import annotations

import logging

from app.channels.commands.base import BaseCommand, CommandResult

logger = logging.getLogger(__name__)


class NewCommand(BaseCommand):
    name = "new"
    aliases = ["n"]
    description = "开始新对话"
    usage = "/new"

    async def execute(self, message: dict, args: str) -> CommandResult:
        from app.channels.store import ChannelStore

        store: ChannelStore = message.get("_store")
        manager = message.get("_manager")
        if store is None or manager is None:
            return CommandResult(success=False, message="Internal error: store or manager not available.")

        client = manager._get_client()
        thread = await client.threads.create()
        new_thread_id = thread["thread_id"]
        store.set_thread_id(
            message["channel_name"],
            message["chat_id"],
            new_thread_id,
            topic_id=message.get("topic_id"),
            user_id=message.get("user_id", ""),
        )
        return CommandResult(
            success=True,
            message="New conversation started.",
            data={"thread_id": new_thread_id},
        )


class StatusCommand(BaseCommand):
    name = "status"
    aliases = ["s"]
    description = "查看当前对话状态"
    usage = "/status"

    async def execute(self, message: dict, args: str) -> CommandResult:
        from app.channels.store import ChannelStore

        store: ChannelStore = message.get("_store")
        if store is None:
            return CommandResult(success=False, message="Internal error: store not available.")

        thread_id = store.get_thread_id(
            message["channel_name"],
            message["chat_id"],
            topic_id=message.get("topic_id"),
        )
        if thread_id:
            return CommandResult(
                success=True,
                message=f"Active thread: {thread_id}",
                data={"thread_id": thread_id},
            )
        return CommandResult(success=True, message="No active conversation.")


class LeadCommand(BaseCommand):
    name = "lead"
    aliases: list[str] = []
    description = "切换到 Lead Agent 对话"
    usage = "/lead"

    async def execute(self, message: dict, args: str) -> CommandResult:
        from app.channels.store import ChannelStore

        store: ChannelStore = message.get("_store")
        if store is None:
            return CommandResult(success=False, message="Internal error: store not available.")

        thread_id = store.get_thread_id(
            message["channel_name"],
            message["chat_id"],
            topic_id=message.get("topic_id"),
        )
        if thread_id is None:
            return CommandResult(success=False, message="No active conversation. Use /new to start one.")

        return CommandResult(
            success=True,
            message="Switched to Lead Agent.",
            data={"thread_id": thread_id, "mode": "lead"},
        )


class ResumeCommand(BaseCommand):
    name = "resume"
    aliases = ["r"]
    description = "恢复指定对话"
    usage = "/resume <thread_id>"

    async def execute(self, message: dict, args: str) -> CommandResult:
        from app.channels.store import ChannelStore

        store: ChannelStore = message.get("_store")
        if store is None:
            return CommandResult(success=False, message="Internal error: store not available.")

        thread_id = args.strip()
        if not thread_id:
            return CommandResult(success=False, message="Usage: /resume <thread_id>")

        store.set_thread_id(
            message["channel_name"],
            message["chat_id"],
            thread_id,
            topic_id=message.get("topic_id"),
            user_id=message.get("user_id", ""),
        )
        return CommandResult(
            success=True,
            message=f"Resumed conversation: {thread_id}",
            data={"thread_id": thread_id},
        )


class ClearCommand(BaseCommand):
    name = "clear"
    aliases: list[str] = []
    description = "清除当前对话映射"
    usage = "/clear"

    async def execute(self, message: dict, args: str) -> CommandResult:
        from app.channels.store import ChannelStore

        store: ChannelStore = message.get("_store")
        if store is None:
            return CommandResult(success=False, message="Internal error: store not available.")

        removed = store.remove(
            message["channel_name"],
            message["chat_id"],
            topic_id=message.get("topic_id"),
        )
        if removed:
            return CommandResult(success=True, message="Conversation mapping cleared.")
        return CommandResult(success=True, message="No conversation mapping to clear.")
