from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class CommandResult(BaseModel):
    success: bool
    message: str
    data: dict | None = None
    format_hint: str = "markdown"


class BaseCommand(ABC):
    name: str
    aliases: list[str]
    description: str
    usage: str

    @abstractmethod
    async def execute(self, message: dict, args: str) -> CommandResult: ...

    def match(self, cmd_name: str) -> bool:
        return cmd_name == self.name or cmd_name in self.aliases

    def get_help(self) -> str:
        return f"`/{self.name}` — {self.description}\n用法: {self.usage}"
