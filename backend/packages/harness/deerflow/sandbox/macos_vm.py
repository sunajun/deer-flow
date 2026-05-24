import asyncio
import json
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


class MacOSVMProvider(CrossPlatformSandboxProvider):
    CLI_NAME = "DeerFlowSandboxCLI"

    def __init__(self, cli_path: str | None = None):
        self._cli_path_value = cli_path
        self._sandboxes: dict[str, dict] = {}

    def _cli_path(self) -> str:
        if self._cli_path_value:
            return self._cli_path_value
        if os.environ.get("DEERFLOW_SANDBOX_CLI"):
            return os.environ["DEERFLOW_SANDBOX_CLI"]
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, ".deerflow", "native", "DeerFlowSandboxCLI"),
            "/usr/local/bin/DeerFlowSandboxCLI",
            os.path.join(os.path.dirname(__file__), "..", "..", "resources", "native", "DeerFlowSandboxCLI"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return "DeerFlowSandboxCLI"

    async def _run_cli(self, action: str, args: dict | None = None) -> dict:
        cmd = [self._cli_path(), action]
        if args:
            cmd.extend(["--args", json.dumps(args)])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except FileNotFoundError:
            raise SandboxError(f"CLI 工具未找到: {self._cli_path()}")
        except asyncio.TimeoutError:
            raise SandboxError("CLI 调用超时")
        if proc.returncode != 0:
            raise SandboxError(f"CLI 错误: {stderr.decode('utf-8', errors='replace')}")
        try:
            return json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError:
            raise SandboxError(f"CLI 输出解析失败: {stdout.decode('utf-8', errors='replace')[:200]}")

    async def is_available(self) -> bool:
        try:
            cli = self._cli_path()
            if not os.path.isfile(cli) and not shutil.which(cli):
                return False
            result = await self._run_cli("detect-support")
            return result.get("success", False) and result.get("data", {}).get("isSupported", False)
        except Exception as e:
            logger.debug("macOS VM 检测失败: %s", e)
            return False

    async def create_sandbox(self, thread_id: str, config: dict) -> str:
        sandbox_id = f"macos-vm-{thread_id}"
        result = await self._run_cli("create-sandbox", {
            "id": sandbox_id,
            "config": config,
        })
        if not result.get("success"):
            raise SandboxError(f"创建 macOS VM 沙箱失败: {result.get('error', '未知错误')}")
        self._sandboxes[sandbox_id] = {
            "thread_id": thread_id,
            "state": VMState.STOPPED,
            "created_at": time.time(),
            "config": config,
        }
        return sandbox_id

    async def start_sandbox(self, sandbox_id: str) -> None:
        result = await self._run_cli("start-sandbox", {"id": sandbox_id})
        if not result.get("success"):
            raise SandboxError(f"启动 macOS VM 沙箱失败: {result.get('error', '未知错误')}")
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id]["state"] = VMState.RUNNING

    async def stop_sandbox(self, sandbox_id: str) -> None:
        result = await self._run_cli("stop-sandbox", {"id": sandbox_id})
        if not result.get("success"):
            logger.warning("停止 macOS VM 沙箱失败: %s", result.get("error"))
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id]["state"] = VMState.STOPPED

    async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
        args: dict = {"id": sandbox_id, "command": command, "timeout": timeout}
        if cwd:
            args["cwd"] = cwd
        result = await self._run_cli("execute", args)
        data = result.get("data", {})
        if data:
            return CommandResult(
                exit_code=data.get("exitCode", -1),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
                timed_out=data.get("timedOut", False),
            )
        return CommandResult(
            exit_code=-1,
            stdout="",
            stderr=result.get("error", "未知错误"),
        )

    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"沙箱不存在: {sandbox_id}")
        info = self._sandboxes[sandbox_id]
        config = info.get("config", {})
        return SandboxInfo(
            sandbox_id=sandbox_id,
            platform="macos",
            strategy=SandboxStrategy.SELECTIVE,
            vm_state=info["state"],
            memory_mb=config.get("memoryMB", 2048),
            cpu_count=config.get("cpuCount", 2),
            workspace_dir=config.get("workspacePath", ""),
        )

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        await self.stop_sandbox(sandbox_id)
        if sandbox_id in self._sandboxes:
            del self._sandboxes[sandbox_id]

    async def pause_sandbox(self, sandbox_id: str) -> None:
        result = await self._run_cli("pause-sandbox", {"id": sandbox_id})
        if not result.get("success"):
            raise SandboxError(f"暂停 macOS VM 沙箱失败: {result.get('error')}")
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id]["state"] = VMState.PAUSED

    async def resume_sandbox(self, sandbox_id: str) -> None:
        result = await self._run_cli("resume-sandbox", {"id": sandbox_id})
        if not result.get("success"):
            raise SandboxError(f"恢复 macOS VM 沙箱失败: {result.get('error')}")
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id]["state"] = VMState.RUNNING

    async def save_snapshot(self, sandbox_id: str, name: str) -> None:
        result = await self._run_cli("save-snapshot", {"id": sandbox_id, "name": name})
        if not result.get("success"):
            raise SandboxError(f"保存快照失败: {result.get('error')}")

    async def restore_snapshot(self, sandbox_id: str, name: str) -> None:
        result = await self._run_cli("restore-snapshot", {"id": sandbox_id, "name": name})
        if not result.get("success"):
            raise SandboxError(f"恢复快照失败: {result.get('error')}")

    async def list_snapshots(self, sandbox_id: str) -> list[str]:
        result = await self._run_cli("list-snapshots", {"id": sandbox_id})
        data = result.get("data", [])
        if isinstance(data, list):
            return [s.get("name", str(s)) if isinstance(s, dict) else str(s) for s in data]
        return []
