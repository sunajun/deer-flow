import asyncio
import enum
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import aiohttp

from deerflow.sandbox.exceptions import SandboxError
from deerflow.sandbox.firecracker.kvm_utils import KVMStatus, check_kvm_available

logger = logging.getLogger(__name__)

_DEFAULT_FC_BINARY = "firecracker"
_DEFAULT_JAILER_BINARY = "jailer"
_VM_RUNTIME_DIR = "/tmp/deerflow-vm"
_DEFAULT_SSH_USER = "sandbox"
_DEFAULT_VM_IP = "192.168.100.2"
_DEFAULT_HOST_IP = "192.168.100.1"
_DEFAULT_SSH_PORT = 22
_DEFAULT_WORKSPACE_MOUNT = "/home/sandbox/workspace"
_API_SOCKET_WAIT_TIMEOUT = 5
_SSH_READY_TIMEOUT = 30
_GRACEFUL_SHUTDOWN_TIMEOUT = 10


class VMState(enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        if not parts:
            return "(no output)"
        return "\n".join(parts)


class KVMNotAvailableError(SandboxError):
    def __init__(self, kvm_status: KVMStatus):
        self.kvm_status = kvm_status
        msg = f"KVM not available: {kvm_status.reason}"
        if kvm_status.fix_description:
            msg += f" — Fix: {kvm_status.fix_description}"
        super().__init__(msg)


class FirecrackerVM:
    def __init__(
        self,
        kernel_path: str,
        rootfs_path: str,
        workspace_dir: str,
        vcpu_count: int = 2,
        mem_size_mib: int = 2048,
        firecracker_binary: str | None = None,
        ssh_private_key_path: str | None = None,
        file_sharing: str = "scp",
        sync_interval: int = 5,
    ):
        self.kernel_path = kernel_path
        self.rootfs_path = rootfs_path
        self.workspace_dir = workspace_dir
        self.vcpu_count = vcpu_count
        self.mem_size_mib = mem_size_mib
        self._firecracker_binary = firecracker_binary or self._find_firecracker_binary()
        self._ssh_private_key_path = ssh_private_key_path
        self._file_sharing = file_sharing
        self._sync_interval = sync_interval

        self._process: subprocess.Popen | None = None
        self._api_socket: str = ""
        self._vm_id: str = ""
        self._ssh_client = None
        self._rootfs_copy_path: str = ""
        self._tap_device: str = ""
        self._network_namespace: str = ""
        self._log_file = None
        self._log_path: str = ""

        self.state: VMState = VMState.STOPPED
        self._kvm_status: KVMStatus | None = None

    @staticmethod
    def _find_firecracker_binary() -> str:
        path = shutil.which("firecracker")
        if path:
            return path
        return _DEFAULT_FC_BINARY

    @staticmethod
    def _default_ssh_key_path() -> str:
        home = os.path.expanduser("~")
        key_dir = os.path.join(home, ".deerflow", "vm-keys")
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, "sandbox_key")
        if not os.path.exists(key_path):
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"],
                check=True,
            )
        return key_path

    async def start(self) -> None:
        if self.state == VMState.RUNNING:
            return

        self._kvm_status = check_kvm_available()
        if not self._kvm_status.available:
            raise KVMNotAvailableError(self._kvm_status)

        if not self._ssh_private_key_path:
            self._ssh_private_key_path = self._default_ssh_key_path()

        self.state = VMState.STARTING
        self._vm_id = f"deerflow-{uuid.uuid4().hex[:8]}"

        try:
            vm_dir = os.path.join(_VM_RUNTIME_DIR, self._vm_id)
            os.makedirs(vm_dir, exist_ok=True)

            self._api_socket = os.path.join(vm_dir, "api.sock")
            self._log_path = os.path.join(vm_dir, "firecracker.log")
            self._log_file = open(self._log_path, "w", encoding="utf-8")

            self._rootfs_copy_path = await self._prepare_rootfs_copy(vm_dir)

            await self._setup_networking()

            self._process = subprocess.Popen(
                [
                    self._firecracker_binary,
                    "--api-sock", self._api_socket,
                    "--id", self._vm_id,
                ],
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
            )

            await self._wait_for_api(timeout=_API_SOCKET_WAIT_TIMEOUT)
            await self._configure_vm()
            await self._start_instance()
            self._ssh_client = await self._wait_for_ssh(timeout=_SSH_READY_TIMEOUT)

            if self._file_sharing == "scp":
                await self._sync_to_vm()

            self.state = VMState.RUNNING
            logger.info("Firecracker VM %s started successfully", self._vm_id)
        except Exception:
            await self._cleanup_resources()
            self.state = VMState.STOPPED
            raise

    async def execute(self, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
        if self.state != VMState.RUNNING:
            raise SandboxError(f"VM is not running (state={self.state.value})")

        if cwd:
            command = f"cd {cwd} && {command}"

        if self._file_sharing == "scp":
            await self._sync_to_vm()

        try:
            result = await asyncio.wait_for(
                self._execute_via_ssh(command),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("Command timed out after %ds in VM %s: %s", timeout, self._vm_id, command[:100])
            return CommandResult(exit_code=-1, stdout="", stderr=f"Command timed out after {timeout}s")

        if self._file_sharing == "scp":
            await self._sync_from_vm()

        return result

    async def execute_stream(self, command: str, timeout: int = 300, cwd: str | None = None) -> AsyncGenerator[str, None]:
        if self.state != VMState.RUNNING:
            raise SandboxError(f"VM is not running (state={self.state.value})")

        if cwd:
            command = f"cd {cwd} && {command}"

        if self._file_sharing == "scp":
            await self._sync_to_vm()

        try:
            async for line in self._execute_via_ssh_stream(command, timeout=timeout):
                yield line
        finally:
            if self._file_sharing == "scp":
                await self._sync_from_vm()

    async def stop(self) -> None:
        if self.state in (VMState.STOPPED, VMState.STOPPING):
            return

        self.state = VMState.STOPPING
        try:
            if self._ssh_client is not None:
                try:
                    await self._ssh_execute("sudo shutdown -h now", timeout=5)
                except Exception:
                    pass
                self._ssh_client = None

            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=_GRACEFUL_SHUTDOWN_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=5)
                except Exception:
                    pass

            await self._cleanup_resources()
        finally:
            self.state = VMState.STOPPED
            logger.info("Firecracker VM %s stopped", self._vm_id)

    async def pause(self) -> None:
        if self.state != VMState.RUNNING:
            raise SandboxError(f"Cannot pause VM in state {self.state.value}")

        await self._api_put("/vm", {"state": "Paused"})
        self.state = VMState.PAUSED
        logger.info("Firecracker VM %s paused", self._vm_id)

    async def resume(self) -> None:
        if self.state != VMState.PAUSED:
            raise SandboxError(f"Cannot resume VM in state {self.state.value}")

        await self._api_put("/vm", {"state": "Resumed"})
        self.state = VMState.RUNNING
        logger.info("Firecracker VM %s resumed", self._vm_id)

    async def create_snapshot(self, snapshot_path: str, mem_file_path: str) -> None:
        if self.state != VMState.RUNNING:
            raise SandboxError(f"Cannot snapshot VM in state {self.state.value}")

        await self._api_put("/snapshot/create", {
            "snapshot_path": snapshot_path,
            "mem_file_path": mem_file_path,
            "type": "Full",
        })
        logger.info("Firecracker VM %s snapshot created", self._vm_id)

    async def restore_snapshot(self, snapshot_path: str, mem_file_path: str) -> None:
        if self.state != VMState.STOPPED:
            raise SandboxError(f"Cannot restore snapshot to VM in state {self.state.value}")

        vm_dir = os.path.join(_VM_RUNTIME_DIR, self._vm_id)
        os.makedirs(vm_dir, exist_ok=True)
        self._api_socket = os.path.join(vm_dir, "api.sock")
        self._log_path = os.path.join(vm_dir, "firecracker.log")
        self._log_file = open(self._log_path, "w", encoding="utf-8")

        self._process = subprocess.Popen(
            [
                self._firecracker_binary,
                "--api-sock", self._api_socket,
                "--id", self._vm_id,
            ],
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
        )

        await self._wait_for_api(timeout=_API_SOCKET_WAIT_TIMEOUT)

        await self._api_put("/snapshot/load", {
            "snapshot_path": snapshot_path,
            "mem_file_path": mem_file_path,
            "enable_diff_snapshots": False,
            "resume_vm": True,
        })

        self._ssh_client = await self._wait_for_ssh(timeout=_SSH_READY_TIMEOUT)
        self.state = VMState.RUNNING
        logger.info("Firecracker VM %s restored from snapshot", self._vm_id)

    async def is_running(self) -> bool:
        if self.state != VMState.RUNNING:
            return False
        try:
            result = await self._execute_via_ssh("echo health", timeout=5)
            return result.exit_code == 0 and "health" in result.stdout
        except Exception:
            return False

    def __del__(self):
        process = getattr(self, "_process", None)
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass
        log_file = getattr(self, "_log_file", None)
        if log_file is not None:
            try:
                log_file.close()
            except Exception:
                pass

    async def _prepare_rootfs_copy(self, vm_dir: str) -> str:
        copy_path = os.path.join(vm_dir, "rootfs.ext4")
        if os.path.exists(copy_path):
            return copy_path

        try:
            result = subprocess.run(
                ["cp", "--reflink=auto", self.rootfs_path, copy_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                shutil.copy2(self.rootfs_path, copy_path)
        except Exception:
            shutil.copy2(self.rootfs_path, copy_path)

        return copy_path

    async def _setup_networking(self) -> None:
        self._tap_device = f"fc-{self._vm_id[:8]}"
        try:
            subprocess.run(["ip", "tuntap", "add", "dev", self._tap_device, "mode", "tap"], check=True, capture_output=True)
            subprocess.run(["ip", "addr", "add", f"{_DEFAULT_HOST_IP}/24", "dev", self._tap_device], check=True, capture_output=True)
            subprocess.run(["ip", "link", "set", self._tap_device, "up"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.warning("Failed to set up TAP device %s: %s", self._tap_device, e)

    async def _teardown_networking(self) -> None:
        if self._tap_device:
            try:
                subprocess.run(["ip", "link", "set", self._tap_device, "down"], capture_output=True)
                subprocess.run(["ip", "tuntap", "del", "dev", self._tap_device, "mode", "tap"], capture_output=True)
            except Exception:
                pass

    async def _wait_for_api(self, timeout: float = 5) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if os.path.exists(self._api_socket):
                return
            await asyncio.sleep(0.1)
        raise SandboxError(f"Firecracker API socket not available after {timeout}s")

    async def _configure_vm(self) -> None:
        await self._api_put("/boot-source", {
            "kernel_image_path": self.kernel_path,
            "boot_args": "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/sbin/overlay-init",
        })

        await self._api_put("/drives/rootfs", {
            "drive_id": "rootfs",
            "path_on_host": self._rootfs_copy_path,
            "is_root_device": True,
            "is_read_only": False,
        })

        await self._api_put("/machine-config", {
            "vcpu_count": self.vcpu_count,
            "mem_size_mib": self.mem_size_mib,
            "ht_enabled": False,
        })

        if self._tap_device:
            await self._api_put("/network-interfaces/eth0", {
                "iface_id": "eth0",
                "host_dev_name": self._tap_device,
                "guest_mac": "AA:FC:00:00:00:01",
            })

        await self._api_put("/vsock", {
            "vsock_id": "vsock0",
            "guest_cid": 3,
            "uds_path": os.path.join(os.path.dirname(self._api_socket), "vsock.sock"),
        })

    async def _start_instance(self) -> None:
        await self._api_put("/actions", {
            "action_type": "InstanceStart",
        })

    async def _api_put(self, path: str, data: dict) -> dict:
        url = f"http://localhost{path}"
        connector = aiohttp.UnixConnector(path=self._api_socket)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.put(url, json=data) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise SandboxError(
                        f"Firecracker API error: PUT {path} returned {resp.status}: {body}",
                    )
                try:
                    return json.loads(body) if body else {}
                except json.JSONDecodeError:
                    return {}

    async def _api_patch(self, path: str, data: dict) -> dict:
        url = f"http://localhost{path}"
        connector = aiohttp.UnixConnector(path=self._api_socket)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.patch(url, json=data) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise SandboxError(
                        f"Firecracker API error: PATCH {path} returned {resp.status}: {body}",
                    )
                try:
                    return json.loads(body) if body else {}
                except json.JSONDecodeError:
                    return {}

    async def _wait_for_ssh(self, timeout: float = 30) -> object:
        try:
            import asyncssh
        except ImportError:
            raise SandboxError("asyncssh is required for Firecracker VM SSH access. Install with: pip install asyncssh")

        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                conn = await asyncio.wait_for(
                    asyncssh.connect(
                        host=_DEFAULT_VM_IP,
                        port=_DEFAULT_SSH_PORT,
                        username=_DEFAULT_SSH_USER,
                        client_keys=[self._ssh_private_key_path],
                        known_hosts=None,
                    ),
                    timeout=3,
                )
                return conn
            except Exception as e:
                last_error = e
                await asyncio.sleep(1)

        raise SandboxError(f"SSH not available after {timeout}s: {last_error}")

    async def _execute_via_ssh(self, command: str, timeout: int | None = None) -> CommandResult:
        import asyncssh

        conn = self._ssh_client
        if conn is None:
            raise SandboxError("SSH client not connected")

        try:
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout or 300,
            )
            return CommandResult(
                exit_code=result.exit_status,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        except TimeoutError:
            raise
        except asyncssh.Error as e:
            return CommandResult(exit_code=-1, stdout="", stderr=str(e))

    async def _execute_via_ssh_stream(self, command: str, timeout: int = 300) -> AsyncGenerator[str, None]:

        conn = self._ssh_client
        if conn is None:
            raise SandboxError("SSH client not connected")

        async with conn.create_process(command) as proc:
            deadline = time.monotonic() + timeout
            async for line in proc.stdout:
                if time.monotonic() > deadline:
                    proc.terminate()
                    break
                yield line.rstrip("\n")

    async def _sync_to_vm(self) -> None:
        if not self.workspace_dir or not os.path.isdir(self.workspace_dir):
            return

        import asyncssh

        conn = self._ssh_client
        if conn is None:
            return

        try:
            await asyncssh.scp(
                (self.workspace_dir + "/",),
                conn,
                _DEFAULT_WORKSPACE_MOUNT + "/",
                recurse=True,
                preserve=True,
            )
        except Exception as e:
            logger.warning("Failed to sync files to VM: %s", e)

    async def _sync_from_vm(self) -> None:
        if not self.workspace_dir:
            return

        import asyncssh

        conn = self._ssh_client
        if conn is None:
            return

        try:
            await asyncssh.scp(
                (conn, _DEFAULT_WORKSPACE_MOUNT + "/"),
                self.workspace_dir + "/",
                recurse=True,
                preserve=True,
            )
        except Exception as e:
            logger.warning("Failed to sync files from VM: %s", e)

    async def _ssh_execute(self, command: str, timeout: int = 10) -> CommandResult:
        return await self._execute_via_ssh(command, timeout=timeout)

    async def _cleanup_resources(self) -> None:
        await self._teardown_networking()

        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

        if self._vm_id:
            vm_dir = os.path.join(_VM_RUNTIME_DIR, self._vm_id)
            if os.path.isdir(vm_dir):
                try:
                    shutil.rmtree(vm_dir, ignore_errors=True)
                except Exception:
                    pass

        self._process = None
        self._ssh_client = None
        self._api_socket = ""
