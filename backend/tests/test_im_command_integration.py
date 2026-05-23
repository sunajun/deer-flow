from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.commands import get_command
from app.channels.commands.base import CommandResult
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
from app.channels.message_bus import OutboundMessage


_COMMAND_ROUTE_CASES = [
    ("/new", NewCommand, ""),
    ("/status", StatusCommand, ""),
    ("/lead", LeadCommand, ""),
    ("/resume", ResumeCommand, "thread-1"),
    ("/clear", ClearCommand, ""),
    ("/claude", ClaudeCommand, ""),
    ("/claude-list", ClaudeListCommand, ""),
    ("/claude-resume", ClaudeResumeCommand, "session-1"),
    ("/claude-terminate", ClaudeTerminateCommand, "session-1"),
    ("/task-list", TaskListCommand, ""),
    ("/task-retry", TaskRetryCommand, "task-1"),
    ("/task-cancel", TaskCancelCommand, "task-1"),
    ("/schedule-list", ScheduleListCommand, ""),
    ("/schedule-create", ScheduleCreateCommand, '"0 9 * * 1-5" test'),
    ("/schedule-pause", SchedulePauseCommand, "sched-1"),
    ("/schedule-resume", ScheduleResumeCommand, "sched-1"),
    ("/schedule-delete", ScheduleDeleteCommand, "sched-1"),
    ("/skill-list", SkillListCommand, ""),
    ("/skill-enable", SkillEnableCommand, "web-search"),
    ("/skill-disable", SkillDisableCommand, "web-search"),
    ("/skill-install", SkillInstallCommand, "search-skill"),
    ("/skill-update", SkillUpdateCommand, "web-search"),
    ("/help", HelpCommand, ""),
]


_ALIAS_ROUTE_CASES = [
    ("/n", NewCommand),
    ("/s", StatusCommand),
    ("/r", ResumeCommand),
    ("/cl", ClaudeListCommand),
    ("/cr", ClaudeResumeCommand),
    ("/ct", ClaudeTerminateCommand),
    ("/tl", TaskListCommand),
    ("/tr", TaskRetryCommand),
    ("/tc", TaskCancelCommand),
    ("/sl", ScheduleListCommand),
    ("/sc", ScheduleCreateCommand),
    ("/sp", SchedulePauseCommand),
    ("/sr", ScheduleResumeCommand),
    ("/sd", ScheduleDeleteCommand),
    ("/skl", SkillListCommand),
    ("/ske", SkillEnableCommand),
    ("/skd", SkillDisableCommand),
    ("/ski", SkillInstallCommand),
    ("/sku", SkillUpdateCommand),
    ("/h", HelpCommand),
    ("/?", HelpCommand),
]


_COMPOUND_ROUTE_CASES = [
    ("/claude list", ClaudeListCommand),
    ("/claude resume", ClaudeResumeCommand),
    ("/claude terminate", ClaudeTerminateCommand),
    ("/task list", TaskListCommand),
    ("/task retry", TaskRetryCommand),
    ("/task cancel", TaskCancelCommand),
    ("/schedule list", ScheduleListCommand),
    ("/schedule create", ScheduleCreateCommand),
    ("/schedule pause", SchedulePauseCommand),
    ("/schedule resume", ScheduleResumeCommand),
    ("/schedule delete", ScheduleDeleteCommand),
    ("/skill list", SkillListCommand),
    ("/skill enable", SkillEnableCommand),
    ("/skill disable", SkillDisableCommand),
    ("/skill install", SkillInstallCommand),
    ("/skill update", SkillUpdateCommand),
]


class TestAllCommandRouting:
    @pytest.mark.parametrize(
        "cmd_text,expected_class,args",
        _COMMAND_ROUTE_CASES,
        ids=[c[0] for c in _COMMAND_ROUTE_CASES],
    )
    @pytest.mark.asyncio
    async def test_command_routes_correctly(
        self,
        mock_channel_manager,
        sample_inbound_message,
        cmd_text,
        expected_class,
        args,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        if cmd_text == "/new":
            mock_client = MagicMock()
            mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-new"})
            mgr._get_client = MagicMock(return_value=mock_client)

        msg = sample_inbound_message(text=cmd_text + (f" {args}" if args else ""))
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert isinstance(outbound, OutboundMessage)
        assert outbound.channel_name == "feishu"
        assert outbound.chat_id == "test-chat-1"
        assert outbound.text


class TestAliasRouting:
    @pytest.mark.parametrize(
        "alias_text,expected_class",
        _ALIAS_ROUTE_CASES,
        ids=[c[0] for c in _ALIAS_ROUTE_CASES],
    )
    @pytest.mark.asyncio
    async def test_alias_routes_correctly(
        self,
        mock_channel_manager,
        sample_inbound_message,
        alias_text,
        expected_class,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        if alias_text in ("/n",):
            mock_client = MagicMock()
            mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-new"})
            mgr._get_client = MagicMock(return_value=mock_client)

        msg = sample_inbound_message(text=alias_text)
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        assert isinstance(published[0], OutboundMessage)


class TestCompoundCommandRouting:
    @pytest.mark.parametrize(
        "compound_text,expected_class",
        _COMPOUND_ROUTE_CASES,
        ids=[c[0].replace("/", "").replace(" ", "_") for c in _COMPOUND_ROUTE_CASES],
    )
    @pytest.mark.asyncio
    async def test_compound_routes_correctly(
        self,
        mock_channel_manager,
        sample_inbound_message,
        compound_text,
        expected_class,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text=compound_text)
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        assert isinstance(published[0], OutboundMessage)


class TestUnknownCommandRouting:
    @pytest.mark.asyncio
    async def test_unknown_command_returns_error(
        self,
        mock_channel_manager,
        sample_inbound_message,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/unknown")
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert "❌" in outbound.text
        assert "未知命令" in outbound.text


class TestCommandExecutionException:
    @pytest.mark.asyncio
    async def test_command_exception_returns_failure(
        self,
        mock_channel_manager,
        sample_inbound_message,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(side_effect=RuntimeError("API unavailable"))
        mgr._get_client = MagicMock(return_value=mock_client)

        msg = sample_inbound_message(text="/new")
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert "❌" in outbound.text
        assert "命令执行失败" in outbound.text


class TestOutboundMessagePublished:
    @pytest.mark.asyncio
    async def test_outbound_published_to_bus(
        self,
        mock_channel_manager,
        sample_inbound_message,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/help")
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert outbound.channel_name == "feishu"
        assert outbound.chat_id == "test-chat-1"
        assert isinstance(outbound.text, str)
        assert len(outbound.text) > 0

    @pytest.mark.asyncio
    async def test_outbound_preserves_channel_and_chat(
        self,
        mock_channel_manager,
        sample_inbound_message,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/status", channel_name="slack")
        msg.chat_id = "slack-chat-42"
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        assert published[0].channel_name == "slack"
        assert published[0].chat_id == "slack-chat-42"


class TestCommandCount:
    def test_all_23_commands_registered(self, all_commands):
        assert len(all_commands) == 23

    def test_command_names_cover_all_categories(self, all_commands):
        names = {cmd.name for cmd in all_commands}
        conversation = {"new", "status", "lead", "resume", "clear"}
        claude = {"claude", "claude-list", "claude-resume", "claude-terminate"}
        task = {"task-list", "task-retry", "task-cancel"}
        schedule = {"schedule-list", "schedule-create", "schedule-pause", "schedule-resume", "schedule-delete"}
        skill = {"skill-list", "skill-enable", "skill-disable", "skill-install", "skill-update"}
        help_cmds = {"help"}
        assert conversation.issubset(names)
        assert claude.issubset(names)
        assert task.issubset(names)
        assert schedule.issubset(names)
        assert skill.issubset(names)
        assert help_cmds.issubset(names)
