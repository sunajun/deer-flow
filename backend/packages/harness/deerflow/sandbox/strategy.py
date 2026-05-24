import logging
from enum import Enum

logger = logging.getLogger(__name__)


class SandboxStrategy(str, Enum):
    STRICT = "strict"
    SELECTIVE = "selective"
    LOCAL = "local"


SANDBOX_REQUIRED_TOOLS: dict[str, bool] = {
    "bash": True,
    "write_file": True,
    "str_replace": True,
    "python_exec": True,
    "npm_install": True,
    "pip_install": True,
    "git_checkout": True,
    "chat": False,
    "clarify": False,
    "view_image": False,
    "tavily_search": False,
    "jina_reader": False,
    "read_file": False,
    "ls": False,
    "glob": False,
    "grep": False,
}


class SandboxRouter:
    def __init__(self, strategy: SandboxStrategy = SandboxStrategy.SELECTIVE):
        self.strategy = strategy

    def should_use_sandbox(self, tool_name: str) -> bool:
        if self.strategy == SandboxStrategy.STRICT:
            return True
        elif self.strategy == SandboxStrategy.LOCAL:
            return False
        return SANDBOX_REQUIRED_TOOLS.get(tool_name, True)

    def get_execution_target(self, tool_name: str) -> str:
        return "vm" if self.should_use_sandbox(tool_name) else "local"

    @classmethod
    def from_config(cls, config: dict) -> "SandboxRouter":
        strategy_str = config.get("sandbox", {}).get("strategy", "selective")
        strategy = SandboxStrategy(strategy_str)
        return cls(strategy=strategy)

    def set_strategy(self, strategy: SandboxStrategy) -> None:
        old = self.strategy
        self.strategy = strategy
        logger.info("沙箱策略变更: %s -> %s", old.value, strategy.value)
