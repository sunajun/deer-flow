from __future__ import annotations

import asyncio
import statistics
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.commands import get_command
from app.channels.commands.formatters import get_formatter
from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, InboundMessageType, MessageBus, OutboundMessage
from app.channels.store import ChannelStore


def _make_mgr(tmp_path, bus=None):
    if bus is None:
        bus = MessageBus()
    store = ChannelStore(path=tmp_path / "perf_store.json")
    mgr = ChannelManager(bus=bus, store=store)
    mgr._semaphore = asyncio.Semaphore(100)
    return mgr, bus, store


def _make_cmd_msg(text, channel_name="feishu", chat_id="perf-chat"):
    return InboundMessage(
        channel_name=channel_name,
        chat_id=chat_id,
        user_id="perf-user",
        text=text,
        msg_type=InboundMessageType.COMMAND,
    )


class TestCommandRoutingLatency:
    @pytest.mark.asyncio
    async def test_command_route_under_10ms(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)

        latencies = []
        commands = [
            "/status", "/help", "/task-list", "/schedule-list",
            "/skill-list", "/claude-list", "/clear",
        ]

        for cmd_text in commands:
            msg = _make_cmd_msg(cmd_text)

            published = []

            async def _capture(m):
                published.append(m)

            bus.subscribe_outbound(_capture)

            start = time.perf_counter()
            await mgr._handle_command(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        median_latency = statistics.median(latencies)
        assert median_latency < 10, f"Command routing median latency {median_latency:.2f}ms exceeds 10ms"


class TestFormattingLatency:
    def test_format_result_under_5ms(self):
        from app.channels.commands.base import CommandResult

        channels = ["feishu", "wecom", "dingtalk", "slack", "telegram", "discord", "wechat"]
        result = CommandResult(success=True, message="Test message with some content")

        latencies = []
        for _ in range(100):
            for channel in channels:
                formatter = get_formatter(channel)
                start = time.perf_counter()
                formatter.format_result(result)
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)

        median_latency = statistics.median(latencies)
        assert median_latency < 5, f"Formatting median latency {median_latency:.2f}ms exceeds 5ms"

    def test_format_table_under_5ms(self):
        channels = ["feishu", "wecom", "dingtalk", "slack", "telegram", "discord", "wechat"]
        headers = ["Name", "Status", "Created"]
        rows = [[f"task-{i}", "running", "2024-01-01"] for i in range(10)]

        latencies = []
        for _ in range(100):
            for channel in channels:
                formatter = get_formatter(channel)
                start = time.perf_counter()
                formatter.format_table(headers, rows)
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)

        median_latency = statistics.median(latencies)
        assert median_latency < 5, f"Table formatting median latency {median_latency:.2f}ms exceeds 5ms"


class TestFullPipelineLatency:
    @pytest.mark.asyncio
    async def test_full_pipeline_under_50ms(self, tmp_path):
        mgr, bus, store = _make_mgr(tmp_path)

        commands = ["/status", "/help", "/task-list", "/schedule-list", "/skill-list"]

        latencies = []
        for cmd_text in commands:
            msg = _make_cmd_msg(cmd_text)

            published = []

            async def _capture(m):
                published.append(m)

            bus.subscribe_outbound(_capture)

            start = time.perf_counter()
            await mgr._handle_command(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        median_latency = statistics.median(latencies)
        assert median_latency < 50, f"Full pipeline median latency {median_latency:.2f}ms exceeds 50ms"


class TestConcurrent100Commands:
    @pytest.mark.asyncio
    async def test_concurrent_100_commands(self, tmp_path):
        bus = MessageBus()
        store = ChannelStore(path=tmp_path / "perf_store.json")
        mgr = ChannelManager(bus=bus, store=store)
        mgr._semaphore = asyncio.Semaphore(100)

        published = []

        async def _capture(m):
            published.append(m)

        bus.subscribe_outbound(_capture)

        commands = [
            "/status", "/help", "/task-list", "/schedule-list", "/skill-list",
            "/claude-list", "/clear", "/lead",
        ]

        tasks = []
        for i in range(100):
            cmd = commands[i % len(commands)]
            msg = _make_cmd_msg(cmd, chat_id=f"perf-chat-{i}")
            tasks.append(mgr._handle_command(msg))

        start = time.perf_counter()
        await asyncio.gather(*tasks)
        total_ms = (time.perf_counter() - start) * 1000

        assert len(published) == 100, f"Expected 100 outbound messages, got {len(published)}"
        assert total_ms < 5000, f"100 concurrent commands took {total_ms:.0f}ms, exceeding 5000ms"
