from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.channels.commands.base import CommandResult


class BaseFormatter(ABC):
    @abstractmethod
    def format_result(self, result: CommandResult) -> str: ...

    @abstractmethod
    def format_table(self, headers: list[str], rows: list[list[str]]) -> str: ...

    @abstractmethod
    def format_code_block(self, code: str, language: str = "") -> str: ...

    @abstractmethod
    def format_link(self, text: str, url: str) -> str: ...

    @abstractmethod
    def format_bold(self, text: str) -> str: ...

    @abstractmethod
    def format_italic(self, text: str) -> str: ...


class FeishuFormatter(BaseFormatter):
    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} {self.format_bold(result.message)}"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [self.format_bold(" | ".join(headers))]
        lines.append("--- | " + " | ".join(["---"] * len(headers)))
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return f"```{language}\n{code}\n```"

    def format_link(self, text: str, url: str) -> str:
        return f"[{text}]({url})"

    def format_bold(self, text: str) -> str:
        return f"**{text}**"

    def format_italic(self, text: str) -> str:
        return f"*{text}*"


class WeComFormatter(BaseFormatter):
    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} {self.format_bold(result.message)}"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [self.format_bold(" | ".join(headers))]
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return f"```\n{code}\n```"

    def format_link(self, text: str, url: str) -> str:
        return f"[{text}]({url})"

    def format_bold(self, text: str) -> str:
        return f"**{text}**"

    def format_italic(self, text: str) -> str:
        return f"*{text}*"


class DingTalkFormatter(BaseFormatter):
    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} {self.format_bold(result.message)}"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [self.format_bold(" | ".join(headers))]
        lines.append("--- | " + " | ".join(["---"] * len(headers)))
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return f"```{language}\n{code}\n```"

    def format_link(self, text: str, url: str) -> str:
        return f"[{text}]({url})"

    def format_bold(self, text: str) -> str:
        return f"**{text}**"

    def format_italic(self, text: str) -> str:
        return f"*{text}*"


class SlackFormatter(BaseFormatter):
    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} {self.format_bold(result.message)}"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [self.format_bold(" | ".join(headers))]
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return f"```{language}\n{code}\n```"

    def format_link(self, text: str, url: str) -> str:
        return f"<{url}|{text}>"

    def format_bold(self, text: str) -> str:
        return f"*{text}*"

    def format_italic(self, text: str) -> str:
        return f"_{text}_"


class TelegramFormatter(BaseFormatter):
    @staticmethod
    def _escape_md(text: str) -> str:
        for ch in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
            text = text.replace(ch, f"\\{ch}")
        return text

    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} *{self._escape_md(result.message)}*"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [self.format_bold(" | ".join(headers))]
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return f"```{language}\n{code}\n```"

    def format_link(self, text: str, url: str) -> str:
        return f"[{self._escape_md(text)}]({url})"

    def format_bold(self, text: str) -> str:
        return f"*{self._escape_md(text)}*"

    def format_italic(self, text: str) -> str:
        return f"_{self._escape_md(text)}_"


class DiscordFormatter(BaseFormatter):
    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} **{result.message}**"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [self.format_bold(" | ".join(headers))]
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return f"```{language}\n{code}\n```"

    def format_link(self, text: str, url: str) -> str:
        return f"[{text}]({url})"

    def format_bold(self, text: str) -> str:
        return f"**{text}**"

    def format_italic(self, text: str) -> str:
        return f"*{text}*"


class WeChatFormatter(BaseFormatter):
    def format_result(self, result: CommandResult) -> str:
        prefix = "✅" if result.success else "❌"
        return f"{prefix} {result.message}"

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [" | ".join(headers)]
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def format_code_block(self, code: str, language: str = "") -> str:
        return code

    def format_link(self, text: str, url: str) -> str:
        return f"{text}({url})"

    def format_bold(self, text: str) -> str:
        return text

    def format_italic(self, text: str) -> str:
        return text


_FORMATTERS: dict[str, type[BaseFormatter]] = {
    "feishu": FeishuFormatter,
    "wecom": WeComFormatter,
    "dingtalk": DingTalkFormatter,
    "slack": SlackFormatter,
    "telegram": TelegramFormatter,
    "discord": DiscordFormatter,
    "wechat": WeChatFormatter,
}

_DEFAULT_FORMATTER = FeishuFormatter


def get_formatter(channel: str) -> BaseFormatter:
    formatter_cls = _FORMATTERS.get(channel, _DEFAULT_FORMATTER)
    return formatter_cls()
