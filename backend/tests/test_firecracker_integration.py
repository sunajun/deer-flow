import os

import pytest

from deerflow.sandbox.firecracker.firecracker_vm import (
    CommandResult,
    FirecrackerVM,
    VMState,
)

KVM_AVAILABLE = os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)

KERNEL_PATH = os.environ.get("FC_KERNEL", "resources/vm-images/vmlinux")
ROOTFS_PATH = os.environ.get("FC_ROOTFS", "resources/vm-images/rootfs.ext4")


def _make_vm(workspace_dir="/tmp/deerflow-integration-workspace", **kwargs):
    return FirecrackerVM(
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        workspace_dir=workspace_dir,
        **kwargs,
    )


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestVMLifecycleWithVersion:
    @pytest.mark.asyncio
    async def test_start_stop_with_version_check(self):
        vm = _make_vm()
        await vm.start()
        try:
            assert vm.state == VMState.RUNNING

            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            version = result.stdout.strip()
            assert version != ""

            result = await vm.execute("echo lifecycle_ok")
            assert result.exit_code == 0
            assert "lifecycle_ok" in result.stdout
        finally:
            await vm.stop()
            assert vm.state == VMState.STOPPED


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestCommandExecution:
    @pytest.fixture
    def vm(self):
        return _make_vm()

    @pytest.mark.asyncio
    async def test_whoami(self, vm):
        await vm.start()
        try:
            result = await vm.execute("whoami")
            assert result.exit_code == 0
            assert "sandbox" in result.stdout
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_python3_version(self, vm):
        await vm.start()
        try:
            result = await vm.execute("python3 --version")
            assert result.exit_code == 0
            assert "Python" in result.stdout
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_node_version(self, vm):
        await vm.start()
        try:
            result = await vm.execute("node --version")
            assert result.exit_code == 0
            assert result.stdout.strip().startswith("v")
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_git_version(self, vm):
        await vm.start()
        try:
            result = await vm.execute("git --version")
            assert result.exit_code == 0
            assert "git version" in result.stdout
        finally:
            await vm.stop()


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestVersionInfo:
    @pytest.mark.asyncio
    async def test_read_deerflow_version(self):
        vm = _make_vm()
        await vm.start()
        try:
            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            version = result.stdout.strip()
            assert version != ""
            parts = version.split(".")
            assert len(parts) >= 2
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_compat_version_file(self):
        vm = _make_vm()
        await vm.start()
        try:
            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            version_content = result.stdout.strip()
            assert "COMPAT_VERSION" in version_content or "." in version_content
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_min_app_version_readable(self):
        vm = _make_vm()
        await vm.start()
        try:
            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            version_content = result.stdout.strip()
            assert "MIN_APP_VERSION" in version_content or "." in version_content
        finally:
            await vm.stop()


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestSnapshotWithVersion:
    @pytest.mark.asyncio
    async def test_snapshot_save_restore_version_preserved(self, tmp_path):
        vm = _make_vm(workspace_dir="/tmp/deerflow-integration-snapshot-workspace")
        await vm.start()
        try:
            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            version_before = result.stdout.strip()

            snapshot_path = str(tmp_path / "vm.snap")
            mem_path = str(tmp_path / "vm.mem")
            await vm.create_snapshot(snapshot_path, mem_path)

            await vm.stop()
            assert vm.state == VMState.STOPPED

            await vm.restore_snapshot(snapshot_path, mem_path)
            assert vm.state == VMState.RUNNING

            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            version_after = result.stdout.strip()
            assert version_after == version_before
        finally:
            await vm.stop()


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestParallelVMInstances:
    @pytest.mark.asyncio
    async def test_multiple_vms_parallel(self):
        vms = []
        for i in range(3):
            vm = _make_vm(workspace_dir=f"/tmp/deerflow-integration-parallel-workspace-{i}")
            await vm.start()
            vms.append(vm)

        try:
            for i, vm in enumerate(vms):
                assert vm.state == VMState.RUNNING
                result = await vm.execute(f"echo vm_{i}")
                assert result.exit_code == 0
                assert f"vm_{i}" in result.stdout

            for i, vm in enumerate(vms):
                result = await vm.execute("cat /etc/deerflow-version")
                assert result.exit_code == 0
                assert result.stdout.strip() != ""
        finally:
            for vm in vms:
                await vm.stop()

    @pytest.mark.asyncio
    async def test_parallel_command_execution(self):
        vms = []
        for i in range(2):
            vm = _make_vm(workspace_dir=f"/tmp/deerflow-integration-cmd-workspace-{i}")
            await vm.start()
            vms.append(vm)

        try:
            commands = ["whoami", "python3 --version", "node --version", "git --version"]
            for vm in vms:
                for cmd in commands:
                    result = await vm.execute(cmd)
                    assert result.exit_code == 0
        finally:
            for vm in vms:
                await vm.stop()


@pytest.mark.skipif(not KVM_AVAILABLE, reason="KVM not available")
class TestResourceLimits:
    @pytest.mark.asyncio
    async def test_minimal_vcpu_and_mem(self):
        vm = _make_vm(
            workspace_dir="/tmp/deerflow-integration-min-workspace",
            vcpu_count=1,
            mem_size_mib=512,
        )
        await vm.start()
        try:
            result = await vm.execute("echo minimal_resources")
            assert result.exit_code == 0
            assert "minimal_resources" in result.stdout
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_minimal_resources_version_check(self):
        vm = _make_vm(
            workspace_dir="/tmp/deerflow-integration-min-ver-workspace",
            vcpu_count=1,
            mem_size_mib=512,
        )
        await vm.start()
        try:
            result = await vm.execute("cat /etc/deerflow-version")
            assert result.exit_code == 0
            assert result.stdout.strip() != ""
        finally:
            await vm.stop()

    @pytest.mark.asyncio
    async def test_minimal_resources_toolchain(self):
        vm = _make_vm(
            workspace_dir="/tmp/deerflow-integration-min-tools-workspace",
            vcpu_count=1,
            mem_size_mib=512,
        )
        await vm.start()
        try:
            for cmd in ["whoami", "python3 --version", "git --version"]:
                result = await vm.execute(cmd)
                assert result.exit_code == 0
        finally:
            await vm.stop()
