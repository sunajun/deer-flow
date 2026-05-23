from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.commands.base import CommandResult
from app.channels.commands.formatters import (
    DingTalkFormatter,
    DiscordFormatter,
    FeishuFormatter,
    SlackFormatter,
    TelegramFormatter,
    WeChatFormatter,
    WeComFormatter,
    get_formatter,
)
from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, InboundMessageType, MessageBus, OutboundMessage
from app.channels.store import ChannelStore


def _make_mgr(tmp_path, bus=None):
    if bus is None:
        bus = MessageBus()
    store = ChannelStore(path=tmp_path / "edge_store.json")
    mgr = ChannelManager(bus=bus, store=store)
    mgr._semaphore = asyncio.Semaphore(5)
    return mgr, bus, store


def _make_cmd_msg(text, channel_name="feishu", **overrides):
    msg = InboundMessage(
        channel_name=channel_name,
        chat_id="edge-chat",
        user_id="edge-user",
        text=text,
        msg_type=InboundMessageType.COMMAND,
    )
    for k, v in overrides.items():
        setattr(msg, k, v)
    return msg


async def _dispatch_and_collect(mgr, bus, msg):
    published = []

    async def _capture(m):
        published.append(m)

    bus.subscribe_outbound(_capture)
    await mgr._handle_command(msg)
    return published


class TestEmptyMessage:
    @pytest.mark.asyncio
    async def test_empty_text(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_whitespace_only(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("   ")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text


class TestSlashOnlyMessage:
    @pytest.mark.asyncio
    async def test_only_slash(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text


class TestMissingCommandArgs:
    @pytest.mark.asyncio
    async def test_resume_without_thread_id(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/resume")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text
        assert "Usage" in published[0].text

    @pytest.mark.asyncio
    async def test_task_retry_without_task_id(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/task-retry")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_task_cancel_without_task_id(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/task-cancel")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_schedule_create_without_args(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/schedule-create")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_schedule_pause_without_task_id(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/schedule-pause")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_skill_enable_without_name(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/skill-enable")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_skill_install_without_args(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/skill-install")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_claude_resume_without_session_id(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/claude-resume")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_claude_terminate_without_session_id(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/claude-terminate")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text


class TestInvalidCommandArgs:
    @pytest.mark.asyncio
    async def test_schedule_create_invalid_cron(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg('/schedule-create "invalid" some prompt')
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text
        assert "Invalid cron" in published[0].text

    @pytest.mark.asyncio
    async def test_schedule_create_malformed_args(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)
        msg = _make_cmd_msg("/schedule-create xyz")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text


class TestCommandExecutionTimeout:
    @pytest.mark.asyncio
    async def test_command_exception_handled_gracefully(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(side_effect=asyncio.TimeoutError("timeout"))
        mgr._get_client = MagicMock(return_value=mock_client)

        msg = _make_cmd_msg("/new")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text
        assert "命令执行失败" in published[0].text


class TestCommandApiUnavailable:
    @pytest.mark.asyncio
    async def test_command_connection_error(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(side_effect=ConnectionError("API unavailable"))
        mgr._get_client = MagicMock(return_value=mock_client)

        msg = _make_cmd_msg("/new")
        published = await _dispatch_and_collect(mgr, bus, msg)
        assert len(published) == 1
        assert "❌" in published[0].text
        assert "命令执行失败" in published[0].text


class TestSpecialCharacterFormatting:
    def test_telegram_escapes_markdown_chars(self):
        f = get_formatter("telegram")
        result = CommandResult(success=True, message="hello_world *bold* [link]")
        text = f.format_result(result)
        assert "hello\\_world" in text
        assert "\\*bold\\*" in text
        assert "\\[link\\]" in text

    def test_feishu_no_escape_needed(self):
        f = get_formatter("feishu")
        result = CommandResult(success=True, message="hello_world *bold*")
        text = f.format_result(result)
        assert "hello_world" in text

    def test_wechat_strips_all_formatting(self):
        f = get_formatter("wechat")
        result = CommandResult(success=True, message="hello_world")
        text = f.format_result(result)
        assert "hello_world" in text
        assert "**" not in text

    def test_emoji_in_result(self):
        for channel in ["feishu", "slack", "discord", "telegram", "wecom", "dingtalk", "wechat"]:
            f = get_formatter(channel)
            result = CommandResult(success=True, message="✅ Done 🎉")
            text = f.format_result(result)
            assert "✅" in text
            assert "🎉" in text

    def test_chinese_characters(self):
        for channel in ["feishu", "slack", "discord", "telegram", "wecom", "dingtalk", "wechat"]:
            f = get_formatter(channel)
            result = CommandResult(success=True, message="对话已创建")
            text = f.format_result(result)
            assert "对话已创建" in text


class TestConcurrentCommandExecution:
    @pytest.mark.asyncio
    async def test_concurrent_commands(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "edge_store.json")
        mgr = ChannelManager(bus=bus, store=store)
        mgr._semaphore = asyncio.Semaphore(10)

        published = []

        async def _capture(m):
            published.append(m)

        bus.subscribe_outbound(_capture)

        commands = ["/status", "/help", "/task-list", "/schedule-list", "/skill-list"]
        tasks = []
        for cmd in commands:
            msg = _make_cmd_msg(cmd, chat_id=f"concurrent-{cmd}")
            tasks.append(mgr._handle_command(msg))

        await asyncio.gather(*tasks)

        assert len(published) == 5
        channels = {p.channel_name for p in published}
        assert channels == {"feishu"}


class TestLongMessageTruncation:
    @pytest.mark.asyncio
    async def test_long_args_handled(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)

        long_arg = "x" * 10000
        msg = _make_cmd_msg(f"/skill-install {long_arg}")
        published = await _dispatch_and_collect(mgr, bus, msg)

        assert len(published) == 1
        assert "✅" in published[0].text

    @pytest.mark.asyncio
    async def test_long_help_output(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)

        msg = _make_cmd_msg("/help")
        published = await _dispatch_and_collect(mgr, bus, msg)

        assert len(published) == 1
        assert len(published[0].text) > 100
