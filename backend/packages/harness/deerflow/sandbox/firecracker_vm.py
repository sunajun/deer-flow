import asyncio
import logging
import os
import time

from deerflow.sandbox.base import (
    CommandResult,
    CrossPlatformSandboxProvider,
    SandboxInfo,
    VMState,
)
from deerflow.sandbox.exceptions import SandboxError
from deerflow.sandbox.strategy import SandboxStrategy

logger = logging.getLogger(__name__)

_DEFAULT_KERNEL_PATH = "resources/vm-images/vmlinux"
_DEFAULT_ROOTFS_PATH = "resources/vm-images/rootfs.ext4"
_DEFAULT_VCPU = 2
_DEFAULT_MEM_MIB = 2048


class FirecrackerVMProvider(CrossPlatformSandboxProvider):
    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._sandboxes: dict[str, dict] = {}
        self._vm_instances: dict[str, object] = {}

    def _load_vm_config(self) -> dict:
        return {
            "kernel_path": self._config.get("kernel_path", _DEFAULT_KERNEL_PATH),
            "rootfs_path": self._config.get("rootfs_path", _DEFAULT_ROOTFS_PATH),
            "vcpu_count": self._config.get("vcpu_count", _DEFAULT_VCPU),
            "mem_size_mib": self._config.get("mem_size_mib", _DEFAULT_MEM_MIB),
            "file_sharing": self._config.get("file_sharing", "scp"),
        }

    async def is_available(self) -> bool:
        try:
            if not os.path.exists("/dev/kvm"):
                return False
            if not os.access("/dev/kvm", os.R_OK | os.W_OK):
                return False
            from shutil import which

            fc_binary = self._config.get("firecracker_binary", "firecracker")
            if which(fc_binary) is None:
                return False
            return True
        except Exception as e:
            logger.debug("Firecracker 检测失败: %s", e)
            return False

    async def create_sandbox(self, thread_id: str, config: dict) -> str:
        sandbox_id = f"fc-{thread_id}"
        vm_config = self._load_vm_config()
        vm_config.update(config)

        try:
            from deerflow.sandbox.firecracker.firecracker_vm import FirecrackerVM

            workspace_dir = config.get("workspace_dir") or os.path.join(
                os.path.expanduser("~"), ".deerflow", "workspace", thread_id
            )
            os.makedirs(workspace_dir, exist_ok=True)

            vm = FirecrackerVM(
                kernel_path=vm_config["kernel_path"],
                rootfs_path=vm_config["rootfs_path"],
                workspace_dir=workspace_dir,
                vcpu_count=vm_config["vcpu_count"],
                mem_size_mib=vm_config["mem_size_mib"],
                file_sharing=vm_config["file_sharing"],
            )

            self._vm_instances[sandbox_id] = vm
            self._sandboxes[sandbox_id] = {
                "thread_id": thread_id,
                "state": VMState.STOPPED,
                "created_at": time.time(),
                "config": vm_config,
            }
            return sandbox_id
        except ImportError:
            raise SandboxError("FirecrackerVM 模块不可用")

    async def start_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"沙箱不存在: {sandbox_id}")

        vm = self._vm_instances.get(sandbox_id)
        if vm is None:
            raise SandboxError(f"VM 实例不存在: {sandbox_id}")

        try:
            await vm.start()
            self._sandboxes[sandbox_id]["state"] = VMState.RUNNING
        except Exception as e:
            self._sandboxes[sandbox_id]["state"] = VMState.ERROR
            raise SandboxError(f"Firecracker VM 启动失败: {e}")

    async def stop_sandbox(self, sandbox_id: str) -> None:
        vm = self._vm_instances.get(sandbox_id)
        if vm is not None:
            try:
                await vm.stop()
            except Exception as e:
                logger.warning("停止 Firecracker VM 失败: %s", e)
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id]["state"] = VMState.STOPPED

    async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
        vm = self._vm_instances.get(sandbox_id)
        if vm is None:
            raise SandboxError(f"VM 实例不存在: {sandbox_id}")

        full_command = command
        if cwd:
            full_command = f"cd {cwd} && {command}"

        try:
            result = await asyncio.wait_for(vm.execute(full_command), timeout=timeout)
            return CommandResult(
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=False,
            )
        except asyncio.TimeoutError:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="命令执行超时",
                timed_out=True,
            )

    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"沙箱不存在: {sandbox_id}")
        info = self._sandboxes[sandbox_id]
        config = info.get("config", {})
        return SandboxInfo(
            sandbox_id=sandbox_id,
            platform="linux",
            strategy=SandboxStrategy.SELECTIVE,
            vm_state=info["state"],
            memory_mb=config.get("mem_size_mib", _DEFAULT_MEM_MIB),
            cpu_count=config.get("vcpu_count", _DEFAULT_VCPU),
            workspace_dir=config.get("workspace_dir", ""),
        )

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        await self.stop_sandbox(sandbox_id)
        self._vm_instances.pop(sandbox_id, None)
        self._sandboxes.pop(sandbox_id, None)

    async def pause_sandbox(self, sandbox_id: str) -> None:
        vm = self._vm_instances.get(sandbox_id)
        if vm is None:
            raise SandboxError(f"VM 实例不存在: {sandbox_id}")
        if hasattr(vm, "pause"):
            await vm.pause()
            if sandbox_id in self._sandboxes:
                self._sandboxes[sandbox_id]["state"] = VMState.PAUSED
        else:
            raise NotImplementedError("Firecracker VM 不支持暂停")

    async def resume_sandbox(self, sandbox_id: str) -> None:
        vm = self._vm_instances.get(sandbox_id)
        if vm is None:
            raise SandboxError(f"VM 实例不存在: {sandbox_id}")
        if hasattr(vm, "resume"):
            await vm.resume()
            if sandbox_id in self._sandboxes:
                self._sandboxes[sandbox_id]["state"] = VMState.RUNNING
        else:
            raise NotImplementedError("Firecracker VM 不支持恢复")
