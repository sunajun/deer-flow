from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.commands.formatters import (
    DingTalkFormatter,
    DiscordFormatter,
    FeishuFormatter,
    SlackFormatter,
    TelegramFormatter,
    WeChatFormatter,
    WeComFormatter,
)
from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, InboundMessageType, MessageBus, OutboundMessage
from app.channels.store import ChannelStore


async def _run_e2e_command(
    channel_name: str,
    cmd_text: str,
    store: ChannelStore,
    bus: MessageBus,
    *,
    chat_id: str = "e2e-chat",
    user_id: str = "e2e-user",
    mock_client=None,
) -> OutboundMessage:
    mgr = ChannelManager(bus=bus, store=store)
    mgr._semaphore = __import__("asyncio").Semaphore(5)

    if mock_client is not None:
        mgr._get_client = MagicMock(return_value=mock_client)

    msg = InboundMessage(
        channel_name=channel_name,
        chat_id=chat_id,
        user_id=user_id,
        text=cmd_text,
        msg_type=InboundMessageType.COMMAND,
    )

    published = []

    async def _capture(m):
        published.append(m)

    bus.subscribe_outbound(_capture)

    await mgr._handle_command(msg)

    assert len(published) >= 1, f"Expected at least 1 outbound message, got {len(published)}"
    return published[0]


class TestE2EFeishuNewConversation:
    @pytest.mark.asyncio
    async def test_feishu_new_conversation(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-feishu-new"})

        outbound = await _run_e2e_command(
            "feishu", "/new 测试对话", store, bus, mock_client=mock_client
        )

        assert outbound.channel_name == "feishu"
        assert outbound.chat_id == "e2e-chat"
        assert "✅" in outbound.text
        assert "New conversation started" in outbound.text
        assert "**" in outbound.text

        thread_id = store.get_thread_id("feishu", "e2e-chat")
        assert thread_id == "t-feishu-new"


class TestE2ESlackClaude:
    @pytest.mark.asyncio
    async def test_slack_claude_session(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        outbound = await _run_e2e_command(
            "slack", "/claude 写一个函数", store, bus
        )

        assert outbound.channel_name == "slack"
        assert outbound.chat_id == "e2e-chat"
        assert "✅" in outbound.text
        assert "*Claude Code session*" in outbound.text or "Claude Code" in outbound.text


class TestE2EWeComTaskList:
    @pytest.mark.asyncio
    async def test_wecom_task_list(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        outbound = await _run_e2e_command(
            "wecom", "/task-list", store, bus
        )

        assert outbound.channel_name == "wecom"
        assert outbound.chat_id == "e2e-chat"
        assert "✅" in outbound.text
        assert "**" in outbound.text


class TestE2EDingTalkScheduleCreate:
    @pytest.mark.asyncio
    async def test_dingtalk_schedule_create(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        outbound = await _run_e2e_command(
            "dingtalk",
            '/schedule-create "0 9 * * 1-5" 每日站会',
            store,
            bus,
        )

        assert outbound.channel_name == "dingtalk"
        assert outbound.chat_id == "e2e-chat"
        assert "✅" in outbound.text
        assert "0 9 * * 1-5" in outbound.text
        assert "每日站会" in outbound.text


class TestE2ETelegramSkillInstall:
    @pytest.mark.asyncio
    async def test_telegram_skill_install(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        outbound = await _run_e2e_command(
            "telegram", "/skill-install search-skill", store, bus
        )

        assert outbound.channel_name == "telegram"
        assert outbound.chat_id == "e2e-chat"
        assert "✅" in outbound.text
        assert "search" in outbound.text and "skill" in outbound.text


class TestE2EDiscordHelp:
    @pytest.mark.asyncio
    async def test_discord_help(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        outbound = await _run_e2e_command(
            "discord", "/help", store, bus
        )

        assert outbound.channel_name == "discord"
        assert outbound.chat_id == "e2e-chat"
        assert "/new" in outbound.text
        assert "/help" in outbound.text


class TestE2EOutboundMessageFields:
    @pytest.mark.asyncio
    async def test_outbound_fields_correct(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        mock_client = MagicMock()
        mock_client.threads.create = AsyncMock(return_value={"thread_id": "t-fields"})

        outbound = await _run_e2e_command(
            "feishu", "/new", store, bus,
            chat_id="chat-fields",
            user_id="user-fields",
            mock_client=mock_client,
        )

        assert outbound.channel_name == "feishu"
        assert outbound.chat_id == "chat-fields"
        assert isinstance(outbound.text, str)
        assert len(outbound.text) > 0
        assert outbound.is_final is True

    @pytest.mark.asyncio
    async def test_bus_publish_outbound_called(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "e2e_store.json")

        call_count = 0

        async def _counter(msg):
            nonlocal call_count
            call_count += 1

        bus.subscribe_outbound(_counter)

        mgr = ChannelManager(bus=bus, store=store)
        mgr._semaphore = __import__("asyncio").Semaphore(5)

        msg = InboundMessage(
            channel_name="feishu",
            chat_id="chat-counter",
            user_id="user-counter",
            text="/status",
            msg_type=InboundMessageType.COMMAND,
        )

        await mgr._handle_command(msg)

        assert call_count == 1
