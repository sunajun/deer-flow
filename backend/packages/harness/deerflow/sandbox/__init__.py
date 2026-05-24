import logging

from .sandbox import Sandbox
from .sandbox_provider import SandboxProvider, get_sandbox_provider
from .base import CrossPlatformSandboxProvider, CommandResult, SandboxInfo, VMState
from .strategy import SandboxRouter, SandboxStrategy
from .fallback import FallbackManager

logger = logging.getLogger(__name__)

__all__ = [
    "Sandbox",
    "SandboxProvider",
    "get_sandbox_provider",
    "CrossPlatformSandboxProvider",
    "CommandResult",
    "SandboxInfo",
    "VMState",
    "SandboxRouter",
    "SandboxStrategy",
    "FallbackManager",
    "get_sandbox_manager",
]

_sandbox_manager: FallbackManager | None = None


async def get_sandbox_manager() -> FallbackManager:
    global _sandbox_manager
    if _sandbox_manager is None:
        try:
            from deerflow.config import get_app_config
            config = get_app_config()
            config_dict = config.model_dump() if hasattr(config, "model_dump") else {}
        except Exception:
            config_dict = {}
        _sandbox_manager = FallbackManager(config_dict)
        await _sandbox_manager.initialize()
    return _sandbox_manager


def reset_sandbox_manager() -> None:
    global _sandbox_manager
    _sandbox_manager = None
