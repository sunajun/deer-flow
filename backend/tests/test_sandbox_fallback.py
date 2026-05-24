import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deerflow.sandbox.base import (
    CommandResult,
    CrossPlatformSandboxProvider,
    SandboxInfo,
    VMState,
)
from deerflow.sandbox.fallback import FallbackManager
from deerflow.sandbox.local_sandbox import LocalSandboxProvider, _audit_log
from deerflow.sandbox.strategy import SANDBOX_REQUIRED_TOOLS, SandboxRouter, SandboxStrategy
from deerflow.sandbox.vm_sandbox import VMSandboxProvider


class TestSandboxRouter:
    def test_selective_mode_high_risk_tools(self):
        router = SandboxRouter(SandboxStrategy.SELECTIVE)
        assert router.should_use_sandbox("bash") is True
        assert router.should_use_sandbox("write_file") is True
        assert router.should_use_sandbox("str_replace") is True
        assert router.should_use_sandbox("python_exec") is True

    def test_selective_mode_low_risk_tools(self):
        router = SandboxRouter(SandboxStrategy.SELECTIVE)
        assert router.should_use_sandbox("chat") is False
        assert router.should_use_sandbox("clarify") is False
        assert router.should_use_sandbox("read_file") is False
        assert router.should_use_sandbox("ls") is False
        assert router.should_use_sandbox("glob") is False
        assert router.should_use_sandbox("grep") is False

    def test_strict_mode_all_tools(self):
        router = SandboxRouter(SandboxStrategy.STRICT)
        for tool in SANDBOX_REQUIRED_TOOLS:
            assert router.should_use_sandbox(tool) is True
        assert router.should_use_sandbox("unknown_tool") is True

    def test_local_mode_all_tools(self):
        router = SandboxRouter(SandboxStrategy.LOCAL)
        for tool in SANDBOX_REQUIRED_TOOLS:
            assert router.should_use_sandbox(tool) is False
        assert router.should_use_sandbox("unknown_tool") is False

    def test_get_execution_target(self):
        router = SandboxRouter(SandboxStrategy.SELECTIVE)
        assert router.get_execution_target("bash") == "vm"
        assert router.get_execution_target("read_file") == "local"

    def test_from_config(self):
        config = {"sandbox": {"strategy": "strict"}}
        router = SandboxRouter.from_config(config)
        assert router.strategy == SandboxStrategy.STRICT

    def test_from_config_default(self):
        config = {}
        router = SandboxRouter.from_config(config)
        assert router.strategy == SandboxStrategy.SELECTIVE

    def test_set_strategy(self):
        router = SandboxRouter(SandboxStrategy.LOCAL)
        router.set_strategy(SandboxStrategy.STRICT)
        assert router.strategy == SandboxStrategy.STRICT
        assert router.should_use_sandbox("bash") is True

    def test_unknown_tool_selective_defaults_to_sandbox(self):
        router = SandboxRouter(SandboxStrategy.SELECTIVE)
        assert router.should_use_sandbox("totally_unknown_tool") is True


class TestLocalSandboxProvider:
    @pytest.fixture
    def provider(self, tmp_path):
        return LocalSandboxProvider({"workspace_dir": str(tmp_path)})

    @pytest.fixture
    def workspace_dir(self, tmp_path):
        return str(tmp_path / "workspace")

    @pytest.mark.asyncio
    async def test_is_available(self, provider):
        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_create_sandbox(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        assert sandbox_id == "local-test-thread"

    @pytest.mark.asyncio
    async def test_start_sandbox(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.start_sandbox(sandbox_id)
        info = await provider.get_sandbox_info(sandbox_id)
        assert info.vm_state == VMState.RUNNING

    @pytest.mark.asyncio
    async def test_stop_sandbox(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.start_sandbox(sandbox_id)
        await provider.stop_sandbox(sandbox_id)
        info = await provider.get_sandbox_info(sandbox_id)
        assert info.vm_state == VMState.STOPPED

    @pytest.mark.asyncio
    async def test_execute_command(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.start_sandbox(sandbox_id)
        result = await provider.execute(sandbox_id, "echo hello")
        assert result.exit_code == 0
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_command_failure(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.start_sandbox(sandbox_id)
        result = await provider.execute(sandbox_id, "false")
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_destroy_sandbox(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.destroy_sandbox(sandbox_id)
        with pytest.raises(ValueError):
            await provider.get_sandbox_info(sandbox_id)

    @pytest.mark.asyncio
    async def test_get_sandbox_info(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        info = await provider.get_sandbox_info(sandbox_id)
        assert info.sandbox_id == sandbox_id
        assert info.platform == "local"
        assert info.strategy == SandboxStrategy.LOCAL

    @pytest.mark.asyncio
    async def test_command_blocklist(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.start_sandbox(sandbox_id)
        with pytest.raises(PermissionError):
            await provider.execute(sandbox_id, "rm -rf /")

    @pytest.mark.asyncio
    async def test_audit_log(self, provider, workspace_dir):
        sandbox_id = await provider.create_sandbox("test-thread", {"workspace_dir": workspace_dir})
        await provider.start_sandbox(sandbox_id)
        await provider.execute(sandbox_id, "echo audited")
        entries = _audit_log.get_entries(sandbox_id)
        assert len(entries) > 0
        assert entries[-1]["mode"] == "local"
        assert "echo audited" in entries[-1]["command"]

    @pytest.mark.asyncio
    async def test_workspace_dir_created(self, provider):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = os.path.join(tmpdir, "workspace")
            sandbox_id = await provider.create_sandbox(
                "test-thread", {"workspace_dir": workspace}
            )
            assert os.path.isdir(workspace)


class TestVMSandboxProvider:
    def test_detect_platform_macos(self):
        with patch("platform.system", return_value="Darwin"):
            provider = VMSandboxProvider()
            assert provider.platform == "macos"

    def test_detect_platform_windows(self):
        with patch("platform.system", return_value="Windows"):
            provider = VMSandboxProvider()
            assert provider.platform == "windows"

    def test_detect_platform_linux(self):
        with patch("platform.system", return_value="Linux"):
            provider = VMSandboxProvider()
            assert provider.platform == "linux"

    def test_detect_platform_unsupported(self):
        with patch("platform.system", return_value="FreeBSD"):
            with pytest.raises(RuntimeError, match="不支持的平台"):
                VMSandboxProvider()

    def test_explicit_platform(self):
        provider = VMSandboxProvider(platform="macos")
        assert provider.platform == "macos"

    @pytest.mark.asyncio
    async def test_is_available_with_unsupported_platform(self):
        provider = VMSandboxProvider(platform="macos")
        with patch.object(provider, "_get_provider", side_effect=ImportError("no module")):
            assert await provider.is_available() is False


class TestMacOSVMProvider:
    @pytest.mark.asyncio
    async def test_is_available_no_cli(self):
        from deerflow.sandbox.macos_vm import MacOSVMProvider

        provider = MacOSVMProvider(cli_path="/nonexistent/DeerFlowSandboxCLI")
        assert await provider.is_available() is False


class TestWSL2VMProvider:
    @pytest.mark.asyncio
    async def test_is_available_no_wsl(self):
        from deerflow.sandbox.wsl2_vm import WSL2VMProvider

        provider = WSL2VMProvider()
        with patch("shutil.which", return_value=None):
            assert await provider.is_available() is False


class TestFirecrackerVMProvider:
    @pytest.mark.asyncio
    async def test_is_available_no_kvm(self):
        from deerflow.sandbox.firecracker_vm import FirecrackerVMProvider

        provider = FirecrackerVMProvider()
        with patch("os.path.exists", return_value=False):
            assert await provider.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_no_kvm_access(self):
        from deerflow.sandbox.firecracker_vm import FirecrackerVMProvider

        provider = FirecrackerVMProvider()
        with patch("os.path.exists", return_value=True), \
             patch("os.access", return_value=False):
            assert await provider.is_available() is False


class TestFallbackManager:
    @pytest.mark.asyncio
    async def test_initialize_falls_to_local(self):
        manager = FallbackManager({})
        with patch.object(manager, "_create_provider", side_effect=lambda t: LocalSandboxProvider() if t == "local" else None):
            await manager.initialize()
            assert manager.active_provider_type == "local"

    @pytest.mark.asyncio
    async def test_initialize_selects_vm_when_available(self):
        manager = FallbackManager({})
        mock_vm = AsyncMock(spec=CrossPlatformSandboxProvider)
        mock_vm.is_available.return_value = True

        def create_provider(provider_type):
            if provider_type == "vm":
                return mock_vm
            return None

        with patch.object(manager, "_create_provider", side_effect=create_provider):
            await manager.initialize()
            assert manager.active_provider_type == "vm"

    @pytest.mark.asyncio
    async def test_fallback_to_local(self):
        manager = FallbackManager({})
        mock_vm = AsyncMock(spec=CrossPlatformSandboxProvider)
        mock_vm.is_available.return_value = False
        mock_local = LocalSandboxProvider()

        def create_provider(provider_type):
            if provider_type == "vm":
                return mock_vm
            if provider_type == "local":
                return mock_local
            return None

        with patch.object(manager, "_create_provider", side_effect=create_provider):
            await manager.initialize()
            assert manager.active_provider_type == "local"

    @pytest.mark.asyncio
    async def test_fallback_method(self):
        manager = FallbackManager({})
        mock_vm = AsyncMock(spec=CrossPlatformSandboxProvider)
        mock_vm.is_available.return_value = True
        mock_local = LocalSandboxProvider()

        manager._providers = {"vm": mock_vm, "local": mock_local}
        manager._active_provider = "vm"

        result = await manager.fallback("VM 启动失败")
        assert manager.active_provider_type == "local"
        assert result is mock_local
        assert len(manager.get_fallback_history()) == 1
        assert manager.get_fallback_history()[0]["reason"] == "VM 启动失败"

    @pytest.mark.asyncio
    async def test_fallback_history(self):
        manager = FallbackManager({})
        mock_vm = AsyncMock(spec=CrossPlatformSandboxProvider)
        mock_local = LocalSandboxProvider()

        manager._providers = {"vm": mock_vm, "local": mock_local}
        manager._active_provider = "vm"

        await manager.fallback("原因1")
        history = manager.get_fallback_history()
        assert len(history) == 1
        assert history[0]["from"] == "vm"
        assert history[0]["to"] == "local"

    @pytest.mark.asyncio
    async def test_should_auto_fallback(self):
        manager = FallbackManager({})
        assert manager.should_auto_fallback() is False

        manager.record_vm_failure()
        manager.record_vm_failure()
        manager.record_vm_failure()
        assert manager.should_auto_fallback() is True

    @pytest.mark.asyncio
    async def test_should_auto_fallback_timeout(self):
        manager = FallbackManager({})
        manager.record_vm_timeout(30.0)
        assert manager.should_auto_fallback() is False
        manager.record_vm_timeout(31.0)
        assert manager.should_auto_fallback() is True

    @pytest.mark.asyncio
    async def test_try_recover_success(self):
        manager = FallbackManager({})
        mock_vm = AsyncMock(spec=CrossPlatformSandboxProvider)
        mock_vm.is_available.return_value = True

        with patch.object(manager, "_create_provider", return_value=mock_vm):
            result = await manager.try_recover("vm")
            assert result is True
            assert manager.active_provider_type == "vm"

    @pytest.mark.asyncio
    async def test_try_recover_failure(self):
        manager = FallbackManager({})
        mock_vm = AsyncMock(spec=CrossPlatformSandboxProvider)
        mock_vm.is_available.return_value = False

        with patch.object(manager, "_create_provider", return_value=mock_vm):
            result = await manager.try_recover("vm")
            assert result is False

    @pytest.mark.asyncio
    async def test_get_provider_always_returns(self):
        manager = FallbackManager({})
        provider = await manager.get_provider()
        assert isinstance(provider, LocalSandboxProvider)


class TestCrossPlatformAbstraction:
    @pytest.mark.asyncio
    async def test_base_class_methods_raise(self):
        class MinimalProvider(CrossPlatformSandboxProvider):
            async def create_sandbox(self, thread_id, config):
                return ""
            async def start_sandbox(self, sandbox_id):
                pass
            async def stop_sandbox(self, sandbox_id):
                pass
            async def execute(self, sandbox_id, command, timeout=300, cwd=None):
                return CommandResult(exit_code=0, stdout="", stderr="")
            async def get_sandbox_info(self, sandbox_id):
                return SandboxInfo(
                    sandbox_id="", platform="", strategy=SandboxStrategy.LOCAL,
                    vm_state=VMState.STOPPED, memory_mb=0, cpu_count=0,
                    workspace_dir="",
                )
            async def destroy_sandbox(self, sandbox_id):
                pass
            async def is_available(self):
                return True

        provider = MinimalProvider()
        with pytest.raises(NotImplementedError):
            await provider.pause_sandbox("test")
        with pytest.raises(NotImplementedError):
            await provider.resume_sandbox("test")
        with pytest.raises(NotImplementedError):
            await provider.save_snapshot("test", "snap")
        with pytest.raises(NotImplementedError):
            await provider.restore_snapshot("test", "snap")
        assert await provider.list_snapshots("test") == []
        with pytest.raises(NotImplementedError):
            await provider.upload_file("test", "/a", "/b")
        with pytest.raises(NotImplementedError):
            await provider.download_file("test", "/a", "/b")


class TestVMState:
    def test_vm_state_values(self):
        assert VMState.STOPPED == "stopped"
        assert VMState.STARTING == "starting"
        assert VMState.RUNNING == "running"
        assert VMState.PAUSED == "paused"
        assert VMState.ERROR == "error"


class TestCommandResult:
    def test_command_result_defaults(self):
        result = CommandResult(exit_code=0, stdout="out", stderr="err")
        assert result.timed_out is False

    def test_command_result_timeout(self):
        result = CommandResult(exit_code=-1, stdout="", stderr="timeout", timed_out=True)
        assert result.timed_out is True


class TestSandboxInfo:
    def test_sandbox_info_extra(self):
        info = SandboxInfo(
            sandbox_id="test",
            platform="local",
            strategy=SandboxStrategy.LOCAL,
            vm_state=VMState.RUNNING,
            memory_mb=512,
            cpu_count=1,
            workspace_dir="/tmp",
            extra={"key": "value"},
        )
        assert info.extra["key"] == "value"
