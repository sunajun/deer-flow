from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.commands import ALL_COMMANDS, KNOWN_CHANNEL_COMMANDS, find_command
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


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_store(tmp_path=None):
    from app.channels.store import ChannelStore

    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    return ChannelStore(path=tmp_path / "store.json")


def _make_message(**overrides):
    msg = {
        "channel_name": "test",
        "chat_id": "chat1",
        "user_id": "user1",
        "topic_id": None,
        "_store": None,
        "_manager": None,
    }
    msg.update(overrides)
    return msg


class TestCommandResult:
    def test_defaults(self):
        r = CommandResult(success=True, message="ok")
        assert r.success is True
        assert r.message == "ok"
        assert r.data is None
        assert r.format_hint == "markdown"

    def test_with_data(self):
        r = CommandResult(success=True, message="ok", data={"key": "val"}, format_hint="json")
        assert r.data == {"key": "val"}
        assert r.format_hint == "json"


class TestBaseCommandMatch:
    def test_match_by_name(self):
        cmd = NewCommand()
        assert cmd.match("new") is True

    def test_match_by_alias(self):
        cmd = NewCommand()
        assert cmd.match("n") is True

    def test_no_match(self):
        cmd = NewCommand()
        assert cmd.match("unknown") is False

    def test_match_no_aliases(self):
        cmd = LeadCommand()
        assert cmd.match("lead") is True
        assert cmd.match("l") is False

    def test_help_alias(self):
        cmd = HelpCommand()
        assert cmd.match("help") is True
        assert cmd.match("h") is True
        assert cmd.match("?") is True


class TestBaseCommandGetHelp:
    def test_get_help_format(self):
        cmd = NewCommand()
        help_text = cmd.get_help()
        assert "/new" in help_text
        assert "开始新对话" in help_text
        assert "用法:" in help_text


class TestCommandRegistry:
    def test_all_commands_registered(self):
        assert len(ALL_COMMANDS) == 23

    def test_find_command_by_name(self):
        cmd = find_command("new")
        assert cmd is not None
        assert isinstance(cmd, NewCommand)

    def test_find_command_by_alias(self):
        cmd = find_command("n")
        assert cmd is not None
        assert isinstance(cmd, NewCommand)

    def test_find_command_unknown(self):
        cmd = find_command("nonexistent")
        assert cmd is None

    def test_no_duplicate_names(self):
        names = [cmd.name for cmd in ALL_COMMANDS]
        assert len(names) == len(set(names))

    def test_all_aliases_unique(self):
        all_ids: list[str] = []
        for cmd in ALL_COMMANDS:
            all_ids.append(cmd.name)
            all_ids.extend(cmd.aliases)
        assert len(all_ids) == len(set(all_ids))


class TestKnownChannelCommands:
    def test_contains_all_new_commands(self):
        expected = {
            "/bootstrap", "/new", "/status", "/models", "/memory", "/help",
            "/lead", "/resume", "/clear",
            "/claude", "/claude-list", "/claude-resume", "/claude-terminate",
            "/task-list", "/task-retry", "/task-cancel",
            "/schedule-list", "/schedule-create", "/schedule-pause", "/schedule-resume", "/schedule-delete",
            "/skill-list", "/skill-enable", "/skill-disable", "/skill-install", "/skill-update",
        }
        for cmd in expected:
            assert cmd in KNOWN_CHANNEL_COMMANDS, f"{cmd} not in KNOWN_CHANNEL_COMMANDS"

    def test_total_count(self):
        assert len(KNOWN_CHANNEL_COMMANDS) == 26


class TestNewCommand:
    def test_execute_creates_new_thread(self):
        store = _make_store()
        mock_manager = MagicMock()
        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(return_value={"thread_id": "new-thread-123"})
        mock_manager._get_client.return_value = mock_client

        msg = _make_message(_store=store, _manager=mock_manager)
        result = _run(NewCommand().execute(msg, ""))
        assert result.success is True
        assert "New conversation started" in result.message
        assert result.data["thread_id"] == "new-thread-123"
        assert store.get_thread_id("test", "chat1") == "new-thread-123"

    def test_execute_without_store(self):
        msg = _make_message()
        result = _run(NewCommand().execute(msg, ""))
        assert result.success is False


class TestStatusCommand:
    def test_execute_with_active_thread(self):
        store = _make_store()
        store.set_thread_id("test", "chat1", "thread-abc", user_id="user1")

        msg = _make_message(_store=store)
        result = _run(StatusCommand().execute(msg, ""))
        assert result.success is True
        assert "thread-abc" in result.message

    def test_execute_without_active_thread(self):
        store = _make_store()
        msg = _make_message(_store=store)
        result = _run(StatusCommand().execute(msg, ""))
        assert result.success is True
        assert "No active conversation" in result.message


class TestLeadCommand:
    def test_execute_with_active_thread(self):
        store = _make_store()
        store.set_thread_id("test", "chat1", "thread-abc", user_id="user1")

        msg = _make_message(_store=store)
        result = _run(LeadCommand().execute(msg, ""))
        assert result.success is True
        assert "Switched to Lead Agent" in result.message

    def test_execute_without_active_thread(self):
        store = _make_store()
        msg = _make_message(_store=store)
        result = _run(LeadCommand().execute(msg, ""))
        assert result.success is False
        assert "No active conversation" in result.message


class TestResumeCommand:
    def test_execute_with_thread_id(self):
        store = _make_store()
        msg = _make_message(_store=store)
        result = _run(ResumeCommand().execute(msg, "thread-xyz"))
        assert result.success is True
        assert "thread-xyz" in result.message
        assert store.get_thread_id("test", "chat1") == "thread-xyz"

    def test_execute_without_thread_id(self):
        store = _make_store()
        msg = _make_message(_store=store)
        result = _run(ResumeCommand().execute(msg, ""))
        assert result.success is False
        assert "Usage" in result.message


class TestClearCommand:
    def test_execute_with_existing_mapping(self):
        store = _make_store()
        store.set_thread_id("test", "chat1", "thread-abc", user_id="user1")

        msg = _make_message(_store=store)
        result = _run(ClearCommand().execute(msg, ""))
        assert result.success is True
        assert "cleared" in result.message
        assert store.get_thread_id("test", "chat1") is None

    def test_execute_without_existing_mapping(self):
        store = _make_store()
        msg = _make_message(_store=store)
        result = _run(ClearCommand().execute(msg, ""))
        assert result.success is True
        assert "No conversation mapping" in result.message


class TestClaudeCommand:
    def test_execute_new_session(self):
        msg = _make_message()
        result = _run(ClaudeCommand().execute(msg, ""))
        assert result.success is True
        assert result.data["action"] == "create"

    def test_execute_resume_session(self):
        msg = _make_message()
        result = _run(ClaudeCommand().execute(msg, "session-123"))
        assert result.success is True
        assert result.data["action"] == "resume"
        assert result.data["session_id"] == "session-123"


class TestClaudeListCommand:
    def test_execute(self):
        msg = _make_message()
        result = _run(ClaudeListCommand().execute(msg, ""))
        assert result.success is True
        assert "sessions" in result.data


class TestClaudeResumeCommand:
    def test_execute_with_session_id(self):
        msg = _make_message()
        result = _run(ClaudeResumeCommand().execute(msg, "session-abc"))
        assert result.success is True
        assert result.data["session_id"] == "session-abc"

    def test_execute_without_session_id(self):
        msg = _make_message()
        result = _run(ClaudeResumeCommand().execute(msg, ""))
        assert result.success is False


class TestClaudeTerminateCommand:
    def test_execute_with_session_id(self):
        msg = _make_message()
        result = _run(ClaudeTerminateCommand().execute(msg, "session-abc"))
        assert result.success is True
        assert result.data["session_id"] == "session-abc"

    def test_execute_without_session_id(self):
        msg = _make_message()
        result = _run(ClaudeTerminateCommand().execute(msg, ""))
        assert result.success is False


class TestTaskListCommand:
    def test_execute(self):
        msg = _make_message()
        result = _run(TaskListCommand().execute(msg, ""))
        assert result.success is True
        assert "tasks" in result.data


class TestTaskRetryCommand:
    def test_execute_with_task_id(self):
        msg = _make_message()
        result = _run(TaskRetryCommand().execute(msg, "task-123"))
        assert result.success is True
        assert result.data["task_id"] == "task-123"
        assert result.data["action"] == "retry"

    def test_execute_without_task_id(self):
        msg = _make_message()
        result = _run(TaskRetryCommand().execute(msg, ""))
        assert result.success is False


class TestTaskCancelCommand:
    def test_execute_with_task_id(self):
        msg = _make_message()
        result = _run(TaskCancelCommand().execute(msg, "task-456"))
        assert result.success is True
        assert result.data["task_id"] == "task-456"
        assert result.data["action"] == "cancel"

    def test_execute_without_task_id(self):
        msg = _make_message()
        result = _run(TaskCancelCommand().execute(msg, ""))
        assert result.success is False


class TestScheduleListCommand:
    def test_execute(self):
        msg = _make_message()
        result = _run(ScheduleListCommand().execute(msg, ""))
        assert result.success is True
        assert "schedules" in result.data


class TestScheduleCreateCommand:
    def test_execute_with_quoted_cron(self):
        msg = _make_message()
        result = _run(ScheduleCreateCommand().execute(msg, '"0 9 * * 1-5" 每日站会提醒'))
        assert result.success is True
        assert result.data["cron"] == "0 9 * * 1-5"
        assert result.data["prompt"] == "每日站会提醒"

    def test_execute_with_unquoted_cron(self):
        msg = _make_message()
        result = _run(ScheduleCreateCommand().execute(msg, "0 9 * * 1-5 每日站会提醒"))
        assert result.success is True
        assert result.data["cron"] == "0 9 * * 1-5"

    def test_execute_without_args(self):
        msg = _make_message()
        result = _run(ScheduleCreateCommand().execute(msg, ""))
        assert result.success is False

    def test_execute_invalid_cron(self):
        msg = _make_message()
        result = _run(ScheduleCreateCommand().execute(msg, '"invalid" some prompt'))
        assert result.success is False
        assert "Invalid cron" in result.message


class TestSchedulePauseCommand:
    def test_execute_with_task_id(self):
        msg = _make_message()
        result = _run(SchedulePauseCommand().execute(msg, "sched-1"))
        assert result.success is True
        assert result.data["action"] == "pause"

    def test_execute_without_task_id(self):
        msg = _make_message()
        result = _run(SchedulePauseCommand().execute(msg, ""))
        assert result.success is False


class TestScheduleResumeCommand:
    def test_execute_with_task_id(self):
        msg = _make_message()
        result = _run(ScheduleResumeCommand().execute(msg, "sched-1"))
        assert result.success is True
        assert result.data["action"] == "resume"


class TestScheduleDeleteCommand:
    def test_execute_with_task_id(self):
        msg = _make_message()
        result = _run(ScheduleDeleteCommand().execute(msg, "sched-1"))
        assert result.success is True
        assert result.data["action"] == "delete"


class TestSkillListCommand:
    def test_execute(self):
        msg = _make_message()
        result = _run(SkillListCommand().execute(msg, ""))
        assert result.success is True
        assert "skills" in result.data


class TestSkillEnableCommand:
    def test_execute_with_skill_name(self):
        msg = _make_message()
        result = _run(SkillEnableCommand().execute(msg, "web-search"))
        assert result.success is True
        assert result.data["skill_name"] == "web-search"
        assert result.data["action"] == "enable"

    def test_execute_without_skill_name(self):
        msg = _make_message()
        result = _run(SkillEnableCommand().execute(msg, ""))
        assert result.success is False


class TestSkillDisableCommand:
    def test_execute_with_skill_name(self):
        msg = _make_message()
        result = _run(SkillDisableCommand().execute(msg, "web-search"))
        assert result.success is True
        assert result.data["action"] == "disable"


class TestSkillInstallCommand:
    def test_execute_with_id_only(self):
        msg = _make_message()
        result = _run(SkillInstallCommand().execute(msg, "my-skill"))
        assert result.success is True
        assert result.data["skill_id"] == "my-skill"
        assert result.data["version"] is None

    def test_execute_with_id_and_version(self):
        msg = _make_message()
        result = _run(SkillInstallCommand().execute(msg, "my-skill 1.2.3"))
        assert result.success is True
        assert result.data["skill_id"] == "my-skill"
        assert result.data["version"] == "1.2.3"

    def test_execute_without_args(self):
        msg = _make_message()
        result = _run(SkillInstallCommand().execute(msg, ""))
        assert result.success is False


class TestSkillUpdateCommand:
    def test_execute_with_name_only(self):
        msg = _make_message()
        result = _run(SkillUpdateCommand().execute(msg, "web-search"))
        assert result.success is True
        assert result.data["skill_name"] == "web-search"
        assert result.data["version"] is None

    def test_execute_with_name_and_version(self):
        msg = _make_message()
        result = _run(SkillUpdateCommand().execute(msg, "web-search 2.0.0"))
        assert result.success is True
        assert result.data["version"] == "2.0.0"


class TestHelpCommand:
    def test_execute(self):
        msg = _make_message()
        result = _run(HelpCommand().execute(msg, ""))
        assert result.success is True
        assert "/new" in result.message
        assert "/help" in result.message
        assert "对话管理" in result.message
        assert "Claude Code" in result.message
        assert "任务管理" in result.message
        assert "定时任务" in result.message
        assert "技能管理" in result.message

    def test_help_includes_all_categories(self):
        msg = _make_message()
        result = _run(HelpCommand().execute(msg, ""))
        for cmd in ALL_COMMANDS:
            assert f"/{cmd.name}" in result.message


class TestAliasMatching:
    @pytest.mark.parametrize(
        "alias,expected_class",
        [
            ("n", NewCommand),
            ("s", StatusCommand),
            ("r", ResumeCommand),
            ("cl", ClaudeListCommand),
            ("cr", ClaudeResumeCommand),
            ("ct", ClaudeTerminateCommand),
            ("tl", TaskListCommand),
            ("tr", TaskRetryCommand),
            ("tc", TaskCancelCommand),
            ("sl", ScheduleListCommand),
            ("sc", ScheduleCreateCommand),
            ("sp", SchedulePauseCommand),
            ("sr", ScheduleResumeCommand),
            ("sd", ScheduleDeleteCommand),
            ("skl", SkillListCommand),
            ("ske", SkillEnableCommand),
            ("skd", SkillDisableCommand),
            ("ski", SkillInstallCommand),
            ("sku", SkillUpdateCommand),
            ("h", HelpCommand),
            ("?", HelpCommand),
        ],
    )
    def test_alias_matches_correct_command(self, alias, expected_class):
        cmd = find_command(alias)
        assert cmd is not None, f"No command found for alias '{alias}'"
        assert isinstance(cmd, expected_class), f"Alias '{alias}' should map to {expected_class.__name__}, got {type(cmd).__name__}"


class TestErrorHandling:
    def test_conversation_commands_without_store(self):
        for cmd_class in [NewCommand, StatusCommand, LeadCommand, ResumeCommand, ClearCommand]:
            msg = _make_message()
            result = _run(cmd_class().execute(msg, ""))
            assert result.success is False, f"{cmd_class.__name__} should fail without store"

    def test_resume_without_args(self):
        msg = _make_message()
        result = _run(ResumeCommand().execute(msg, ""))
        assert result.success is False

    def test_claude_resume_without_session_id(self):
        msg = _make_message()
        result = _run(ClaudeResumeCommand().execute(msg, ""))
        assert result.success is False

    def test_claude_terminate_without_session_id(self):
        msg = _make_message()
        result = _run(ClaudeTerminateCommand().execute(msg, ""))
        assert result.success is False

    def test_task_retry_without_task_id(self):
        msg = _make_message()
        result = _run(TaskRetryCommand().execute(msg, ""))
        assert result.success is False

    def test_task_cancel_without_task_id(self):
        msg = _make_message()
        result = _run(TaskCancelCommand().execute(msg, ""))
        assert result.success is False

    def test_schedule_create_without_args(self):
        msg = _make_message()
        result = _run(ScheduleCreateCommand().execute(msg, ""))
        assert result.success is False

    def test_skill_enable_without_name(self):
        msg = _make_message()
        result = _run(SkillEnableCommand().execute(msg, ""))
        assert result.success is False

    def test_skill_install_without_args(self):
        msg = _make_message()
        result = _run(SkillInstallCommand().execute(msg, ""))
        assert result.success is False
