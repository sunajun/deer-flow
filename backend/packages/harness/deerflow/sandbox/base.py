from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from deerflow.sandbox.strategy import SandboxStrategy


class VMState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass
class SandboxInfo:
    sandbox_id: str
    platform: str
    strategy: SandboxStrategy
    vm_state: VMState
    memory_mb: int
    cpu_count: int
    workspace_dir: str
    extra: dict = field(default_factory=dict)


class CrossPlatformSandboxProvider(ABC):
    @abstractmethod
    async def create_sandbox(self, thread_id: str, config: dict) -> str: ...

    @abstractmethod
    async def start_sandbox(self, sandbox_id: str) -> None: ...

    @abstractmethod
    async def stop_sandbox(self, sandbox_id: str) -> None: ...

    @abstractmethod
    async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult: ...

    @abstractmethod
    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo: ...

    @abstractmethod
    async def destroy_sandbox(self, sandbox_id: str) -> None: ...

    @abstractmethod
    async def is_available(self) -> bool: ...

    async def pause_sandbox(self, sandbox_id: str) -> None:
        raise NotImplementedError("暂停功能在此沙箱提供者上不可用")

    async def resume_sandbox(self, sandbox_id: str) -> None:
        raise NotImplementedError("恢复功能在此沙箱提供者上不可用")

    async def save_snapshot(self, sandbox_id: str, name: str) -> None:
        raise NotImplementedError("快照功能在此沙箱提供者上不可用")

    async def restore_snapshot(self, sandbox_id: str, name: str) -> None:
        raise NotImplementedError("快照功能在此沙箱提供者上不可用")

    async def list_snapshots(self, sandbox_id: str) -> list[str]:
        return []

    async def upload_file(self, sandbox_id: str, local_path: str, remote_path: str) -> None:
        raise NotImplementedError

    async def download_file(self, sandbox_id: str, remote_path: str, local_path: str) -> None:
        raise NotImplementedError
