import logging
import platform as pf

from deerflow.sandbox.base import (
    CommandResult,
    CrossPlatformSandboxProvider,
    SandboxInfo,
    VMState,
)
from deerflow.sandbox.strategy import SandboxStrategy

logger = logging.getLogger(__name__)


class VMSandboxProvider(CrossPlatformSandboxProvider):
    def __init__(self, platform: str = "auto"):
        self.platform = self._detect_platform() if platform == "auto" else platform
        self._provider: CrossPlatformSandboxProvider | None = None
        self._vm_pool: dict[str, CrossPlatformSandboxProvider] = {}

    def _detect_platform(self) -> str:
        system = pf.system().lower()
        if system == "darwin":
            return "macos"
        elif system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        raise RuntimeError(f"不支持的平台: {system}")

    async def _get_provider(self) -> CrossPlatformSandboxProvider:
        if self._provider is not None:
            return self._provider
        if self.platform == "macos":
            from deerflow.sandbox.macos_vm import MacOSVMProvider

            self._provider = MacOSVMProvider()
        elif self.platform == "windows":
            from deerflow.sandbox.wsl2_vm import WSL2VMProvider

            self._provider = WSL2VMProvider()
        elif self.platform == "linux":
            from deerflow.sandbox.firecracker_vm import FirecrackerVMProvider

            self._provider = FirecrackerVMProvider()
        else:
            raise RuntimeError(f"不支持的平台: {self.platform}")
        return self._provider

    async def is_available(self) -> bool:
        try:
            provider = await self._get_provider()
            return await provider.is_available()
        except (ImportError, RuntimeError) as e:
            logger.warning("VM 沙箱提供者不可用: %s", e)
            return False

    async def create_sandbox(self, thread_id: str, config: dict) -> str:
        provider = await self._get_provider()
        if not await provider.is_available():
            logger.warning("VM 沙箱不可用 (platform=%s)，降级到本地模式", self.platform)
            from deerflow.sandbox.local_sandbox import LocalSandboxProvider

            local_provider = LocalSandboxProvider()
            return await local_provider.create_sandbox(thread_id, config)
        return await provider.create_sandbox(thread_id, config)

    async def start_sandbox(self, sandbox_id: str) -> None:
        provider = await self._get_provider()
        await provider.start_sandbox(sandbox_id)

    async def stop_sandbox(self, sandbox_id: str) -> None:
        provider = await self._get_provider()
        await provider.stop_sandbox(sandbox_id)

    async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
        provider = await self._get_provider()
        return await provider.execute(sandbox_id, command, timeout, cwd)

    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        provider = await self._get_provider()
        return await provider.get_sandbox_info(sandbox_id)

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        provider = await self._get_provider()
        await provider.destroy_sandbox(sandbox_id)

    async def pause_sandbox(self, sandbox_id: str) -> None:
        provider = await self._get_provider()
        await provider.pause_sandbox(sandbox_id)

    async def resume_sandbox(self, sandbox_id: str) -> None:
        provider = await self._get_provider()
        await provider.resume_sandbox(sandbox_id)

    async def save_snapshot(self, sandbox_id: str, name: str) -> None:
        provider = await self._get_provider()
        await provider.save_snapshot(sandbox_id, name)

    async def restore_snapshot(self, sandbox_id: str, name: str) -> None:
        provider = await self._get_provider()
        await provider.restore_snapshot(sandbox_id, name)

    async def list_snapshots(self, sandbox_id: str) -> list[str]:
        provider = await self._get_provider()
        return await provider.list_snapshots(sandbox_id)

    async def upload_file(self, sandbox_id: str, local_path: str, remote_path: str) -> None:
        provider = await self._get_provider()
        await provider.upload_file(sandbox_id, local_path, remote_path)

    async def download_file(self, sandbox_id: str, remote_path: str, local_path: str) -> None:
        provider = await self._get_provider()
        await provider.download_file(sandbox_id, remote_path, local_path)
