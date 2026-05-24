import asyncio
import logging
import subprocess
import time

from deerflow.sandbox.exceptions import SandboxError
from deerflow.sandbox.firecracker.firecracker_vm import CommandResult
from deerflow.sandbox.sandbox import Sandbox
from deerflow.sandbox.sandbox_provider import SandboxProvider
from deerflow.sandbox.search import GrepMatch

logger = logging.getLogger(__name__)


class ContainerSandboxProvider(SandboxProvider):
    container_cmd: str = "docker"

    def __init__(self, image: str | None = None):
        self._image = image or "ubuntu:24.04"
        self._containers: dict[str, dict] = {}

    async def is_available(self) -> bool:
        try:
            result = await asyncio.create_subprocess_exec(
                self.container_cmd, "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.wait()
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def acquire(self, thread_id: str | None = None) -> str:
        sandbox_id = f"fc-fallback-{self.container_cmd}-{thread_id or 'default'}"
        if sandbox_id in self._containers:
            return sandbox_id

        container_name = f"deerflow-{self.container_cmd}-{thread_id or 'default'}"
        try:
            result = subprocess.run(
                [
                    self.container_cmd, "run", "-d",
                    "--name", container_name,
                    "--label", "deerflow-sandbox=true",
                    self._image,
                    "sleep", "infinity",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise SandboxError(f"Failed to start {self.container_cmd} container: {result.stderr}")

            container_id = result.stdout.strip()[:12]
            self._containers[sandbox_id] = {
                "container_id": container_id,
                "container_name": container_name,
                "created_at": time.time(),
            }
            return sandbox_id
        except subprocess.TimeoutExpired:
            raise SandboxError(f"Timeout starting {self.container_cmd} container")
        except FileNotFoundError:
            raise SandboxError(f"{self.container_cmd} is not installed")

    def get(self, sandbox_id: str) -> Sandbox | None:
        if sandbox_id not in self._containers:
            return None
        info = self._containers[sandbox_id]
        return ContainerSandbox(
            id=sandbox_id,
            container_id=info["container_id"],
            container_cmd=self.container_cmd,
        )

    def release(self, sandbox_id: str) -> None:
        info = self._containers.pop(sandbox_id, None)
        if info is None:
            return
        try:
            subprocess.run(
                [self.container_cmd, "rm", "-f", info["container_name"]],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            logger.warning("Failed to remove container %s: %s", info["container_name"], e)

    def reset(self) -> None:
        for sandbox_id in list(self._containers.keys()):
            self.release(sandbox_id)


class DockerSandboxProvider(ContainerSandboxProvider):
    container_cmd: str = "docker"


class PodmanSandboxProvider(ContainerSandboxProvider):
    container_cmd: str = "podman"


class ContainerSandbox(Sandbox):
    def __init__(self, id: str, container_id: str, container_cmd: str = "docker"):
        super().__init__(id)
        self._container_id = container_id
        self._container_cmd = container_cmd

    def _exec(self, command: str, timeout: int = 300) -> CommandResult:
        try:
            result = subprocess.run(
                [self._container_cmd, "exec", self._container_id, "bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        except subprocess.TimeoutExpired:
            return CommandResult(exit_code=-1, stdout="", stderr=f"Command timed out after {timeout}s")
        except FileNotFoundError:
            raise SandboxError(f"{self._container_cmd} is not installed")

    def execute_command(self, command: str) -> str:
        result = self._exec(command)
        output = result.stdout
        if result.stderr:
            output += f"\nStd Error:\n{result.stderr}" if output else result.stderr
        if result.exit_code != 0:
            output += f"\nExit Code: {result.exit_code}"
        return output or "(no output)"

    def read_file(self, path: str) -> str:
        result = self._exec(f"cat {path}")
        if result.exit_code != 0:
            raise OSError(f"Failed to read file {path}: {result.stderr}")
        return result.stdout

    def download_file(self, path: str) -> bytes:
        try:
            result = subprocess.run(
                [self._container_cmd, "cp", f"{self._container_id}:{path}", "-"],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise OSError(f"Failed to download file {path}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise OSError(f"Timeout downloading file {path}")

    def list_dir(self, path: str, max_depth=2) -> list[str]:
        result = self._exec(f"find {path} -maxdepth {max_depth} -printf '%P\\n' 2>/dev/null | head -200")
        if result.exit_code != 0:
            return []
        entries = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                entries.append(f"{path}/{line}" if not line.startswith("/") else line)
        return entries

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        import shlex
        escaped = shlex.quote(content)
        op = ">>" if append else ">"
        result = self._exec(f"mkdir -p $(dirname {path}) && printf '%s' {escaped} {op} {path}")
        if result.exit_code != 0:
            raise OSError(f"Failed to write file {path}: {result.stderr}")

    def glob(self, path: str, pattern: str, *, include_dirs: bool = False, max_results: int = 200) -> tuple[list[str], bool]:
        find_type = "" if include_dirs else "-type f"
        result = self._exec(f"find {path} -name '{pattern}' {find_type} 2>/dev/null | head -n {max_results + 1}")
        lines = result.stdout.splitlines()[:max_results]
        truncated = len(result.stdout.splitlines()) > max_results
        return lines, truncated

    def grep(
        self,
        path: str,
        pattern: str,
        *,
        glob: str | None = None,
        literal: bool = False,
        case_sensitive: bool = False,
        max_results: int = 100,
    ) -> tuple[list[GrepMatch], bool]:
        grep_opts = "-n"
        if not case_sensitive:
            grep_opts += "i"
        if literal:
            grep_opts += "F"
        if glob:
            grep_opts += f" --include='{glob}'"

        result = self._exec(f"grep -r {grep_opts} '{pattern}' {path} 2>/dev/null | head -n {max_results + 1}")
        matches = []
        truncated = len(result.stdout.splitlines()) > max_results
        for line in result.stdout.splitlines()[:max_results]:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append(GrepMatch(path=parts[0], line_number=int(parts[1]), line=parts[2]))
        return matches, truncated

    def update_file(self, path: str, content: bytes) -> None:
        import base64
        encoded = base64.b64encode(content).decode()
        result = self._exec(f"echo '{encoded}' | base64 -d > {path}")
        if result.exit_code != 0:
            raise OSError(f"Failed to update file {path}: {result.stderr}")


def select_sandbox_provider() -> SandboxProvider:
    from deerflow.sandbox.firecracker.kvm_utils import check_kvm_available

    kvm_status = check_kvm_available()
    if kvm_status.available:
        logger.info("KVM available — Firecracker VM sandbox is the primary option")
        from deerflow.sandbox.firecracker.firecracker_vm_provider import FirecrackerSandboxProvider
        return FirecrackerSandboxProvider()

    logger.info("KVM not available (%s) — trying fallback providers", kvm_status.reason)

    for provider_cls in [DockerSandboxProvider, PodmanSandboxProvider]:
        provider = provider_cls()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, provider.is_available())
                available = future.result(timeout=10)
        else:
            available = asyncio.run(provider.is_available())

        if available:
            logger.info("Using %s as fallback sandbox provider", provider_cls.__name__)
            return provider

    from deerflow.sandbox.local.local_sandbox_provider import LocalSandboxProvider
    logger.warning("No isolated sandbox available — falling back to local mode")
    return LocalSandboxProvider()
