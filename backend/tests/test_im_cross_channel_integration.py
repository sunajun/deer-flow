from __future__ import annotations

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
from app.channels.message_bus import OutboundMessage

ALL_CHANNELS = ["feishu", "wecom", "dingtalk", "slack", "telegram", "discord", "wechat"]


class TestStatusCommandCrossChannel:
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    @pytest.mark.asyncio
    async def test_status_output_format(
        self,
        mock_channel_manager,
        sample_inbound_message,
        channel,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/status", channel_name=channel)
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert outbound.channel_name == channel
        assert "✅" in outbound.text or "No active conversation" in outbound.text

    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    def test_status_formatter_produces_output(self, channel):
        formatter = get_formatter(channel)
        result = CommandResult(success=True, message="Active thread: t-123")
        text = formatter.format_result(result)
        assert "✅" in text
        assert "t" in text and "123" in text


class TestHelpCommandCrossChannel:
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    @pytest.mark.asyncio
    async def test_help_output_format(
        self,
        mock_channel_manager,
        sample_inbound_message,
        channel,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/help", channel_name=channel)
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert outbound.channel_name == channel
        assert "/new" in outbound.text
        assert "/help" in outbound.text

    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    def test_help_formatter_produces_output(self, channel):
        formatter = get_formatter(channel)
        result = CommandResult(success=True, message="**可用命令**\n\n/new — 开始新对话")
        text = formatter.format_result(result)
        assert "可用命令" in text


class TestTaskListCrossChannel:
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    @pytest.mark.asyncio
    async def test_task_list_output_format(
        self,
        mock_channel_manager,
        sample_inbound_message,
        channel,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/task-list", channel_name=channel)
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        outbound = published[0]
        assert outbound.channel_name == channel

    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    def test_table_formatting_per_channel(self, channel):
        formatter = get_formatter(channel)
        headers = ["Task", "Status", "Created"]
        rows = [["task-1", "running", "2024-01-01"]]
        text = formatter.format_table(headers, rows)
        assert "task-1" in text
        assert "running" in text

        if channel == "wechat":
            assert "**" not in text
        else:
            assert "Task" in text or "**Task" in text


class TestClaudeResultCrossChannel:
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    def test_code_block_formatting(self, channel):
        formatter = get_formatter(channel)
        code = "def hello():\n    print('hi')"
        text = formatter.format_code_block(code, "python")

        if channel == "wechat":
            assert "def hello" in text
            assert "```" not in text
        else:
            assert "```" in text
            assert "def hello" in text

    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    def test_claude_result_formatting(self, channel):
        formatter = get_formatter(channel)
        result = CommandResult(
            success=True,
            message="Creating new Claude Code session...",
            data={"action": "create"},
        )
        text = formatter.format_result(result)
        assert "✅" in text
        assert "Claude Code session" in text


class TestFormatterChannelSpecifics:
    def test_feishu_uses_markdown_bold(self):
        f = FeishuFormatter()
        result = CommandResult(success=True, message="Done")
        assert "**Done**" in f.format_result(result)

    def test_slack_uses_star_bold(self):
        f = SlackFormatter()
        result = CommandResult(success=True, message="Done")
        assert "*Done*" in f.format_result(result)

    def test_discord_uses_double_star_bold(self):
        f = DiscordFormatter()
        result = CommandResult(success=True, message="Done")
        assert "**Done**" in f.format_result(result)

    def test_wechat_no_markdown(self):
        f = WeChatFormatter()
        result = CommandResult(success=True, message="Done")
        text = f.format_result(result)
        assert "Done" in text
        assert "**" not in text

    def test_telegram_escapes_special_chars(self):
        f = TelegramFormatter()
        result = CommandResult(success=True, message="hello_world")
        text = f.format_result(result)
        assert "hello\\_world" in text

    def test_wecom_uses_markdown_bold(self):
        f = WeComFormatter()
        result = CommandResult(success=True, message="Done")
        assert "**Done**" in f.format_result(result)

    def test_dingtalk_uses_markdown_bold(self):
        f = DingTalkFormatter()
        result = CommandResult(success=True, message="Done")
        assert "**Done**" in f.format_result(result)

    def test_slack_link_format(self):
        f = SlackFormatter()
        assert f.format_link("text", "http://example.com") == "<http://example.com|text>"

    def test_feishu_link_format(self):
        f = FeishuFormatter()
        assert f.format_link("text", "http://example.com") == "[text](http://example.com)"

    def test_wechat_link_format(self):
        f = WeChatFormatter()
        assert f.format_link("text", "http://example.com") == "text(http://example.com)"


class TestCrossChannelErrorFormatting:
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    def test_error_result_format(self, channel):
        formatter = get_formatter(channel)
        result = CommandResult(success=False, message="Something went wrong")
        text = formatter.format_result(result)
        assert "❌" in text
        assert "Something went wrong" in text

    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    @pytest.mark.asyncio
    async def test_unknown_command_per_channel(
        self,
        mock_channel_manager,
        sample_inbound_message,
        channel,
    ):
        bus = mock_channel_manager.bus
        mgr = mock_channel_manager

        msg = sample_inbound_message(text="/unknown", channel_name=channel)
        await mgr._handle_command(msg)

        published = bus._test_published_outbound
        assert len(published) == 1
        assert "❌" in published[0].text
        assert "未知命令" in published[0].text
