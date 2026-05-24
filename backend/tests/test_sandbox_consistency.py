import os
import platform
import re
from typing import Any, Callable, Coroutine

import pytest

from deerflow.sandbox.base import CommandResult, CrossPlatformSandboxProvider, VMState

KVM_AVAILABLE = os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)
IS_LINUX = platform.system() == "Linux"
IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"

EXPECTED_PYTHON_VERSION = "3.12"
EXPECTED_NODE_MAJOR = "20"
EXPECTED_COMPAT_VERSION = "1"
EXPECTED_MIN_APP_VERSION = "0.1.0"
EXPECTED_SANDBOX_USER = "sandbox"
EXPECTED_WORKSPACE_DIR = "/home/sandbox/workspace"
EXPECTED_DEERFLOW_VERSION_PATH = "/etc/deerflow-version"

REQUIRED_TOOLS = ["bash", "git", "curl", "wget", "python3", "node"]

DEERFLOW_VERSION_FIELDS = [
    "DEERFLOW_VERSION",
    "IMAGE_FORMAT",
    "BUILD_DATE",
    "COMPAT_VERSION",
    "MIN_APP_VERSION",
    "PYTHON_VERSION",
    "NODE_VERSION",
    "UBUNTU_VERSION",
]

REQUIRED_ENV_VARS = ["LANG", "LC_ALL"]


class ConsistencyTestHelper:
    def __init__(self, execute: Callable[[str], Coroutine[Any, Any, CommandResult]]):
        self._execute = execute

    async def run(self, command: str) -> CommandResult:
        return await self._execute(command)

    async def assert_command_succeeds(self, command: str, msg: str = "") -> CommandResult:
        result = await self.run(command)
        assert result.exit_code == 0, (
            f"命令执行失败: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}\n{msg}"
        )
        return result

    async def assert_tool_available(self, tool: str) -> None:
        result = await self.run(f"which {tool}")
        assert result.exit_code == 0, f"工具 {tool} 不可用: {result.stderr}"

    async def assert_python_version(self, expected: str) -> None:
        result = await self.run("python3 --version")
        assert result.exit_code == 0, f"获取 Python 版本失败: {result.stderr}"
        version_str = result.stdout.strip()
        major_minor = ".".join(version_str.split()[1].split(".")[:2])
        assert major_minor == expected, (
            f"Python 版本不匹配: 期望 {expected}, 实际 {major_minor} (完整: {version_str})"
        )

    async def assert_node_version(self, expected_major: str) -> None:
        result = await self.run("node --version")
        assert result.exit_code == 0, f"获取 Node.js 版本失败: {result.stderr}"
        version_str = result.stdout.strip()
        major = version_str.lstrip("v").split(".")[0]
        assert major == expected_major, (
            f"Node.js 版本不匹配: 期望 v{expected_major}.x, 实际 {version_str}"
        )

    async def assert_user_exists(self, username: str) -> None:
        result = await self.run(f"id {username}")
        assert result.exit_code == 0, f"用户 {username} 不存在: {result.stderr}"

    async def assert_user_home_writable(self, username: str) -> None:
        result = await self.run(f"su - {username} -c 'touch ~/__consistency_test__ && rm ~/__consistency_test__'")
        assert result.exit_code == 0, f"用户 {username} 家目录不可写: {result.stderr}"

    async def assert_directory_exists(self, path: str) -> None:
        result = await self.run(f"test -d {path}")
        assert result.exit_code == 0, f"目录 {path} 不存在"

    async def assert_directory_writable(self, path: str) -> None:
        result = await self.run(
            f"test -d {path} && touch {path}/__consistency_write_test__ && rm {path}/__consistency_write_test__"
        )
        assert result.exit_code == 0, f"目录 {path} 不可写"

    async def read_deerflow_version(self) -> dict[str, str]:
        result = await self.run(f"cat {EXPECTED_DEERFLOW_VERSION_PATH}")
        assert result.exit_code == 0, f"读取 {EXPECTED_DEERFLOW_VERSION_PATH} 失败: {result.stderr}"
        entries: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                entries[key.strip()] = value.strip().strip('"').strip("'")
        return entries

    async def assert_deerflow_version_format(self) -> dict[str, str]:
        entries = await self.read_deerflow_version()
        missing = [f for f in DEERFLOW_VERSION_FIELDS if f not in entries]
        assert not missing, f"{EXPECTED_DEERFLOW_VERSION_PATH} 缺少字段: {missing}"
        return entries

    async def assert_compat_version(self, expected: str) -> None:
        entries = await self.read_deerflow_version()
        actual = entries.get("COMPAT_VERSION", "")
        assert actual == expected, f"COMPAT_VERSION 不匹配: 期望 {expected}, 实际 {actual}"

    async def assert_min_app_version_present(self) -> None:
        entries = await self.read_deerflow_version()
        min_ver = entries.get("MIN_APP_VERSION", "")
        assert min_ver, "MIN_APP_VERSION 缺失"
        semver_pattern = r"^\d+\.\d+\.\d+"
        assert re.match(semver_pattern, min_ver), f"MIN_APP_VERSION 格式无效: {min_ver}"

    async def assert_env_var_set(self, var: str) -> None:
        result = await self.run(f"echo '${{{var}}}'")
        assert result.exit_code == 0, f"读取环境变量 {var} 失败"
        value = result.stdout.strip()
        assert value, f"环境变量 {var} 未设置或为空"

    async def assert_env_var_utf8(self, var: str) -> None:
        result = await self.run(f"echo '${{{var}}}'")
        assert result.exit_code == 0, f"读取环境变量 {var} 失败"
        value = result.stdout.strip()
        if value:
            assert "UTF-8" in value.upper() or "utf8" in value.lower() or "C" in value, (
                f"环境变量 {var} 值 {value} 不符合 UTF-8 区域设置约定"
            )


def _macos_available() -> bool:
    if not IS_MACOS:
        return False
    try:
        from deerflow.sandbox.macos_vm import MacOSVMProvider

        provider = MacOSVMProvider()
        import asyncio

        return asyncio.get_event_loop().run_until_complete(provider.is_available())
    except Exception:
        return False


def _wsl2_available() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        from deerflow.sandbox.wsl2_vm import WSL2VMProvider

        provider = WSL2VMProvider()
        import asyncio

        return asyncio.get_event_loop().run_until_complete(provider.is_available())
    except Exception:
        return False


def _firecracker_available() -> bool:
    if not IS_LINUX or not KVM_AVAILABLE:
        return False
    try:
        from deerflow.sandbox.firecracker_vm import FirecrackerVMProvider

        provider = FirecrackerVMProvider()
        import asyncio

        return asyncio.get_event_loop().run_until_complete(provider.is_available())
    except Exception:
        return False


def _get_available_platforms() -> list[str]:
    platforms = []
    if _firecracker_available():
        platforms.append("linux")
    if _macos_available():
        platforms.append("macos")
    if _wsl2_available():
        platforms.append("windows")
    return platforms


_AVAILABLE_PLATFORMS = _get_available_platforms()


def _platform_skip_reason(p: str) -> str:
    reasons = {
        "linux": "Linux Firecracker 需要 KVM 支持",
        "macos": "macOS Virtualization.framework 沙箱不可用",
        "windows": "Windows WSL2 沙箱不可用",
    }
    return reasons.get(p, f"平台 {p} 不可用")


async def _create_provider_for_platform(p: str) -> CrossPlatformSandboxProvider:
    if p == "linux":
        from deerflow.sandbox.firecracker_vm import FirecrackerVMProvider

        return FirecrackerVMProvider()
    elif p == "macos":
        from deerflow.sandbox.macos_vm import MacOSVMProvider

        return MacOSVMProvider()
    elif p == "windows":
        from deerflow.sandbox.wsl2_vm import WSL2VMProvider

        return WSL2VMProvider()
    raise ValueError(f"不支持的平台: {p}")


@pytest.fixture(params=_AVAILABLE_PLATFORMS, ids=lambda p: f"{p}-sandbox")
def sandbox_platform(request):
    return request.param


@pytest.fixture
async def sandbox_helper(sandbox_platform):
    provider = await _create_provider_for_platform(sandbox_platform)
    sandbox_id = await provider.create_sandbox(
        "consistency-test",
        {"workspace_dir": "/tmp/deerflow-consistency-test-workspace"},
    )
    await provider.start_sandbox(sandbox_id)

    async def execute(command: str) -> CommandResult:
        return await provider.execute(sandbox_id, command)

    helper = ConsistencyTestHelper(execute)
    yield helper

    try:
        await provider.stop_sandbox(sandbox_id)
        await provider.destroy_sandbox(sandbox_id)
    except Exception:
        pass


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxToolAvailability:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool", REQUIRED_TOOLS)
    async def test_required_tool_available(self, sandbox_helper, tool):
        await sandbox_helper.assert_tool_available(tool)


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxLanguageRuntimes:
    @pytest.mark.asyncio
    async def test_python_version(self, sandbox_helper):
        await sandbox_helper.assert_python_version(EXPECTED_PYTHON_VERSION)

    @pytest.mark.asyncio
    async def test_node_version(self, sandbox_helper):
        await sandbox_helper.assert_node_version(EXPECTED_NODE_MAJOR)

    @pytest.mark.asyncio
    async def test_python_can_execute_script(self, sandbox_helper):
        result = await sandbox_helper.run("python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)'")
        assert result.exit_code == 0, f"Python 脚本执行失败: {result.stderr}"
        parts = result.stdout.strip().split()
        assert parts[0] == EXPECTED_PYTHON_VERSION.split(".")[0]
        assert parts[1] == EXPECTED_PYTHON_VERSION.split(".")[1]

    @pytest.mark.asyncio
    async def test_node_can_execute_script(self, sandbox_helper):
        result = await sandbox_helper.run("node -e 'console.log(process.versions.node.split(\".\")[0])'")
        assert result.exit_code == 0, f"Node.js 脚本执行失败: {result.stderr}"
        assert result.stdout.strip() == EXPECTED_NODE_MAJOR


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxUser:
    @pytest.mark.asyncio
    async def test_sandbox_user_exists(self, sandbox_helper):
        await sandbox_helper.assert_user_exists(EXPECTED_SANDBOX_USER)

    @pytest.mark.asyncio
    async def test_sandbox_user_home_writable(self, sandbox_helper):
        await sandbox_helper.assert_user_home_writable(EXPECTED_SANDBOX_USER)

    @pytest.mark.asyncio
    async def test_sandbox_user_is_not_root(self, sandbox_helper):
        result = await sandbox_helper.run(f"id -u {EXPECTED_SANDBOX_USER}")
        assert result.exit_code == 0
        uid = int(result.stdout.strip())
        assert uid != 0, f"用户 {EXPECTED_SANDBOX_USER} 不应为 root (uid=0)"


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxWorkspace:
    @pytest.mark.asyncio
    async def test_workspace_directory_exists(self, sandbox_helper):
        await sandbox_helper.assert_directory_exists(EXPECTED_WORKSPACE_DIR)

    @pytest.mark.asyncio
    async def test_workspace_directory_writable(self, sandbox_helper):
        await sandbox_helper.assert_directory_writable(EXPECTED_WORKSPACE_DIR)

    @pytest.mark.asyncio
    async def test_workspace_is_home_subdirectory(self, sandbox_helper):
        result = await sandbox_helper.run(f"realpath {EXPECTED_WORKSPACE_DIR}")
        assert result.exit_code == 0
        workspace_real = result.stdout.strip()
        assert workspace_real.startswith(f"/home/{EXPECTED_SANDBOX_USER}/"), (
            f"工作目录 {workspace_real} 不在用户家目录下"
        )


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestDeerflowVersionFile:
    @pytest.mark.asyncio
    async def test_deerflow_version_file_exists(self, sandbox_helper):
        result = await sandbox_helper.run(f"test -f {EXPECTED_DEERFLOW_VERSION_PATH}")
        assert result.exit_code == 0, f"{EXPECTED_DEERFLOW_VERSION_PATH} 不存在"

    @pytest.mark.asyncio
    async def test_deerflow_version_format(self, sandbox_helper):
        await sandbox_helper.assert_deerflow_version_format()

    @pytest.mark.asyncio
    async def test_compat_version(self, sandbox_helper):
        await sandbox_helper.assert_compat_version(EXPECTED_COMPAT_VERSION)

    @pytest.mark.asyncio
    async def test_min_app_version_present(self, sandbox_helper):
        await sandbox_helper.assert_min_app_version_present()

    @pytest.mark.asyncio
    async def test_python_version_in_version_file(self, sandbox_helper):
        entries = await sandbox_helper.read_deerflow_version()
        python_ver = entries.get("PYTHON_VERSION", "")
        assert python_ver.startswith(EXPECTED_PYTHON_VERSION), (
            f"版本文件中 PYTHON_VERSION={python_ver} 与期望 {EXPECTED_PYTHON_VERSION} 不匹配"
        )

    @pytest.mark.asyncio
    async def test_node_version_in_version_file(self, sandbox_helper):
        entries = await sandbox_helper.read_deerflow_version()
        node_ver = entries.get("NODE_VERSION", "")
        assert node_ver.startswith(EXPECTED_NODE_MAJOR), (
            f"版本文件中 NODE_VERSION={node_ver} 与期望 {EXPECTED_NODE_MAJOR} 不匹配"
        )


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxEnvironment:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("var", REQUIRED_ENV_VARS)
    async def test_required_env_var_set(self, sandbox_helper, var):
        await sandbox_helper.assert_env_var_set(var)

    @pytest.mark.asyncio
    async def test_lang_utf8(self, sandbox_helper):
        await sandbox_helper.assert_env_var_utf8("LANG")

    @pytest.mark.asyncio
    async def test_lc_all_utf8(self, sandbox_helper):
        await sandbox_helper.assert_env_var_utf8("LC_ALL")

    @pytest.mark.asyncio
    async def test_path_includes_standard_dirs(self, sandbox_helper):
        result = await sandbox_helper.run("echo $PATH")
        assert result.exit_code == 0
        path_dirs = result.stdout.strip().split(":")
        standard_dirs = ["/usr/local/bin", "/usr/bin", "/bin"]
        for d in standard_dirs:
            assert d in path_dirs, f"标准路径 {d} 不在 PATH 中"

    @pytest.mark.asyncio
    async def test_home_env_set(self, sandbox_helper):
        result = await sandbox_helper.run("echo $HOME")
        assert result.exit_code == 0
        home = result.stdout.strip()
        assert home == f"/home/{EXPECTED_SANDBOX_USER}", f"HOME={home}, 期望 /home/{EXPECTED_SANDBOX_USER}"


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxCommandConsistency:
    @pytest.mark.asyncio
    async def test_echo(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("echo hello")
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_pwd(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("pwd")
        assert result.stdout.strip()

    @pytest.mark.asyncio
    async def test_ls(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("ls /")
        assert "home" in result.stdout or "etc" in result.stdout

    @pytest.mark.asyncio
    async def test_cat(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("cat /etc/os-release")
        assert "Ubuntu" in result.stdout or "ubuntu" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_mkdir_and_rmdir(self, sandbox_helper):
        test_dir = f"{EXPECTED_WORKSPACE_DIR}/__consistency_mkdir_test__"
        await sandbox_helper.assert_command_succeeds(f"mkdir -p {test_dir}")
        result = await sandbox_helper.run(f"test -d {test_dir}")
        assert result.exit_code == 0
        await sandbox_helper.assert_command_succeeds(f"rmdir {test_dir}")

    @pytest.mark.asyncio
    async def test_pipe(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("echo 'hello world' | tr ' ' '_'")
        assert "hello_world" in result.stdout

    @pytest.mark.asyncio
    async def test_redirect(self, sandbox_helper):
        test_file = f"{EXPECTED_WORKSPACE_DIR}/__consistency_redirect_test__.txt"
        await sandbox_helper.assert_command_succeeds(f"echo 'test content' > {test_file}")
        result = await sandbox_helper.assert_command_succeeds(f"cat {test_file}")
        assert "test content" in result.stdout
        await sandbox_helper.assert_command_succeeds(f"rm -f {test_file}")

    @pytest.mark.asyncio
    async def test_exit_code_propagation(self, sandbox_helper):
        result = await sandbox_helper.run("exit 42")
        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_stderr_capture(self, sandbox_helper):
        result = await sandbox_helper.run("echo error_msg >&2")
        assert "error_msg" in result.stderr


@pytest.mark.skipif(not _AVAILABLE_PLATFORMS, reason="没有可用的沙箱平台")
class TestSandboxNetworkToolConsistency:
    @pytest.mark.asyncio
    async def test_curl_version(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("curl --version")
        assert "curl" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_wget_version(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("wget --version")
        assert "wget" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_git_version(self, sandbox_helper):
        result = await sandbox_helper.assert_command_succeeds("git --version")
        assert "git version" in result.stdout.lower()


class TestConsistencyTestHelperUnit:
    def test_helper_instantiation(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=0, stdout="ok", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        assert helper._execute is mock_execute

    @pytest.mark.asyncio
    async def test_assert_command_succeeds_pass(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=0, stdout="ok", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        result = await helper.assert_command_succeeds("echo ok")
        assert result.stdout == "ok"

    @pytest.mark.asyncio
    async def test_assert_command_succeeds_fail(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=1, stdout="", stderr="error")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="命令执行失败"):
            await helper.assert_command_succeeds("false")

    @pytest.mark.asyncio
    async def test_assert_tool_available_pass(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=0, stdout="/usr/bin/bash", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_tool_available("bash")

    @pytest.mark.asyncio
    async def test_assert_tool_available_fail(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=1, stdout="", stderr="not found")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="不可用"):
            await helper.assert_tool_available("nonexistent")

    @pytest.mark.asyncio
    async def test_assert_python_version_pass(self):
        async def mock_execute(cmd: str) -> CommandResult:
            if "python3 --version" in cmd:
                return CommandResult(exit_code=0, stdout="Python 3.12.4", stderr="")
            return CommandResult(exit_code=1, stdout="", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_python_version("3.12")

    @pytest.mark.asyncio
    async def test_assert_python_version_fail(self):
        async def mock_execute(cmd: str) -> CommandResult:
            if "python3 --version" in cmd:
                return CommandResult(exit_code=0, stdout="Python 3.11.0", stderr="")
            return CommandResult(exit_code=1, stdout="", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="Python 版本不匹配"):
            await helper.assert_python_version("3.12")

    @pytest.mark.asyncio
    async def test_assert_node_version_pass(self):
        async def mock_execute(cmd: str) -> CommandResult:
            if "node --version" in cmd:
                return CommandResult(exit_code=0, stdout="v20.11.0", stderr="")
            return CommandResult(exit_code=1, stdout="", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_node_version("20")

    @pytest.mark.asyncio
    async def test_assert_node_version_fail(self):
        async def mock_execute(cmd: str) -> CommandResult:
            if "node --version" in cmd:
                return CommandResult(exit_code=0, stdout="v18.19.0", stderr="")
            return CommandResult(exit_code=1, stdout="", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="Node.js 版本不匹配"):
            await helper.assert_node_version("20")

    @pytest.mark.asyncio
    async def test_read_deerflow_version(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = (
                "DEERFLOW_VERSION=0.1.0\n"
                "IMAGE_FORMAT=ext4\n"
                "BUILD_DATE=2025-01-01\n"
                "COMPAT_VERSION=1\n"
                "MIN_APP_VERSION=0.1.0\n"
                "PYTHON_VERSION=3.12\n"
                "NODE_VERSION=20\n"
                "UBUNTU_VERSION=24.04\n"
            )
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        entries = await helper.read_deerflow_version()
        assert entries["DEERFLOW_VERSION"] == "0.1.0"
        assert entries["COMPAT_VERSION"] == "1"
        assert entries["PYTHON_VERSION"] == "3.12"

    @pytest.mark.asyncio
    async def test_assert_deerflow_version_format_missing_field(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = "DEERFLOW_VERSION=0.1.0\nCOMPAT_VERSION=1\n"
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="缺少字段"):
            await helper.assert_deerflow_version_format()

    @pytest.mark.asyncio
    async def test_assert_compat_version(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = "COMPAT_VERSION=1\n"
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_compat_version("1")

    @pytest.mark.asyncio
    async def test_assert_compat_version_mismatch(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = "COMPAT_VERSION=2\n"
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="COMPAT_VERSION 不匹配"):
            await helper.assert_compat_version("1")

    @pytest.mark.asyncio
    async def test_assert_min_app_version_present(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = "MIN_APP_VERSION=0.1.0\n"
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_min_app_version_present()

    @pytest.mark.asyncio
    async def test_assert_min_app_version_invalid(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = "MIN_APP_VERSION=not-a-version\n"
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="格式无效"):
            await helper.assert_min_app_version_present()

    @pytest.mark.asyncio
    async def test_assert_env_var_utf8(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=0, stdout="en_US.UTF-8", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_env_var_utf8("LANG")

    @pytest.mark.asyncio
    async def test_assert_user_exists(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=0, stdout="uid=1000(sandbox) gid=1000(sandbox)", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_user_exists("sandbox")

    @pytest.mark.asyncio
    async def test_assert_user_not_exists(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=1, stdout="", stderr="no such user")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="不存在"):
            await helper.assert_user_exists("nobody_special")

    @pytest.mark.asyncio
    async def test_assert_directory_exists(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=0, stdout="", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        await helper.assert_directory_exists("/home/sandbox/workspace")

    @pytest.mark.asyncio
    async def test_assert_directory_not_exists(self):
        async def mock_execute(cmd: str) -> CommandResult:
            return CommandResult(exit_code=1, stdout="", stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        with pytest.raises(AssertionError, match="不存在"):
            await helper.assert_directory_exists("/nonexistent")

    @pytest.mark.asyncio
    async def test_read_deerflow_version_with_quotes(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = 'DEERFLOW_VERSION="0.1.0"\nCOMPAT_VERSION=\'1\'\n'
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        entries = await helper.read_deerflow_version()
        assert entries["DEERFLOW_VERSION"] == "0.1.0"
        assert entries["COMPAT_VERSION"] == "1"

    @pytest.mark.asyncio
    async def test_read_deerflow_version_with_comments(self):
        async def mock_execute(cmd: str) -> CommandResult:
            content = "# This is a comment\nDEERFLOW_VERSION=0.1.0\n\nCOMPAT_VERSION=1\n"
            return CommandResult(exit_code=0, stdout=content, stderr="")

        helper = ConsistencyTestHelper(mock_execute)
        entries = await helper.read_deerflow_version()
        assert "DEERFLOW_VERSION" in entries
        assert "COMPAT_VERSION" in entries
        assert len(entries) == 2
