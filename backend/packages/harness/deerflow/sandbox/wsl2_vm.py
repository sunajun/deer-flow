import asyncio
import logging
import os
import shutil
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

_WSL2_DISTRO_NAME = "DeerFlow"
_WSL2_DEFAULT_IMAGE = "deerflow-sandbox.tar.gz"


class WSL2VMProvider(CrossPlatformSandboxProvider):
    def __init__(self, distro_name: str | None = None):
        self._distro_name = distro_name or _WSL2_DISTRO_NAME
        self._sandboxes: dict[str, dict] = {}

    async def _run_wsl(self, command: str, distro: str | None = None, timeout: int = 60) -> tuple[int, str, str]:
        distro = distro or self._distro_name
        full_cmd = ["wsl", "-d", distro, "--", "bash", "-c", command]
        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError:
            return -1, "", "wsl 命令未找到"
        except asyncio.TimeoutError:
            return -1, "", "WSL2 命令执行超时"

    async def _wsl_exists(self) -> bool:
        return shutil.which("wsl") is not None

    async def _distro_installed(self) -> bool:
        if not await self._wsl_exists():
            return False
        proc = await asyncio.create_subprocess_exec(
            "wsl", "-l", "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            output = stdout.decode("utf-8", errors="replace")
            return self._distro_name in output
        except Exception:
            return False

    async def is_available(self) -> bool:
        try:
            if not await self._wsl_exists():
                return False
            proc = await asyncio.create_subprocess_exec(
                "wsl", "--status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as e:
            logger.debug("WSL2 检测失败: %s", e)
            return False

    async def create_sandbox(self, thread_id: str, config: dict) -> str:
        sandbox_id = f"wsl2-{thread_id}"

        if not await self._distro_installed():
            image_path = config.get("image_path", _WSL2_DEFAULT_IMAGE)
            if os.path.isfile(image_path):
                proc = await asyncio.create_subprocess_exec(
                    "wsl", "--import", self._distro_name, "$HOME/.deerflow/wsl2", image_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                if proc.returncode != 0:
                    raise SandboxError(f"导入 WSL2 发行版失败: {self._distro_name}")
            else:
                raise SandboxError(f"WSL2 发行版未安装且未找到镜像: {image_path}")

        self._sandboxes[sandbox_id] = {
            "thread_id": thread_id,
            "state": VMState.STOPPED,
            "created_at": time.time(),
            "config": config,
        }
        return sandbox_id

    async def start_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"沙箱不存在: {sandbox_id}")
        exit_code, _, stderr = await self._run_wsl("echo ready")
        if exit_code != 0:
            raise SandboxError(f"WSL2 沙箱启动失败: {stderr}")
        self._sandboxes[sandbox_id]["state"] = VMState.RUNNING

    async def stop_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id]["state"] = VMState.STOPPED

    async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"沙箱不存在: {sandbox_id}")

        full_command = command
        if cwd:
            full_command = f"cd {cwd} && {command}"

        exit_code, stdout, stderr = await self._run_wsl(full_command, timeout=timeout)
        return CommandResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out="超时" in stderr,
        )

    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"沙箱不存在: {sandbox_id}")
        info = self._sandboxes[sandbox_id]
        config = info.get("config", {})
        return SandboxInfo(
            sandbox_id=sandbox_id,
            platform="windows",
            strategy=SandboxStrategy.SELECTIVE,
            vm_state=info["state"],
            memory_mb=config.get("memory_mb", 2048),
            cpu_count=config.get("cpu_count", 2),
            workspace_dir=config.get("workspace_dir", ""),
        )

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id in self._sandboxes:
            del self._sandboxes[sandbox_id]

    async def upload_file(self, sandbox_id: str, local_path: str, remote_path: str) -> None:
        if not await self._wsl_exists():
            raise SandboxError("WSL2 不可用")
        wsl_path = remote_path.replace("\\", "/")
        proc = await asyncio.create_subprocess_exec(
            "wsl", "-d", self._distro_name, "--", "cp", local_path, wsl_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise SandboxError(f"上传文件失败: {stderr.decode('utf-8', errors='replace')}")

    async def download_file(self, sandbox_id: str, remote_path: str, local_path: str) -> None:
        if not await self._wsl_exists():
            raise SandboxError("WSL2 不可用")
        proc = await asyncio.create_subprocess_exec(
            "wsl", "-d", self._distro_name, "--", "cp", remote_path, local_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise SandboxError(f"下载文件失败: {stderr.decode('utf-8', errors='replace')}")
