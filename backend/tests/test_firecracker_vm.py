import os
from unittest.mock import MagicMock, patch

import pytest

from deerflow.sandbox.firecracker.firecracker_vm import (
    CommandResult,
    FirecrackerVM,
    KVMNotAvailableError,
    VMState,
)
from deerflow.sandbox.firecracker.kvm_utils import KVMStatus, check_kvm_available
from deerflow.sandbox.firecracker.rootless_sandbox import (
    ContainerSandbox,
    DockerSandboxProvider,
    PodmanSandboxProvider,
)

KVM_AVAILABLE = os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


class TestCommandResult:
    def test_output_stdout_only(self):
        r = CommandResult(exit_code=0, stdout="hello", stderr="")
        assert r.output == "hello"

    def test_output_stderr_only(self):
        r = CommandResult(exit_code=1, stdout="", stderr="error")
        assert r.output == "error"

    def test_output_both(self):
        r = CommandResult(exit_code=0, stdout="out", stderr="err")
        assert r.output == "out\nerr"

    def test_output_empty(self):
        r = CommandResult(exit_code=0, stdout="", stderr="")
        assert r.output == "(no output)"


class TestVMState:
    def test_state_values(self):
        assert VMState.STOPPED.value == "stopped"
        assert VMState.STARTING.value == "starting"
        assert VMState.RUNNING.value == "running"
        assert VMState.PAUSED.value == "paused"
        assert VMState.STOPPING.value == "stopping"


class TestKVMStatus:
    def test_available_true(self):
        status = KVMStatus(available=True)
        assert status.available is True
        assert status.reason == ""
        assert status.can_fix is False

    def test_available_false_with_fix(self):
        status = KVMStatus(
            available=False,
            reason="No access",
            can_fix=True,
            fix_description="sudo usermod -aG kvm $USER",
        )
        assert status.available is False
        assert status.reason == "No access"
        assert status.can_fix is True
        assert "usermod" in status.fix_description


class TestKVMNotAvailableError:
    def test_error_with_fix(self):
        status = KVMStatus(
            available=False,
            reason="No /dev/kvm",
            can_fix=True,
            fix_description="sudo modprobe kvm_intel",
        )
        err = KVMNotAvailableError(status)
        assert "No /dev/kvm" in str(err)
        assert "sudo modprobe kvm_intel" in str(err)
        assert err.kvm_status is status

    def test_error_without_fix(self):
        status = KVMStatus(available=False, reason="Unknown CPU")
        err = KVMNotAvailableError(status)
        assert "Unknown CPU" in str(err)
        assert "Fix" not in str(err)


class TestCheckKvmAvailable:
    @patch("os.path.exists")
    @patch("os.access")
    def test_kvm_available(self, mock_access, mock_exists):
        mock_exists.return_value = True
        mock_access.return_value = True
        with patch("deerflow.sandbox.firecracker.kvm_utils._is_kvm_module_loaded", return_value=True):
            status = check_kvm_available()
        assert status.available is True

    @patch("os.path.exists")
    def test_kvm_not_exists_no_cpu(self, mock_exists):
        mock_exists.return_value = False
        with patch("deerflow.sandbox.firecracker.kvm_utils._detect_cpu_type", return_value="unknown"), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_kvm_module_loaded", return_value=False):
            status = check_kvm_available()
        assert status.available is False
        assert "unknown" in status.reason.lower() or "does not exist" in status.reason.lower()

    @patch("os.path.exists")
    def test_kvm_not_exists_intel_autoload(self, mock_exists):
        mock_exists.side_effect = [False, True]
        with patch("deerflow.sandbox.firecracker.kvm_utils._detect_cpu_type", return_value="intel"), \
             patch("deerflow.sandbox.firecracker.kvm_utils._try_load_module", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_kvm_module_loaded", return_value=False):
            status = check_kvm_available()
        assert status.available is True

    @patch("os.path.exists")
    @patch("os.access")
    def test_kvm_no_permission(self, mock_access, mock_exists):
        mock_exists.return_value = True
        mock_access.return_value = False
        with patch("deerflow.sandbox.firecracker.kvm_utils._check_group_exists", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._check_user_in_group", return_value=False), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_kvm_module_loaded", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_in_docker", return_value=False), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_in_cloud_vm", return_value=False):
            status = check_kvm_available()
        assert status.available is False
        assert status.can_fix is True
        assert "usermod" in status.fix_description

    @patch("os.path.exists")
    def test_kvm_in_docker_no_dev(self, mock_exists):
        mock_exists.return_value = False
        with patch("deerflow.sandbox.firecracker.kvm_utils._detect_cpu_type", return_value="unknown"), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_kvm_module_loaded", return_value=False), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_in_docker", return_value=True):
            status = check_kvm_available()
        assert status.available is False
        assert "Docker" in status.reason
        assert "--device /dev/kvm" in status.fix_description

    @patch("os.path.exists")
    @patch("os.access")
    def test_kvm_cloud_no_nested(self, mock_access, mock_exists):
        mock_exists.return_value = True
        mock_access.return_value = False
        with patch("deerflow.sandbox.firecracker.kvm_utils._check_group_exists", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._check_user_in_group", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_kvm_module_loaded", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_in_docker", return_value=False), \
             patch("deerflow.sandbox.firecracker.kvm_utils._is_in_cloud_vm", return_value=True), \
             patch("deerflow.sandbox.firecracker.kvm_utils._check_nested_virtualization", return_value=False):
            status = check_kvm_available()
        assert status.available is False
        assert "nested" in status.reason.lower() or "cloud" in status.reason.lower()


class TestFirecrackerVMInit:
    def test_init_defaults(self):
        vm = FirecrackerVM(
            kernel_path="/path/to/vmlinux",
            rootfs_path="/path/to/rootfs.ext4",
            workspace_dir="/tmp/workspace",
        )
        assert vm.kernel_path == "/path/to/vmlinux"
        assert vm.rootfs_path == "/path/to/rootfs.ext4"
        assert vm.workspace_dir == "/tmp/workspace"
        assert vm.vcpu_count == 2
        assert vm.mem_size_mib == 2048
        assert vm.state == VMState.STOPPED
        assert vm._process is None
        assert vm._ssh_client is None

    def test_init_custom_params(self):
        vm = FirecrackerVM(
            kernel_path="/k",
            rootfs_path="/r",
            workspace_dir="/w",
            vcpu_count=4,
            mem_size_mib=4096,
            file_sharing="vsock",
        )
        assert vm.vcpu_count == 4
        assert vm.mem_size_mib == 4096
        assert vm._file_sharing == "vsock"


class TestDockerSandboxProvider:
    def test_init(self):
        provider = DockerSandboxProvider()
        assert provider.container_cmd == "docker"

    @pytest.mark.asyncio
    async def test_is_available_docker_not_installed(self):
        provider = DockerSandboxProvider()
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.wait = MagicMock(return_value=MagicMock())
            mock_proc.returncode = 127
            mock_exec.side_effect = FileNotFoundError
            result = await provider.is_available()
        assert result is False


class TestPodmanSandboxProvider:
    def test_init(self):
        provider = PodmanSandboxProvider()
        assert provider.container_cmd == "podman"

    @pytest.mark.asyncio
    async def test_is_available_podman_not_installed(self):
        provider = PodmanSandboxProvider()
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError
            result = await provider.is_available()
        assert result is False


class TestContainerSandbox:
    def test_init(self):
        sandbox = ContainerSandbox(id="test", container_id="abc123", container_cmd="docker")
        assert sandbox.id == "test"
        assert sandbox._container_id == "abc123"
        assert sandbox._container_cmd == "docker"


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestFirecrackerVMLive:
    @pytest.fixture
    def vm(self):
        return FirecrackerVM(
            kernel_path=os.environ.get("FC_KERNEL", "resources/vm-images/vmlinux"),
            rootfs_path=os.environ.get("FC_ROOTFS", "resources/vm-images/rootfs.ext4"),
            workspace_dir="/tmp/deerflow-test-workspace",
        )

    @pytest.mark.asyncio
    async def test_vm_lifecycle(self, vm):
        await vm.start()
        assert vm.state == VMState.RUNNING

        result = await vm.execute("echo hello")
        assert result.exit_code == 0
        assert "hello" in result.stdout

        await vm.stop()
        assert vm.state == VMState.STOPPED

    @pytest.mark.asyncio
    async def test_command_execution(self, vm):
        await vm.start()
        try:
            result = await vm.execute("whoami")
            assert result.exit_code == 0
            assert "sandbox" in result.stdout
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_command_with_cwd(self, vm):
        await vm.start()
        try:
            result = await vm.execute("pwd", cwd="/home/sandbox/workspace")
            assert result.exit_code == 0
            assert "/home/sandbox/workspace" in result.stdout
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_command_timeout(self, vm):
        await vm.start()
        try:
            result = await vm.execute("sleep 60", timeout=2)
            assert result.exit_code == -1
            assert "timed out" in result.stderr.lower()
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_pause_resume(self, vm):
        await vm.start()
        try:
            await vm.pause()
            assert vm.state == VMState.PAUSED

            await vm.resume()
            assert vm.state == VMState.RUNNING

            result = await vm.execute("echo after_resume")
            assert result.exit_code == 0
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_health_check(self, vm):
        await vm.start()
        try:
            assert await vm.is_running() is True
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_is_running_when_stopped(self, vm):
        assert await vm.is_running() is False


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestFirecrackerMultiVM:
    @pytest.mark.asyncio
    async def test_parallel_vms(self):
        vms = []
        for i in range(2):
            vm = FirecrackerVM(
                kernel_path=os.environ.get("FC_KERNEL", "resources/vm-images/vmlinux"),
                rootfs_path=os.environ.get("FC_ROOTFS", "resources/vm-images/rootfs.ext4"),
                workspace_dir=f"/tmp/deerflow-test-workspace-{i}",
            )
            await vm.start()
            vms.append(vm)

        try:
            for i, vm in enumerate(vms):
                result = await vm.execute(f"echo vm_{i}")
                assert result.exit_code == 0
                assert f"vm_{i}" in result.stdout
        finally:
            for vm in vms:
                await vm.stop()


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestFirecrackerSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_save_restore(self, tmp_path):
        vm = FirecrackerVM(
            kernel_path=os.environ.get("FC_KERNEL", "resources/vm-images/vmlinux"),
            rootfs_path=os.environ.get("FC_ROOTFS", "resources/vm-images/rootfs.ext4"),
            workspace_dir="/tmp/deerflow-test-snapshot-workspace",
        )
        await vm.start()
        try:
            result = await vm.execute("echo before_snapshot")
            assert result.exit_code == 0

            snapshot_path = str(tmp_path / "vm.snap")
            mem_path = str(tmp_path / "vm.mem")
            await vm.create_snapshot(snapshot_path, mem_path)

            await vm.stop()
            assert vm.state == VMState.STOPPED

            await vm.restore_snapshot(snapshot_path, mem_path)
            assert vm.state == VMState.RUNNING

            result = await vm.execute("echo after_restore")
            assert result.exit_code == 0
        finally:
            await vm.stop()


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestFirecrackerResourceLimits:
    @pytest.mark.asyncio
    async def test_minimal_resources(self):
        vm = FirecrackerVM(
            kernel_path=os.environ.get("FC_KERNEL", "resources/vm-images/vmlinux"),
            rootfs_path=os.environ.get("FC_ROOTFS", "resources/vm-images/rootfs.ext4"),
            workspace_dir="/tmp/deerflow-test-min-workspace",
            vcpu_count=1,
            mem_size_mib=512,
        )
        await vm.start()
        try:
            result = await vm.execute("echo minimal")
            assert result.exit_code == 0
        finally:
            await vm.stop()
