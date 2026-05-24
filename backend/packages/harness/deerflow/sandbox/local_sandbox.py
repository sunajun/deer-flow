import asyncio
import logging
import os
import time
from pathlib import Path

from deerflow.sandbox.base import (
    CommandResult,
    CrossPlatformSandboxProvider,
    SandboxInfo,
    VMState,
)
from deerflow.sandbox.strategy import SandboxStrategy

logger = logging.getLogger(__name__)

_COMMAND_BLOCKLIST: set[str] = {
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "chmod -R 777 /",
    "chown -R",
}

_ENV_WHITELIST: set[str] = {
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "TERM",
    "SHELL",
    "TMPDIR",
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "NODE_PATH",
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "no_proxy",
}

_AUDIT_LOG_MAX_ENTRIES = 10000


class AuditLog:
    def __init__(self, max_entries: int = _AUDIT_LOG_MAX_ENTRIES):
        self._entries: list[dict] = []
        self._max_entries = max_entries

    def record(self, sandbox_id: str, command: str, exit_code: int, cwd: str | None = None) -> None:
        entry = {
            "timestamp": time.time(),
            "sandbox_id": sandbox_id,
            "command": command[:500],
            "exit_code": exit_code,
            "cwd": cwd,
            "mode": "local",
        }
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def get_entries(self, sandbox_id: str | None = None, limit: int = 100) -> list[dict]:
        entries = self._entries
        if sandbox_id is not None:
            entries = [e for e in entries if e["sandbox_id"] == sandbox_id]
        return entries[-limit:]


_audit_log = AuditLog()


class LocalSandboxProvider(CrossPlatformSandboxProvider):
    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._sandboxes: dict[str, dict] = {}
        self._command_blocklist: set[str] = set(_COMMAND_BLOCKLIST)
        if config and "command_blocklist" in config:
            self._command_blocklist.update(config["command_blocklist"])
        self._allowed_work_dirs: list[str] | None = None
        if config and "allowed_work_dirs" in config:
            self._allowed_work_dirs = config["allowed_work_dirs"]

    async def is_available(self) -> bool:
        return True

    async def create_sandbox(self, thread_id: str, config: dict) -> str:
        sandbox_id = f"local-{thread_id}"
        workspace_dir = config.get("workspace_dir") or self._get_default_workspace(thread_id)
        os.makedirs(workspace_dir, exist_ok=True)
        self._sandboxes[sandbox_id] = {
            "thread_id": thread_id,
            "workspace_dir": workspace_dir,
            "state": VMState.STOPPED,
            "created_at": time.time(),
        }
        logger.info("本地沙箱已创建: %s (workspace=%s)", sandbox_id, workspace_dir)
        return sandbox_id

    async def start_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"沙箱不存在: {sandbox_id}")
        self._sandboxes[sandbox_id]["state"] = VMState.RUNNING
        logger.info("本地沙箱已启动: %s", sandbox_id)

    async def stop_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"沙箱不存在: {sandbox_id}")
        self._sandboxes[sandbox_id]["state"] = VMState.STOPPED
        logger.info("本地沙箱已停止: %s", sandbox_id)

    async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"沙箱不存在: {sandbox_id}")

        self._validate_command(command)

        sandbox_info = self._sandboxes[sandbox_id]
        work_dir = cwd or sandbox_info.get("workspace_dir", os.getcwd())

        if self._allowed_work_dirs is not None:
            self._validate_work_dir(work_dir)

        env = self._build_env()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stdout_bytes, stderr_bytes = b"", "命令执行超时".encode("utf-8")
                timed_out = True

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode if proc.returncode is not None else -1

            _audit_log.record(sandbox_id, command, exit_code, cwd=work_dir)

            return CommandResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
            )
        except Exception as e:
            _audit_log.record(sandbox_id, command, -1, cwd=work_dir)
            return CommandResult(exit_code=-1, stdout="", stderr=str(e), timed_out=False)

    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"沙箱不存在: {sandbox_id}")
        info = self._sandboxes[sandbox_id]
        return SandboxInfo(
            sandbox_id=sandbox_id,
            platform="local",
            strategy=SandboxStrategy.LOCAL,
            vm_state=info["state"],
            memory_mb=0,
            cpu_count=0,
            workspace_dir=info["workspace_dir"],
        )

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        if sandbox_id in self._sandboxes:
            del self._sandboxes[sandbox_id]
            logger.info("本地沙箱已销毁: %s", sandbox_id)

    def _validate_command(self, command: str) -> None:
        command_lower = command.lower().strip()
        for blocked in self._command_blocklist:
            if blocked.lower() in command_lower:
                raise PermissionError(f"命令被安全策略拦截: {blocked}")

    def _validate_work_dir(self, work_dir: str) -> None:
        resolved = str(Path(work_dir).resolve())
        for allowed in self._allowed_work_dirs:
            if resolved.startswith(str(Path(allowed).resolve())):
                return
        raise PermissionError(f"工作目录不在允许范围内: {work_dir}")

    def _build_env(self) -> dict[str, str]:
        env = {}
        for key in _ENV_WHITELIST:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
        return env

    def _get_default_workspace(self, thread_id: str) -> str:
        base = os.path.expanduser("~/.deerflow/workspace")
        return os.path.join(base, thread_id)

    @staticmethod
    def get_audit_log() -> AuditLog:
        return _audit_log
