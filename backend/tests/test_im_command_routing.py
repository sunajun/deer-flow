from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.commands import get_command, get_all_commands, find_command
from app.channels.commands.base import BaseCommand, CommandResult
from app.channels.commands.conversation import NewCommand, StatusCommand
from app.channels.commands.help import HelpCommand
from app.channels.commands.claude import ClaudeListCommand
from app.channels.commands.formatters import (
    BaseFormatter,
    FeishuFormatter,
    WeComFormatter,
    DingTalkFormatter,
    SlackFormatter,
    TelegramFormatter,
    DiscordFormatter,
    WeChatFormatter,
    get_formatter,
)
from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, InboundMessageType, MessageBus
from app.channels.store import ChannelStore


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_store(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    return ChannelStore(path=tmp_path / "store.json")


def _make_inbound(text: str, channel_name: str = "feishu", **overrides) -> InboundMessage:
    msg = InboundMessage(
        channel_name=channel_name,
        chat_id="chat1",
        user_id="user1",
        text=text,
        msg_type=InboundMessageType.COMMAND,
    )
    for k, v in overrides.items():
        setattr(msg, k, v)
    return msg


class TestGetCommand:
    def test_get_command_new(self):
        cmd = get_command("new")
        assert cmd is not None
        assert isinstance(cmd, NewCommand)

    def test_get_command_help(self):
        cmd = get_command("help")
        assert cmd is not None
        assert isinstance(cmd, HelpCommand)

    def test_get_command_unknown(self):
        cmd = get_command("unknown")
        assert cmd is None

    def test_get_command_by_alias(self):
        cmd = get_command("n")
        assert cmd is not None
        assert isinstance(cmd, NewCommand)


class TestGetAllCommands:
    def test_returns_list(self):
        cmds = get_all_commands()
        assert isinstance(cmds, list)
        assert len(cmds) > 0

    def test_all_are_base_command(self):
        cmds = get_all_commands()
        for cmd in cmds:
            assert isinstance(cmd, BaseCommand)

    def test_includes_new_and_help(self):
        cmds = get_all_commands()
        names = [cmd.name for cmd in cmds]
        assert "new" in names
        assert "help" in names


class TestFeishuFormatter:
    def test_format_result_success(self):
        f = FeishuFormatter()
        result = CommandResult(success=True, message="ok")
        text = f.format_result(result)
        assert "✅" in text
        assert "**ok**" in text

    def test_format_result_failure(self):
        f = FeishuFormatter()
        result = CommandResult(success=False, message="error")
        text = f.format_result(result)
        assert "❌" in text
        assert "**error**" in text

    def test_format_bold(self):
        assert FeishuFormatter().format_bold("hi") == "**hi**"

    def test_format_italic(self):
        assert FeishuFormatter().format_italic("hi") == "*hi*"

    def test_format_code_block(self):
        assert FeishuFormatter().format_code_block("x=1", "python") == "```python\nx=1\n```"

    def test_format_link(self):
        assert FeishuFormatter().format_link("txt", "http://a") == "[txt](http://a)"

    def test_format_table(self):
        f = FeishuFormatter()
        text = f.format_table(["A", "B"], [["1", "2"]])
        assert "**A | B**" in text
        assert "1 | 2" in text


class TestSlackFormatter:
    def test_format_result_success(self):
        f = SlackFormatter()
        result = CommandResult(success=True, message="ok")
        text = f.format_result(result)
        assert "✅" in text
        assert "*ok*" in text

    def test_format_link(self):
        assert SlackFormatter().format_link("txt", "http://a") == "<http://a|txt>"

    def test_format_bold(self):
        assert SlackFormatter().format_bold("hi") == "*hi*"

    def test_format_italic(self):
        assert SlackFormatter().format_italic("hi") == "_hi_"


class TestDiscordFormatter:
    def test_format_result_success(self):
        f = DiscordFormatter()
        result = CommandResult(success=True, message="ok")
        text = f.format_result(result)
        assert "✅" in text
        assert "**ok**" in text

    def test_format_bold(self):
        assert DiscordFormatter().format_bold("hi") == "**hi**"

    def test_format_link(self):
        assert DiscordFormatter().format_link("txt", "http://a") == "[txt](http://a)"


class TestWeChatFormatter:
    def test_format_result_no_markdown(self):
        f = WeChatFormatter()
        result = CommandResult(success=True, message="ok")
        text = f.format_result(result)
        assert "✅" in text
        assert "**" not in text
        assert "ok" in text

    def test_format_bold_plain(self):
        assert WeChatFormatter().format_bold("hi") == "hi"

    def test_format_italic_plain(self):
        assert WeChatFormatter().format_italic("hi") == "hi"

    def test_format_code_block_plain(self):
        assert WeChatFormatter().format_code_block("x=1") == "x=1"

    def test_format_link_plain(self):
        assert WeChatFormatter().format_link("txt", "http://a") == "txt(http://a)"


class TestTelegramFormatter:
    def test_format_result_escaped(self):
        f = TelegramFormatter()
        result = CommandResult(success=True, message="hello_world")
        text = f.format_result(result)
        assert "✅" in text
        assert "hello\\_world" in text

    def test_format_bold_escaped(self):
        assert TelegramFormatter().format_bold("a_b") == "*a\\_b*"

    def test_format_link_escaped(self):
        assert TelegramFormatter().format_link("a_b", "http://a") == "[a\\_b](http://a)"


class TestWeComFormatter:
    def test_format_result_success(self):
        f = WeComFormatter()
        result = CommandResult(success=True, message="ok")
        text = f.format_result(result)
        assert "✅" in text
        assert "**ok**" in text


class TestDingTalkFormatter:
    def test_format_result_success(self):
        f = DingTalkFormatter()
        result = CommandResult(success=True, message="ok")
        text = f.format_result(result)
        assert "✅" in text
        assert "**ok**" in text


class TestGetFormatter:
    def test_feishu(self):
        assert isinstance(get_formatter("feishu"), FeishuFormatter)

    def test_wecom(self):
        assert isinstance(get_formatter("wecom"), WeComFormatter)

    def test_dingtalk(self):
        assert isinstance(get_formatter("dingtalk"), DingTalkFormatter)

    def test_slack(self):
        assert isinstance(get_formatter("slack"), SlackFormatter)

    def test_telegram(self):
        assert isinstance(get_formatter("telegram"), TelegramFormatter)

    def test_discord(self):
        assert isinstance(get_formatter("discord"), DiscordFormatter)

    def test_wechat(self):
        assert isinstance(get_formatter("wechat"), WeChatFormatter)

    def test_unknown_defaults_to_feishu(self):
        assert isinstance(get_formatter("unknown_channel"), FeishuFormatter)


class TestCrossChannelFormatting:
    def test_same_result_different_format(self):
        result = CommandResult(success=True, message="Done")
        feishu_text = FeishuFormatter().format_result(result)
        slack_text = SlackFormatter().format_result(result)
        wechat_text = WeChatFormatter().format_result(result)
        discord_text = DiscordFormatter().format_result(result)

        assert "**Done**" in feishu_text
        assert "*Done*" in slack_text
        assert "Done" in wechat_text
        assert "**Done**" in discord_text
        assert "**" not in wechat_text

    def test_error_result_different_format(self):
        result = CommandResult(success=False, message="Failed")
        feishu_text = FeishuFormatter().format_result(result)
        wechat_text = WeChatFormatter().format_result(result)

        assert "❌" in feishu_text
        assert "❌" in wechat_text
        assert "**Failed**" in feishu_text
        assert "Failed" in wechat_text


class TestCommandRouting:
    def _make_manager(self, store=None):
        bus = MessageBus()
        if store is None:
            store = _make_store()
        return ChannelManager(bus=bus, store=store)

    def test_normalize_simple_command(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("new", "") == "new"

    def test_normalize_compound_claude_list(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("claude", "list") == "claude-list"

    def test_normalize_compound_task_list(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("task", "list") == "task-list"

    def test_normalize_compound_schedule_list(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("schedule", "list") == "schedule-list"

    def test_normalize_compound_skill_list(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("skill", "list") == "skill-list"

    def test_normalize_claude_with_session_id(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("claude", "session-123") == "claude"

    def test_normalize_no_args(self):
        mgr = self._make_manager()
        assert mgr._normalize_command("claude", "") == "claude"

    @pytest.mark.asyncio
    async def test_handle_command_routes_to_new(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-1"})
        mgr._get_client = MagicMock(return_value=mock_client)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/new", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1
        assert "✅" in published[0].text
        assert "New conversation started" in published[0].text

    @pytest.mark.asyncio
    async def test_handle_command_routes_to_help(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/help", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1
        assert "/new" in published[0].text

    @pytest.mark.asyncio
    async def test_handle_command_unknown(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/unknown", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1
        assert "❌" in published[0].text
        assert "未知命令" in published[0].text

    @pytest.mark.asyncio
    async def test_handle_command_compound_claude_list(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/claude list", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1
        assert "✅" in published[0].text

    @pytest.mark.asyncio
    async def test_handle_command_cross_channel_formatting(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-1"})
        mgr._get_client = MagicMock(return_value=mock_client)

        feishu_published = []
        wechat_published = []

        feishu_msg = _make_inbound("/new", channel_name="feishu")
        wechat_msg = _make_inbound("/new", channel_name="wechat")

        bus.subscribe_outbound(lambda msg: (
            feishu_published.append(msg) if msg.channel_name == "feishu" else wechat_published.append(msg)
        ))

        await mgr._handle_command(feishu_msg)
        await mgr._handle_command(wechat_msg)

        assert len(feishu_published) == 1
        assert len(wechat_published) == 1
        assert "**" in feishu_published[0].text
        assert "**" not in wechat_published[0].text

    @pytest.mark.asyncio
    async def test_handle_command_empty_text(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1
        assert "❌" in published[0].text

    @pytest.mark.asyncio
    async def test_handle_command_only_slash(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1

    @pytest.mark.asyncio
    async def test_handle_command_bootstrap(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-boot"})
        mgr._get_client = MagicMock(return_value=mock_client)

        with patch.object(mgr, "_handle_chat", new_callable=AsyncMock) as mock_chat:
            msg = _make_inbound("/bootstrap", channel_name="feishu")
            await mgr._handle_command(msg)
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args
            assert call_kwargs[1].get("extra_context", {}).get("is_bootstrap") is True

    @pytest.mark.asyncio
    async def test_handle_command_exception(self):
        bus = MessageBus()
        store = _make_store()
        mgr = ChannelManager(bus=bus, store=store)

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(side_effect=RuntimeError("boom"))
        mgr._get_client = MagicMock(return_value=mock_client)

        published = []
        bus.subscribe_outbound(lambda msg: published.append(msg))

        msg = _make_inbound("/new", channel_name="feishu")
        await mgr._handle_command(msg)

        assert len(published) == 1
        assert "❌" in published[0].text
        assert "命令执行失败" in published[0].text
