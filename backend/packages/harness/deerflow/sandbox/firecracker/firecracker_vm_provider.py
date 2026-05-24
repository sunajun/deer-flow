import asyncio
import atexit
import logging
import os
import signal
import threading

from deerflow.config import get_app_config
from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import get_effective_user_id
from deerflow.sandbox.exceptions import SandboxError
from deerflow.sandbox.firecracker.firecracker_vm import (
    FirecrackerVM,
    KVMNotAvailableError,
)
from deerflow.sandbox.sandbox import Sandbox
from deerflow.sandbox.sandbox_provider import SandboxProvider
from deerflow.sandbox.search import GrepMatch

logger = logging.getLogger(__name__)

_DEFAULT_KERNEL_PATH = "resources/vm-images/vmlinux"
_DEFAULT_ROOTFS_PATH = "resources/vm-images/rootfs.ext4"
_DEFAULT_VCPU = 2
_DEFAULT_MEM_MIB = 2048
_DEFAULT_FILE_SHARING = "scp"


class FirecrackerSandbox(Sandbox):
    def __init__(self, id: str, vm: FirecrackerVM):
        super().__init__(id)
        self._vm = vm

    @property
    def vm(self) -> FirecrackerVM:
        return self._vm

    def execute_command(self, command: str) -> str:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self._vm.execute(command))
                result = future.result(timeout=600)
        else:
            result = asyncio.run(self._vm.execute(command))

        output = result.stdout
        if result.stderr:
            output += f"\nStd Error:\n{result.stderr}" if output else result.stderr
        if result.exit_code != 0:
            output += f"\nExit Code: {result.exit_code}"
        return output or "(no output)"

    def read_file(self, path: str) -> str:
        result = asyncio.run(self._vm.execute(f"cat {path}"))
        if result.exit_code != 0:
            raise OSError(f"Failed to read file {path}: {result.stderr}")
        return result.stdout

    def download_file(self, path: str) -> bytes:
        import base64
        result = asyncio.run(self._vm.execute(f"base64 {path}"))
        if result.exit_code != 0:
            raise OSError(f"Failed to download file {path}: {result.stderr}")
        return base64.b64decode(result.stdout)

    def list_dir(self, path: str, max_depth=2) -> list[str]:
        result = asyncio.run(self._vm.execute(f"find {path} -maxdepth {max_depth} -printf '%P\\n' 2>/dev/null | head -200"))
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
        result = asyncio.run(self._vm.execute(f"mkdir -p $(dirname {path}) && printf '%s' {escaped} {op} {path}"))
        if result.exit_code != 0:
            raise OSError(f"Failed to write file {path}: {result.stderr}")

    def glob(self, path: str, pattern: str, *, include_dirs: bool = False, max_results: int = 200) -> tuple[list[str], bool]:
        find_type = "" if include_dirs else "-type f"
        result = asyncio.run(self._vm.execute(f"find {path} -name '{pattern}' {find_type} 2>/dev/null | head -n {max_results + 1}"))
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

        result = asyncio.run(self._vm.execute(f"grep -r {grep_opts} '{pattern}' {path} 2>/dev/null | head -n {max_results + 1}"))
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
        result = asyncio.run(self._vm.execute(f"echo '{encoded}' | base64 -d > {path}"))
        if result.exit_code != 0:
            raise OSError(f"Failed to update file {path}: {result.stderr}")


class FirecrackerSandboxProvider(SandboxProvider):
    uses_thread_data_mounts = True

    def __init__(self):
        self._lock = threading.Lock()
        self._sandboxes: dict[str, FirecrackerSandbox] = {}
        self._vms: dict[str, FirecrackerVM] = {}
        self._thread_sandboxes: dict[str, str] = {}
        self._shutdown_called = False
        self._config = self._load_config()
        atexit.register(self.shutdown)
        self._register_signal_handlers()

    def _load_config(self) -> dict:
        try:
            config = get_app_config()
            sandbox_config = config.sandbox
            return {
                "kernel_path": getattr(sandbox_config, "kernel_path", None) or _DEFAULT_KERNEL_PATH,
                "rootfs_path": getattr(sandbox_config, "rootfs_path", None) or _DEFAULT_ROOTFS_PATH,
                "vcpu_count": getattr(sandbox_config, "vcpu_count", None) or _DEFAULT_VCPU,
                "mem_size_mib": getattr(sandbox_config, "mem_size_mib", None) or _DEFAULT_MEM_MIB,
                "file_sharing": getattr(sandbox_config, "file_sharing", None) or _DEFAULT_FILE_SHARING,
            }
        except Exception:
            return {
                "kernel_path": _DEFAULT_KERNEL_PATH,
                "rootfs_path": _DEFAULT_ROOTFS_PATH,
                "vcpu_count": _DEFAULT_VCPU,
                "mem_size_mib": _DEFAULT_MEM_MIB,
                "file_sharing": _DEFAULT_FILE_SHARING,
            }

    def _register_signal_handlers(self) -> None:
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sigint = signal.getsignal(signal.SIGINT)

        def signal_handler(signum, frame):
            self.shutdown()
            original = self._original_sigterm if signum == signal.SIGTERM else self._original_sigint
            if callable(original):
                original(signum, frame)
            elif original == signal.SIG_DFL:
                signal.signal(signum, signal.SIG_DFL)
                signal.raise_signal(signum)

        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except ValueError:
            pass

    def _get_workspace_dir(self, thread_id: str | None) -> str:
        if thread_id is None:
            return os.path.join(os.path.expanduser("~"), ".deerflow", "workspace")
        paths = get_paths()
        user_id = get_effective_user_id()
        paths.ensure_thread_dirs(thread_id, user_id=user_id)
        return str(paths.sandbox_work_dir(thread_id, user_id=user_id))

    def acquire(self, thread_id: str | None = None) -> str:
        with self._lock:
            if thread_id and thread_id in self._thread_sandboxes:
                existing_id = self._thread_sandboxes[thread_id]
                if existing_id in self._sandboxes:
                    return existing_id

        workspace_dir = self._get_workspace_dir(thread_id)
        sandbox_id = f"fc-{thread_id or 'default'}"

        vm = FirecrackerVM(
            kernel_path=self._config["kernel_path"],
            rootfs_path=self._config["rootfs_path"],
            workspace_dir=workspace_dir,
            vcpu_count=self._config["vcpu_count"],
            mem_size_mib=self._config["mem_size_mib"],
            file_sharing=self._config["file_sharing"],
        )

        try:
            asyncio.run(vm.start())
        except KVMNotAvailableError as e:
            logger.error("KVM not available for Firecracker: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to start Firecracker VM: %s", e)
            raise SandboxError(f"Failed to start Firecracker VM: {e}")

        sandbox = FirecrackerSandbox(id=sandbox_id, vm=vm)

        with self._lock:
            self._sandboxes[sandbox_id] = sandbox
            self._vms[sandbox_id] = vm
            if thread_id:
                self._thread_sandboxes[thread_id] = sandbox_id

        return sandbox_id

    async def acquire_async(self, thread_id: str | None = None) -> str:
        with self._lock:
            if thread_id and thread_id in self._thread_sandboxes:
                existing_id = self._thread_sandboxes[thread_id]
                if existing_id in self._sandboxes:
                    return existing_id

        workspace_dir = self._get_workspace_dir(thread_id)
        sandbox_id = f"fc-{thread_id or 'default'}"

        vm = FirecrackerVM(
            kernel_path=self._config["kernel_path"],
            rootfs_path=self._config["rootfs_path"],
            workspace_dir=workspace_dir,
            vcpu_count=self._config["vcpu_count"],
            mem_size_mib=self._config["mem_size_mib"],
            file_sharing=self._config["file_sharing"],
        )

        try:
            await vm.start()
        except KVMNotAvailableError as e:
            logger.error("KVM not available for Firecracker: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to start Firecracker VM: %s", e)
            raise SandboxError(f"Failed to start Firecracker VM: {e}")

        sandbox = FirecrackerSandbox(id=sandbox_id, vm=vm)

        with self._lock:
            self._sandboxes[sandbox_id] = sandbox
            self._vms[sandbox_id] = vm
            if thread_id:
                self._thread_sandboxes[thread_id] = sandbox_id

        return sandbox_id

    def get(self, sandbox_id: str) -> Sandbox | None:
        with self._lock:
            return self._sandboxes.get(sandbox_id)

    def release(self, sandbox_id: str) -> None:
        vm = None
        with self._lock:
            self._sandboxes.pop(sandbox_id, None)
            vm = self._vms.pop(sandbox_id, None)
            thread_ids_to_remove = [tid for tid, sid in self._thread_sandboxes.items() if sid == sandbox_id]
            for tid in thread_ids_to_remove:
                del self._thread_sandboxes[tid]

        if vm is not None:
            try:
                asyncio.run(vm.stop())
            except Exception as e:
                logger.warning("Failed to stop VM %s: %s", sandbox_id, e)

    def reset(self) -> None:
        with self._lock:
            for sandbox_id in list(self._sandboxes.keys()):
                vm = self._vms.pop(sandbox_id, None)
                if vm:
                    try:
                        asyncio.run(vm.stop())
                    except Exception:
                        pass
            self._sandboxes.clear()
            self._thread_sandboxes.clear()

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_called:
                return
            self._shutdown_called = True

        for sandbox_id in list(self._sandboxes.keys()):
            try:
                self.release(sandbox_id)
            except Exception as e:
                logger.error("Failed to release sandbox %s during shutdown: %s", sandbox_id, e)
