# T32 - Linux Firecracker 适配

## 元信息
- **任务ID**: T32
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P4
- **预估工期**: 6 天（增加 KVM 权限处理和 rootless 备选方案）
- **依赖任务**: T29
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
实现 Linux 平台基于 Firecracker 的轻量 VM 沙箱，支持 VM 启停、命令执行、工作目录共享，**重点处理 KVM 权限问题和 rootless 备选方案**，确保无 KVM 时有合理的降级路径。

## KVM 访问要求

### KVM 权限层级
| 层级 | 条件 | Firecracker 可用性 |
|------|------|-------------------|
| 完全访问 | `/dev/kvm` 存在，当前用户有读写权限 | ✅ 完全可用 |
| 组权限 | 用户在 `kvm` 组中 | ✅ 完全可用（需重新登录） |
| 仅 root | `/dev/kvm` 仅 root 可访问 | ⚠️ 需 sudo 运行 Firecracker |
| 不存在 | `/dev/kvm` 不存在 | ❌ 不可用，需降级 |
| 云主机 | 嵌套虚拟化未启用 | ❌ 不可用，需降级 |

### KVM 模块加载
- Intel CPU: `kvm_intel` 模块
- AMD CPU: `kvm_amd` 模块
- 检测: `lsmod | grep kvm`

## 详细实现步骤

### 步骤1: 创建 Firecracker 沙箱模块
- **文件**: `backend/packages/harness/deerflow/sandbox/firecracker_vm.py`
- **操作**: 新建
- **内容**: 实现 `FirecrackerVM` 类：
  1. **类定义**：
     ```python
     class FirecrackerVM:
         def __init__(
             self,
             kernel_path: str,
             rootfs_path: str,
             workspace_dir: str,
             vcpu_count: int = 2,
             mem_size_mib: int = 2048,
         ):
             self.kernel_path = kernel_path
             self.rootfs_path = rootfs_path
             self.workspace_dir = workspace_dir
             self.vcpu_count = vcpu_count
             self.mem_size_mib = mem_size_mib
             self._process: subprocess.Popen | None = None
             self._api_socket: str = ""
             self._vm_id: str = ""
             self._ssh_client: SSHClient | None = None
             self.state: VMState = VMState.STOPPED

         async def start(self) -> None: ...
         async def execute(self, command: str, timeout: int = 300) -> CommandResult: ...
         async def stop(self) -> None: ...
         async def pause(self) -> None: ...
         async def resume(self) -> None: ...
         async def is_running(self) -> bool: ...
     ```
  2. **路径管理**：
     - kernel_path: Firecracker Linux 内核镜像（vmlinux）
     - rootfs_path: ext4 格式的根文件系统镜像
     - workspace_dir: 宿主工作目录（通过 mount 共享到 VM）
     - 所有路径通过配置或自动检测获取
  3. **资源隔离**：
     - 每个 VM 实例独立的 network namespace
     - 独立的 API socket 文件
     - 独立的日志文件
- **验收**: 类定义完整，Type hint 正确

### 步骤2: KVM 权限检测与自动修复
- **文件**: `backend/packages/harness/deerflow/sandbox/kvm_utils.py`
- **操作**: 新建
- **内容**: **核心改进：完整的 KVM 权限检测、自动修复和降级路径**：
  1. **KVM 可用性检测**：
     ```python
     @dataclass
     class KVMStatus:
         available: bool
         reason: str = ""
         can_fix: bool = False
         fix_description: str = ""
         kvm_group_exists: bool = False
         user_in_kvm_group: bool = False
         kvm_module_loaded: bool = False
         cpu_type: str = ""  # "intel" / "amd" / "unknown"

     def check_kvm_available() -> KVMStatus:
         # 1. 检查 /dev/kvm 是否存在
         if not os.path.exists("/dev/kvm"):
             # 尝试加载 KVM 模块
             cpu_type = _detect_cpu_type()
             if cpu_type == "intel":
                 _try_load_module("kvm_intel")
             elif cpu_type == "amd":
                 _try_load_module("kvm_amd")
             # 重新检查
             if not os.path.exists("/dev/kvm"):
                 return KVMStatus(
                     available=False,
                     reason="KVM 模块未加载且无法自动加载",
                     can_fix=True,
                     fix_description=f"尝试: sudo modprobe kvm_{cpu_type}",
                     cpu_type=cpu_type,
                 )

         # 2. 检查读写权限
         if not os.access("/dev/kvm", os.R_OK | os.W_OK):
             kvm_group_exists = _check_group_exists("kvm")
             user_in_kvm_group = _check_user_in_group("kvm")
             return KVMStatus(
                 available=False,
                 reason="无 /dev/kvm 读写权限",
                 can_fix=True,
                 fix_description="将当前用户加入 kvm 组: sudo usermod -aG kvm $USER",
                 kvm_group_exists=kvm_group_exists,
                 user_in_kvm_group=user_in_kvm_group,
             )

         return KVMStatus(available=True)
     ```
  2. **自动修复权限**：
     - **kvm 组设置**：
       - 检查 `kvm` 组是否存在：`getent group kvm`
       - 不存在时创建：`sudo groupadd kvm`
       - 将当前用户加入 `kvm` 组：`sudo usermod -aG kvm $USER`
       - 修改 `/dev/kvm` 权限：`sudo chmod 666 /dev/kvm`（临时方案）
       - 需要 sudo 权限，通过 polkit 弹窗请求
     - **KVM 模块加载**：
       - Intel: `sudo modprobe kvm_intel`
       - AMD: `sudo modprobe kvm_amd`
       - 持久化：`echo "kvm_intel" | sudo tee /etc/modules-load.d/kvm.conf`
     - **权限修复后提示**：
       - 加入 kvm 组后需要**重新登录**才能生效
       - 提示用户注销并重新登录
  3. **Docker 环境特殊处理**：
     - Docker 容器内需 `--device /dev/kvm` 才能使用 KVM
     - 检测是否在 Docker 内运行：`/.dockerenv` 文件存在
     - Docker 内提示正确的启动参数：`docker run --device /dev/kvm ...`
  4. **云主机嵌套虚拟化检测**：
     - 检测是否在云主机上运行：`systemd-detect-virt`
     - 云主机上检查嵌套虚拟化：`cat /sys/module/kvm_intel/parameters/nested`
     - 嵌套虚拟化未启用时提示联系云服务商
  5. **无 KVM 降级**：
     - Firecracker 无 KVM 无法运行
     - 降级到本地模式或 Docker 模式
     - 降级时通知用户原因和建议
- **验收**: KVM 不可用时有明确提示和自动修复建议；自动修复后 KVM 可用

### 步骤3: Rootless Firecracker 备选方案
- **文件**: `backend/packages/harness/deerflow/sandbox/rootless_sandbox.py`
- **操作**: 新建
- **内容**: 当 KVM 不可用时，提供 rootless 备选方案：
  1. **Docker 沙箱备选**：
     ```python
     class DockerSandboxProvider(SandboxProvider):
         """Docker 容器沙箱 — KVM 不可用时的备选方案"""

         async def is_available(self) -> bool:
             try:
                 result = await asyncio.create_subprocess_exec(
                     "docker", "info",
                     stdout=asyncio.subprocess.PIPE,
                     stderr=asyncio.subprocess.PIPE,
                 )
                 await result.wait()
                 return result.returncode == 0
             except FileNotFoundError:
                 return False

         async def create_sandbox(self, thread_id: str, config: dict) -> str:
             container_id = await self._run_container(config)
             return container_id

         async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult:
             exec_cmd = f"docker exec {sandbox_id} bash -c '{command}'"
             result = await self._run_command(exec_cmd, timeout)
             return result
     ```
  2. **Podman 沙箱备选**（rootless）：
     - Podman 天然支持 rootless 运行
     - 无需 daemon，更安全
     - 与 Docker CLI 兼容
     ```python
     class PodmanSandboxProvider(DockerSandboxProvider):
         """Podman rootless 沙箱 — 无需 root 权限"""

         async def is_available(self) -> bool:
             try:
                 result = await asyncio.create_subprocess_exec(
                     "podman", "info",
                     stdout=asyncio.subprocess.PIPE,
                     stderr=asyncio.subprocess.PIPE,
                 )
                 await result.wait()
                 return result.returncode == 0
             except FileNotFoundError:
                 return False

         def _container_cmd(self) -> str:
             return "podman"
     ```
  3. **备选方案优先级**：
     - Firecracker (KVM) > Docker > Podman > 本地模式
     - 自动检测可用性，选择最高优先级的可用方案
  4. **备选方案限制说明**：
     - Docker/Podman 隔离性弱于 Firecracker VM
     - 启动速度慢于 Firecracker（~2s vs ~500ms）
     - 资源开销更大
     - 但比本地模式安全得多
- **验收**: KVM 不可用时自动降级到 Docker/Podman 沙箱；Docker/Podman 也不可用时降级到本地模式

### 步骤4: VM 启动实现
- **文件**: `backend/packages/harness/deerflow/sandbox/firecracker_vm.py`（扩展）
- **操作**: 改造
- **内容**: 实现 `start()` 方法：
  1. **KVM 检测**：
     - 调用 `check_kvm_available()` 检测 KVM 状态
     - KVM 不可用时抛出 `KVMNotAvailableError`，附带 `KVMStatus` 信息
     - 上层捕获后可尝试自动修复或降级
  2. **准备 rootfs 副本**：
     - 为每个 VM 实例复制 rootfs 镜像（避免多实例写冲突）
     - 副本路径：`/tmp/deerflow-vm/{vm_id}/rootfs.ext4`
     - 使用 `cp --reflink=auto` 在 Btrfs 上节省空间
  3. **启动 Firecracker 进程**：
     ```python
     async def start(self):
         kvm_status = check_kvm_available()
         if not kvm_status.available:
             raise KVMNotAvailableError(kvm_status)

         self._vm_id = f"deerflow-{uuid4().hex[:8]}"
         self._api_socket = f"/tmp/deerflow-vm/{self._vm_id}/api.sock"

         self._process = subprocess.Popen(
             [self._get_firecracker_binary(), "--api-sock", self._api_socket, "--id", self._vm_id],
             stdout=subprocess.PIPE,
             stderr=subprocess.PIPE,
         )

         await self._wait_for_api(timeout=5)
         await self._configure_vm()
         await self._start_instance()
         self._ssh_client = await self._wait_for_ssh(timeout=30)
         self.state = VMState.RUNNING
     ```
  4. **VM 配置**（通过 Firecracker API）：
     - 设置 boot-source、drives、machine-config
     - 网络配置：TAP 设备 + NAT
     - vsock 设备（用于文件共享）
  5. **API 调用封装**：
     ```python
     async def _api_put(self, path: str, data: dict) -> dict:
         url = f"http://unix{self._api_socket}{path}"
         async with aiohttp.ClientSession() as session:
             async with session.put(url, json=data) as resp:
                 return await resp.json()
     ```
- **验收**: Firecracker 进程启动，VM 配置成功，实例运行

### 步骤5: 命令执行
- **文件**: `backend/packages/harness/deerflow/sandbox/firecracker_vm.py`（扩展）
- **操作**: 改造
- **内容**: 实现 `execute()` 方法：
  1. **通过 SSH 执行**：
     - 使用 `asyncssh` 库连接 VM
     - 连接参数：host 192.168.100.2、port 22、用户名 sandbox、密钥认证
  2. **流式输出**：
     - 支持 `execute_stream()` 方法，通过 async generator 返回行
  3. **超时处理**：
     - 使用 `asyncio.wait_for` 设置超时
     - 超时后发送 SIGTERM，5s 后 SIGKILL
  4. **工作目录支持**：
     - `execute(command, cwd="/home/sandbox/workspace")`
     - 通过 `cd {cwd} && {command}` 实现
- **验收**: 命令执行返回正确结果；长命令 streaming 输出正常；超时命令被正确终止

### 步骤6: 工作目录共享
- **文件**: `backend/packages/harness/deerflow/sandbox/firecracker_vm.py`（扩展）
- **操作**: 改造
- **内容**: 实现宿主与 VM 的工作目录共享：
  1. **方案选择**：
     - 方案 A（推荐）：vsock + virtiofs — 性能最优但配置复杂
     - 方案 C（简单）：SCP 文件同步 — 每次执行前后同步
  2. **vsock 方案实现**：
     - Firecracker 配置 vsock 设备
     - VM 内运行 virtiofsd
     - 宿主通过 vsock 连接 virtiofsd
  3. **简化方案（SCP 同步）**：
     - 执行命令前：将宿主工作目录文件通过 SCP 传输到 VM
     - 执行命令后：将 VM 内结果文件通过 SCP 传回宿主
     - 增量同步：基于 mtime 比较只传输变化文件
  4. **配置选项**：
     ```yaml
     sandbox:
       firecracker:
         file_sharing: "vsock"  # "vsock" | "scp"
         sync_interval: 5       # SCP 模式同步间隔（秒）
     ```
- **验收**: 宿主文件可在 VM 中访问；VM 内文件修改可同步回宿主

### 步骤7: VM 生命周期管理
- **文件**: `backend/packages/harness/deerflow/sandbox/firecracker_vm.py`（扩展）
- **操作**: 改造
- **内容**: 实现完整的 VM 生命周期管理：
  1. **stop()**：优雅关机 → 超时 SIGKILL → 清理资源
  2. **pause() / resume()**：通过 Firecracker API
  3. **快照**：Firecracker 原生支持快照保存/恢复
  4. **健康检查**：定期执行 `echo health` 检查 VM 可用性
  5. **资源清理**：`__del__`、`atexit`、信号处理确保进程终止
- **验收**: VM 启动/停止/暂停/恢复生命周期完整；快照保存/恢复正常

### 步骤8: kvm 用户组设置脚本
- **文件**: `desktop/scripts/setup-kvm.sh`
- **操作**: 新建
- **内容**: 一键设置 KVM 访问权限的脚本（供启动向导调用）：
  ```bash
  #!/bin/bash
  set -euo pipefail

  echo "=== DeerFlow KVM 权限设置 ==="

  # 1. 检测 CPU 类型
  CPU_TYPE=$(grep -m1 'vendor_id' /proc/cpuinfo | awk '{print $3}')
  if [ "$CPU_TYPE" = "GenuineIntel" ]; then
      KVM_MODULE="kvm_intel"
  elif [ "$CPU_TYPE" = "AuthenticAMD" ]; then
      KVM_MODULE="kvm_amd"
  else
      echo "未知 CPU 类型，无法自动加载 KVM 模块"
      exit 1
  fi

  # 2. 加载 KVM 模块
  if ! lsmod | grep -q "^kvm"; then
      echo "加载 KVM 模块: $KVM_MODULE"
      sudo modprobe "$KVM_MODULE"
      echo "$KVM_MODULE" | sudo tee /etc/modules-load.d/kvm.conf
  fi

  # 3. 创建 kvm 组（如不存在）
  if ! getent group kvm > /dev/null 2>&1; then
      echo "创建 kvm 组"
      sudo groupadd kvm
  fi

  # 4. 将当前用户加入 kvm 组
  if ! groups | grep -q kvm; then
      echo "将用户 $USER 加入 kvm 组"
      sudo usermod -aG kvm "$USER"
      echo "⚠️  需要重新登录才能生效"
  fi

  # 5. 设置 /dev/kvm 权限
  if [ -e /dev/kvm ]; then
      sudo chmod 666 /dev/kvm 2>/dev/null || true
  fi

  echo "KVM 权限设置完成"
  ```
- **验收**: 脚本执行后当前用户可访问 `/dev/kvm`；重新登录后权限持久化

### 步骤9: 构建最小 rootfs
- **文件**: `scripts/build-vm-image/build-firecracker.sh`
- **操作**: 新建
- **内容**: 构建 Firecracker 最小 rootfs 镜像：
  1. **构建流程**：
     - 使用 Docker 构建基础环境
     - 导出文件系统
     - 创建 ext4 镜像
     - 复制文件到镜像
  2. **rootfs 内容**：
     - Ubuntu 24.04 最小安装
     - Python 3.12 + pip
     - Node.js 20 LTS
     - bash, git, curl, wget, build-essential
     - OpenSSH Server（用于命令执行）
     - sandbox 用户（UID 1000）
  3. **大小优化**：
     - 清理 apt/pip 缓存
     - 删除 locale、doc、man
     - 使用 strip 处理 ELF 二进制
     - 目标大小：~40MB（ext4 镜像，非压缩）
  4. **内核构建**：
     - 使用 Firecracker 推荐的最小内核配置
     - 下载预编译内核或从源码构建
     - 内核路径：`resources/vm-images/vmlinux`
- **验收**: 构建的 rootfs.ext4 可用于 Firecracker 启动 VM，大小 < 50MB

### 步骤10: Ubuntu 22.04/24.04 兼容测试
- **文件**: `backend/tests/test_firecracker_vm.py`
- **操作**: 新建
- **内容**: 编写 Firecracker VM 兼容性测试：
  1. **KVM 可用时**：
     - VM 启动/停止
     - 命令执行
     - 文件共享
     - 快照保存/恢复
  2. **KVM 不可用时**：
     - 降级到 Docker/Podman 沙箱
     - 降级到本地模式
     - 提示信息正确
  3. **KVM 权限修复测试**：
     - 用户不在 kvm 组 → 自动修复 → 重新登录后可用
     - KVM 模块未加载 → 自动加载 → 可用
  4. **多实例并行**：
     - 同时启动 2-3 个 VM 实例
     - 各实例命令执行独立
  5. **资源限制**：
     - 1 vCPU + 512MB 内存
     - 2 vCPU + 2048MB 内存
  6. **需要标记**：
     - `@pytest.mark.skipif(not os.path.exists("/dev/kvm"), reason="KVM not available")`
     - CI 中在支持 KVM 的 runner 上运行
- **验收**: 在 Ubuntu 22.04 和 24.04 上所有测试通过

## 验收标准
- [ ] FirecrackerVM 类可启动 VM，命令执行返回正确结果
- [ ] VM 生命周期（start/stop/pause/resume）完整
- [ ] 快照保存/恢复功能正常
- [ ] 工作目录文件共享正常（至少 SCP 模式）
- [ ] **KVM 不可用时有明确提示、自动修复建议和降级方案**
- [ ] **kvm 组设置脚本可一键修复权限问题**
- [ ] **Docker/Podman 沙箱备选方案在无 KVM 时可用**
- [ ] 最小 rootfs 镜像可构建且大小 < 50MB
- [ ] 在 Ubuntu 22.04 和 24.04 上测试通过
- [ ] 多 VM 实例并行运行互不干扰
- [ ] 进程意外退出时资源正确清理

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | FirecrackerVM.__init__() | 参数正确保存，状态为 STOPPED |
| 单元测试 | check_kvm_available() KVM 可用 | 返回 available=True |
| 单元测试 | check_kvm_available() KVM 不可用 | 返回 available=False 附带原因和修复建议 |
| 单元测试 | check_kvm_available() 用户不在 kvm 组 | 返回 can_fix=True, fix_description 含 usermod 命令 |
| 单元测试 | DockerSandboxProvider.is_available() Docker 已安装 | 返回 True |
| 单元测试 | PodmanSandboxProvider.is_available() Podman 已安装 | 返回 True |
| 集成测试 | VM 启动 → 命令执行 → 停止 | 完整生命周期正常 |
| 集成测试 | VM 快照保存 → 恢复 | 恢复后状态与快照时一致 |
| 集成测试 | 多 VM 实例并行 | 各实例命令执行独立，无冲突 |
| 集成测试 | SCP 文件同步 | 宿主→VM 和 VM→宿主 文件同步正确 |
| 集成测试 | KVM 权限修复 | 执行修复脚本后 KVM 可用 |
| 降级测试 | KVM 不可用 → Docker 沙箱 | 命令执行正常，隔离性弱于 VM |
| 降级测试 | KVM + Docker 均不可用 → 本地模式 | 命令执行正常，无隔离 |
| E2E 测试 | 完整沙箱流程 | 启动 VM → 执行代码 → 获取结果 → 停止 |
| 边界测试 | 命令执行超时 | 超时后命令被终止，返回超时错误 |
| 边界测试 | KVM 权限不足 | 自动修复或降级到 Docker/本地模式 |
| 边界测试 | VM 进程意外崩溃 | 资源清理，可重新启动 |
| 边界测试 | Docker 容器内运行 | 检测到 Docker 环境，提示正确参数 |
| 性能测试 | VM 启动时间 | < 2s |
| 性能测试 | 命令执行延迟 | < 100ms（不含命令本身耗时） |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| KVM 在某些云主机上不可用 | 高 | **提供 Docker/Podman 备选方案**；文档说明哪些云主机支持嵌套虚拟化 |
| KVM 权限问题导致用户无法使用 | 高 | **一键权限修复脚本**；自动检测并提示修复；kvm 组设置 |
| Firecracker vsock 文件共享性能差 | 中 | 使用 SCP 同步作为备选；对大文件项目使用增量同步 |
| rootfs 构建体积过大 | 中 | 使用 Alpine Linux 作为基础；多阶段构建 |
| Firecracker API 版本兼容性 | 低 | 固定 Firecracker 版本；API 调用做版本适配 |
| vmlinux 内核版本与 rootfs 不兼容 | 中 | 使用 Firecracker 官方推荐的内核版本和配置 |
| 并行 VM 实例资源竞争 | 中 | 限制最大并行数；监控宿主资源使用 |
| systemd 在 Firecracker 中不工作 | 中 | 使用 sysvinit 或直接启动 SSH 服务 |
| Docker/Podman 备选方案性能差 | 中 | 文档说明备选方案限制；推荐用户启用 KVM 获得最佳体验 |
| AppImage 内运行 Firecracker 权限问题 | 中 | AppImage 需要 `/dev/kvm` 访问权限；安装说明文档 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.5.3 Linux Firecracker 轻量VM、7.6 VM 镜像构建）
- Firecracker 官方文档: https://firecracker-microvm.github.io/
- Firecracker 快照支持: https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting.md
- Firecracker API 规范: https://github.com/firecracker-microvm/firecracker/blob/main/api_server/swagger/firecracker.yaml
- KVM 权限设置: https://help.ubuntu.com/community/KVM/Installation
- Linux KVM 嵌套虚拟化: https://www.linux-kvm.org/page/NestedGuests
