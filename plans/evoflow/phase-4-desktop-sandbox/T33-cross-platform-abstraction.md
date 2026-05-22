# T33 - 跨平台抽象层 + 自动检测降级

## 元信息
- **任务ID**: T33
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P5
- **预估工期**: 6 天（增加优雅降级和本地模式一等公民支持）
- **依赖任务**: T30, T31, T32
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
构建跨平台沙箱抽象层，统一 macOS/Windows/Linux 三平台的沙箱接口，实现平台自动检测、沙箱策略路由和**优雅降级**。**本地模式是一等公民**，当 VM 不可用时，用户仍可完整使用 DeerFlow 的所有功能，只是没有沙箱隔离。

## 设计原则

### 本地模式是一等公民
- 本地模式不是"降级体验"，而是 DeerFlow 的基础运行模式
- 所有核心功能在本地模式下必须正常工作
- VM 沙箱是"增强功能"，提供额外安全隔离
- 用户应始终可以选择本地模式，即使 VM 可用
- 本地模式下的安全措施（命令白名单、工作目录限制）必须健壮

### 优雅降级
- VM 不可用时，自动降级到本地模式，**无需用户干预**
- 降级过程必须透明：通知用户当前模式和原因
- 降级后功能不缺失，仅安全隔离级别降低
- 用户可随时在设置中切换模式

## 详细实现步骤

### 步骤1: 创建沙箱策略模块
- **文件**: `backend/packages/harness/deerflow/sandbox/strategy.py`
- **操作**: 新建
- **内容**: 实现沙箱策略路由核心逻辑：
  1. **SandboxStrategy 枚举**：
     ```python
     class SandboxStrategy(str, Enum):
         STRICT = "strict"        # 全部走 VM（类似 TRAE 模式）
         SELECTIVE = "selective"  # 仅代码/文件执行走 VM（推荐，默认）
         LOCAL = "local"          # 全部本机执行（一等公民模式）
     ```
  2. **SANDBOX_REQUIRED_TOOLS 字典**：
     ```python
     SANDBOX_REQUIRED_TOOLS: dict[str, bool] = {
         "bash": True, "write_file": True, "str_replace": True,
         "python_exec": True, "npm_install": True, "pip_install": True,
         "git_checkout": True,
         "chat": False, "clarify": False, "view_image": False,
         "tavily_search": False, "jina_reader": False,
         "read_file": False, "ls": False, "glob": False, "grep": False,
     }
     ```
  3. **SandboxRouter 类**：
     ```python
     class SandboxRouter:
         def __init__(self, strategy: SandboxStrategy = SandboxStrategy.SELECTIVE):
             self.strategy = strategy

         def should_use_sandbox(self, tool_name: str) -> bool:
             if self.strategy == SandboxStrategy.STRICT:
                 return True
             elif self.strategy == SandboxStrategy.LOCAL:
                 return False
             return SANDBOX_REQUIRED_TOOLS.get(tool_name, True)

         def get_execution_target(self, tool_name: str) -> str:
             return "vm" if self.should_use_sandbox(tool_name) else "local"

         @classmethod
         def from_config(cls, config: dict) -> "SandboxRouter":
             strategy_str = config.get("sandbox", {}).get("strategy", "selective")
             strategy = SandboxStrategy(strategy_str)
             return cls(strategy=strategy)
     ```
  4. **策略动态切换**：
     - 支持运行时切换策略（通过 API 或配置热重载）
     - 策略变更时记录日志
- **验收**: SandboxRouter 正确路由各类工具；SELECTIVE 模式下高风险工具走 VM，低风险走本机

### 步骤2: 创建 SandboxProvider 基类
- **文件**: `backend/packages/harness/deerflow/sandbox/base.py`
- **操作**: 新建
- **内容**: 定义沙箱提供者抽象基类：
  ```python
  from abc import ABC, abstractmethod
  from dataclasses import dataclass
  from enum import Enum

  class VMState(str, Enum):
      STOPPED = "stopped"
      STARTING = "starting"
      RUNNING = "running"
      PAUSED = "paused"
      ERROR = "error"

  @dataclass
  class CommandResult:
      exit_code: int
      stdout: str
      stderr: str
      timed_out: bool = False

  @dataclass
  class SandboxInfo:
      sandbox_id: str
      platform: str
      strategy: SandboxStrategy
      vm_state: VMState
      memory_mb: int
      cpu_count: int
      workspace_dir: str

  class SandboxProvider(ABC):
      @abstractmethod
      async def create_sandbox(self, thread_id: str, config: dict) -> str: ...
      @abstractmethod
      async def start_sandbox(self, sandbox_id: str) -> None: ...
      @abstractmethod
      async def stop_sandbox(self, sandbox_id: str) -> None: ...
      @abstractmethod
      async def execute(self, sandbox_id: str, command: str, timeout: int = 300, cwd: str | None = None) -> CommandResult: ...
      @abstractmethod
      async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo: ...
      @abstractmethod
      async def destroy_sandbox(self, sandbox_id: str) -> None: ...
      @abstractmethod
      async def is_available(self) -> bool: ...

      async def pause_sandbox(self, sandbox_id: str) -> None:
          raise NotImplementedError("暂停功能在此沙箱提供者上不可用")

      async def resume_sandbox(self, sandbox_id: str) -> None:
          raise NotImplementedError("恢复功能在此沙箱提供者上不可用")

      async def save_snapshot(self, sandbox_id: str, name: str) -> None:
          raise NotImplementedError("快照功能在此沙箱提供者上不可用")

      async def restore_snapshot(self, sandbox_id: str, name: str) -> None:
          raise NotImplementedError("快照功能在此沙箱提供者上不可用")

      async def list_snapshots(self, sandbox_id: str) -> list[str]:
          return []

      async def upload_file(self, sandbox_id: str, local_path: str, remote_path: str) -> None:
          raise NotImplementedError

      async def download_file(self, sandbox_id: str, remote_path: str, local_path: str) -> None:
          raise NotImplementedError
  ```
- **验收**: 抽象基类定义完整，所有方法签名和类型注解正确

### 步骤3: 创建 LocalSandboxProvider（一等公民）
- **文件**: `backend/packages/harness/deerflow/sandbox/local_sandbox.py`
- **操作**: 新建
- **内容**: 实现本地模式沙箱（**一等公民，非降级体验**）：
  1. **类定义**：
     ```python
     class LocalSandboxProvider(SandboxProvider):
         """本地模式沙箱 — 一等公民模式，直接在宿主机执行命令"""
     ```
  2. **execute() 实现**：
     - 使用 `asyncio.create_subprocess_shell` 执行命令
     - 设置工作目录、环境变量
     - 捕获 stdout/stderr
     - 支持超时
  3. **安全措施**（本地模式下）：
     - 命令白名单/黑名单（配置项）
     - 工作目录限制（不允许 `cd /` 等）
     - 环境变量隔离（使用子进程环境）
     - 超时强制终止
     - **审计日志**：所有命令执行记录到审计日志，标记为 `local` 模式
  4. **is_available() 永远返回 True**：
     - 本地模式始终可用
  5. **本地模式增强功能**：
     - 工作目录自动创建和管理
     - 临时文件清理
     - 进程资源限制（通过 `resource` 模块设置 ulimit）
     - 环境变量沙箱（仅传递白名单环境变量）
  6. **本地模式 UI 集成**：
     - 状态栏显示"本地模式"标识
     - 首次使用本地模式时提示安全说明
     - 设置页面可配置安全策略
- **验收**: 本地模式命令执行正确；安全限制生效；审计日志完整

### 步骤4: 创建 VMSandboxProvider
- **文件**: `backend/packages/harness/deerflow/sandbox/vm_sandbox.py`
- **操作**: 新建
- **内容**: 实现 VM 沙箱统一提供者，自动选择平台实现：
  1. **类定义**：
     ```python
     class VMSandboxProvider(SandboxProvider):
         def __init__(self, platform: str = "auto"):
             self.platform = self._detect_platform() if platform == "auto" else platform
             self._provider: SandboxProvider | None = None
             self._vm_pool: dict[str, SandboxProvider] = {}

         def _detect_platform(self) -> str:
             import platform as pf
             system = pf.system().lower()
             if system == "darwin":
                 return "macos"
             elif system == "windows":
                 return "windows"
             elif system == "linux":
                 return "linux"
             raise RuntimeError(f"不支持的平台: {system}")
     ```
  2. **延迟初始化平台提供者**：
     ```python
     async def _get_provider(self) -> SandboxProvider:
         if self._provider is not None:
             return self._provider
         if self.platform == "macos":
             from deerflow.sandbox.macos_vm import MacOSVMProvider
             self._provider = MacOSVMProvider()
         elif self.platform == "windows":
             from deerflow.sandbox.wsl2_vm import WSL2VMProvider
             self._provider = WSL2VMProvider()
         elif self.platform == "linux":
             from deerflow.sandbox.firecracker_vm import FirecrackerVMProvider
             self._provider = FirecrackerVMProvider()
         return self._provider
     ```
  3. **平台检测降级**：
     ```python
     async def is_available(self) -> bool:
         try:
             provider = await self._get_provider()
             return await provider.is_available()
         except (ImportError, RuntimeError):
             return False

     async def create_sandbox(self, thread_id: str, config: dict) -> str:
         provider = await self._get_provider()
         if not await provider.is_available():
             logger.warning(f"VM 沙箱不可用 (platform={self.platform})，降级到本地模式")
             local_provider = LocalSandboxProvider()
             return await local_provider.create_sandbox(thread_id, config)
         return await provider.create_sandbox(thread_id, config)
     ```
  4. **所有方法委托到平台提供者**
- **验收**: 在 macOS 上自动使用 MacOSVMProvider，在 Linux 上使用 FirecrackerVMProvider；不可用时降级到 LocalSandboxProvider

### 步骤5: macOS VM Provider 封装
- **文件**: `backend/packages/harness/deerflow/sandbox/macos_vm.py`
- **操作**: 新建
- **内容**: 封装 T30 的 Swift CLI 为 Python SandboxProvider：
  1. **MacOSVMProvider 类**：继承 `SandboxProvider`，通过 `subprocess` 调用 `DeerFlowSandboxCLI`
  2. **CLI 调用封装**：
     ```python
     class MacOSVMProvider(SandboxProvider):
         CLI_NAME = "DeerFlowSandboxCLI"

         async def _run_cli(self, action: str, args: dict | None = None) -> dict:
             cmd = [self._cli_path(), action]
             if args:
                 cmd.extend(["--args", json.dumps(args)])
             proc = await asyncio.create_subprocess_exec(
                 *cmd,
                 stdout=asyncio.subprocess.PIPE,
                 stderr=asyncio.subprocess.PIPE,
             )
             stdout, stderr = await proc.communicate()
             if proc.returncode != 0:
                 raise SandboxError(f"CLI 错误: {stderr.decode()}")
             return json.loads(stdout)
     ```
  3. **is_available()**：检查 CLI 文件存在 + 调用 `detectSupport` 确认虚拟化支持
  4. **所有方法委托到对应 CLI action**
- **验收**: Python 调用 `MacOSVMProvider` 可正确操作 VM

### 步骤6: WSL2 VM Provider 封装
- **文件**: `backend/packages/harness/deerflow/sandbox/wsl2_vm.py`
- **操作**: 新建
- **内容**: 封装 T31 的 WSL2 桥接为 Python SandboxProvider：
  1. **WSL2VMProvider 类**：继承 `SandboxProvider`，通过 `subprocess` 调用 `wsl` 命令
  2. **is_available()**：检查 `wsl` 命令存在 + WSL2 已安装 + DeerFlow 发行版已导入
  3. **create_sandbox()**：检查发行版是否已导入，未导入时自动导入
  4. **execute()**：使用 `wsl -d DeerFlow -- bash -c "command"` 执行
- **验收**: Python 调用 `WSL2VMProvider` 可正确操作 WSL2 发行版

### 步骤7: Firecracker VM Provider 封装
- **文件**: `backend/packages/harness/deerflow/sandbox/firecracker_vm.py`（扩展）
- **操作**: 改造
- **内容**: 将 T32 的 FirecrackerVM 封装为 SandboxProvider：
  1. **FirecrackerVMProvider 类**：继承 `SandboxProvider`，管理 VM 实例池
  2. **is_available()**：检查 `/dev/kvm` 存在且可读写 + Firecracker 二进制存在
  3. **create_sandbox()**：创建新的 FirecrackerVM 实例，加入实例池
- **验收**: FirecrackerVMProvider 正确管理 VM 实例

### 步骤8: Electron 侧平台检测（健壮版）
- **文件**: `desktop/electron/sandbox-detector.ts`
- **操作**: 新建
- **内容**: 实现 Electron 主进程中的沙箱检测逻辑（**健壮版，处理所有异常**）：
  1. **detectAndSetupSandbox() 函数**：
     ```typescript
     export async function detectAndSetupSandbox(): Promise<SandboxDetectionResult> {
         const platform = process.platform;

         try {
             if (platform === "darwin") {
                 const hasVirtualization = await checkMacOSVirtualization();
                 if (hasVirtualization) {
                     return { type: "macos-vm", available: true, details: hasVirtualization };
                 }
             } else if (platform === "win32") {
                 const hasWSL2 = await checkWSL2Support();
                 if (hasWSL2.available) {
                     return { type: "wsl2", available: true, details: hasWSL2 };
                 }
                 if (hasWSL2.canInstall) {
                     const installed = await offerWSL2Install();
                     if (installed) {
                         return { type: "wsl2", available: true, details: { ...hasWSL2, installed: true } };
                     }
                 }
             } else if (platform === "linux") {
                 const hasKVM = await checkKVMSupport();
                 if (hasKVM) {
                     return { type: "firecracker", available: true, details: hasKVM };
                 }
                 const hasDocker = await checkDockerSupport();
                 if (hasDocker) {
                     return { type: "docker", available: true, details: hasDocker };
                 }
             }
         } catch (error) {
             logger.error("沙箱检测失败:", error);
         }

         return { type: "local", available: true, details: { reason: "未检测到虚拟化能力，将使用本地模式" } };
     }
     ```
  2. **平台检测函数**（健壮版）：
     - `checkMacOSVirtualization()`: 调用 Swift CLI `detectSupport`，**捕获 CLI 不存在、超时等异常**
     - `checkWSL2Support()`: 执行 `wsl --status`，**捕获命令不存在、编码异常**
     - `checkKVMSupport()`: 检查 `/dev/kvm` 文件存在性，**捕获权限异常**
     - `checkDockerSupport()`: 执行 `docker info`，**捕获 Docker 未安装异常**
  3. **检测结果缓存**：
     - 检测结果缓存到 `localStorage`（有效期 24h）
     - 避免每次启动都重新检测
     - **缓存失效时静默重新检测，不阻塞用户**
  4. **SandboxDetectionResult 类型**：
     ```typescript
     interface SandboxDetectionResult {
         type: "macos-vm" | "wsl2" | "firecracker" | "docker" | "local";
         available: boolean;
         details: Record<string, any>;
     }
     ```
- **验收**: 在 macOS 上检测到 Virtualization.framework；在无 WSL2 的 Windows 上提示安装；在无 KVM 的 Linux 上降级到 local；**所有异常都被捕获，不会导致应用崩溃**

### 步骤9: 降级路径实现（优雅降级）
- **文件**: `backend/packages/harness/deerflow/sandbox/fallback.py`
- **操作**: 新建
- **内容**: 实现沙箱降级逻辑（**优雅降级，无需用户干预**）：
  1. **FallbackManager 类**：
     ```python
     class FallbackManager:
         PROVIDER_PRIORITY = ["vm", "docker", "local"]

         def __init__(self, config: dict):
             self.config = config
             self._providers: dict[str, SandboxProvider] = {}
             self._active_provider: str = ""
             self._fallback_history: list[dict] = []

         async def initialize(self) -> None:
             for provider_type in self.PROVIDER_PRIORITY:
                 provider = self._create_provider(provider_type)
                 if provider and await provider.is_available():
                     self._providers[provider_type] = provider
                     self._active_provider = provider_type
                     logger.info(f"沙箱提供者选择: {provider_type}")
                     return
                 else:
                     logger.info(f"沙箱提供者 {provider_type} 不可用，尝试下一个")

             self._providers["local"] = LocalSandboxProvider()
             self._active_provider = "local"
             logger.warning("所有 VM 沙箱不可用，降级到本地模式")

         async def get_provider(self) -> SandboxProvider:
             return self._providers[self._active_provider]

         async def fallback(self, reason: str) -> SandboxProvider:
             current_idx = self.PROVIDER_PRIORITY.index(self._active_provider)
             for next_type in self.PROVIDER_PRIORITY[current_idx + 1:]:
                 if next_type in self._providers and await self._providers[next_type].is_available():
                     self._fallback_history.append({
                         "from": self._active_provider,
                         "to": next_type,
                         "reason": reason,
                         "timestamp": datetime.now().isoformat(),
                     })
                     self._active_provider = next_type
                     return self._providers[next_type]
             raise RuntimeError(f"无法降级: {reason}")
     ```
  2. **自动降级触发**：
     - VM 启动失败 3 次 → 自动降级
     - VM 响应超时累计 > 60s → 自动降级
     - VM 内存不足 → 自动降级
     - **降级后自动通知用户**（通过 IPC），显示降级原因和建议
  3. **降级恢复**：
     - 用户可在设置中手动切换回 VM 模式
     - 切换前重新检测虚拟化能力
     - 恢复成功后清除降级历史
  4. **降级历史记录**：
     - 记录每次降级的时间、原因、目标
     - 可通过 API 查询
  5. **本地模式作为默认回退**：
     - **本地模式始终可用**，是最后的保障
     - 降级到本地模式时，自动启用安全措施
     - 通知用户当前为本地模式，建议启用 VM 获得更好隔离
- **验收**: VM 不可用时自动降级到本地模式；降级通知用户；可手动恢复

### 步骤10: 沙箱与 DeerFlow Runtime 集成
- **文件**: `backend/packages/harness/deerflow/sandbox/__init__.py`（改造）
- **操作**: 改造
- **内容**: 将沙箱抽象层集成到 DeerFlow 运行时：
  1. **全局沙箱管理器**：
     ```python
     _sandbox_manager: FallbackManager | None = None

     async def get_sandbox_manager() -> FallbackManager:
         global _sandbox_manager
         if _sandbox_manager is None:
             from deerflow.config import get_app_config
             config = get_app_config()
             _sandbox_manager = FallbackManager(config)
             await _sandbox_manager.initialize()
         return _sandbox_manager
     ```
  2. **工具执行路由**：
     - 在 `deerflow.tools` 中集成 SandboxRouter
     - 高风险工具通过沙箱执行
     - 低风险工具直接本地执行
  3. **配置项**：
     ```yaml
     sandbox:
       strategy: "selective"     # strict / selective / local
       auto_detect: true         # 自动检测平台能力
       fallback: true            # 启用自动降级
       local_mode_enhanced: true # 本地模式增强安全
       vm:
         memory_mb: 2048
         cpu_count: 2
         workspace_dir: null     # null = 自动选择
       firecracker:
         kernel_path: null
         rootfs_path: null
         file_sharing: "scp"
     ```
- **验收**: DeerFlow 运行时工具执行正确路由到沙箱或本地

### 步骤11: 跨平台降级路径测试
- **文件**: `backend/tests/test_sandbox_fallback.py`
- **操作**: 新建
- **内容**: 编写跨平台降级路径测试：
  1. **macOS 降级测试**：
     - 模拟 Virtualization.framework 不可用 → 降级到 local
     - 模拟 VM 启动失败 3 次 → 自动降级
  2. **Windows 降级测试**：
     - 模拟 WSL2 未安装 → 降级到 local
     - 模拟 WSL2 发行版损坏 → 降级到 local
  3. **Linux 降级测试**：
     - 模拟 /dev/kvm 不存在 → 降级到 Docker → 降级到 local
     - 模拟 KVM 权限不足 → 降级到 Docker → 降级到 local
     - 模拟 Docker 不可用 → 降级到 local
  4. **通用降级测试**：
     - FallbackManager 初始化优先级测试
     - 手动降级/恢复测试
     - 降级历史记录测试
  5. **SandboxRouter 测试**：
     - STRICT 模式所有工具走 VM
     - SELECTIVE 模式正确路由
     - LOCAL 模式所有工具走本机
  6. **本地模式一等公民测试**：
     - 本地模式下所有工具正常执行
     - 安全措施（白名单、目录限制）生效
     - 审计日志完整
  7. **Mock 方式**：
     - 使用 `unittest.mock.patch` 模拟平台检测
     - 不需要真实 VM 环境
- **验收**: 所有降级路径测试通过

## 验收标准
- [ ] SandboxProvider 基类定义完整，所有平台实现遵循接口
- [ ] SandboxRouter 正确路由工具调用到 VM 或本地
- [ ] VMSandboxProvider 在 macOS/Windows/Linux 上自动选择正确提供者
- [ ] 虚拟化不可用时自动降级到 LocalSandboxProvider
- [ ] **本地模式是一等公民，所有核心功能正常工作**
- [ ] **本地模式下安全措施（白名单、目录限制、审计日志）生效**
- [ ] Electron 侧 sandbox-detector.ts 正确检测平台能力
- [ ] **平台检测健壮，异常不会导致应用崩溃**
- [ ] FallbackManager 降级/恢复流程正常
- [ ] 降级通知可送达用户
- [ ] 配置热重载支持策略动态切换

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | SandboxRouter.should_use_sandbox() SELECTIVE 模式 | 高风险工具返回 True，低风险返回 False |
| 单元测试 | SandboxRouter.should_use_sandbox() STRICT 模式 | 所有工具返回 True |
| 单元测试 | SandboxRouter.should_use_sandbox() LOCAL 模式 | 所有工具返回 False |
| 单元测试 | VMSandboxProvider._detect_platform() | macOS→macos, Windows→windows, Linux→linux |
| 单元测试 | LocalSandboxProvider.is_available() | 始终返回 True |
| 单元测试 | LocalSandboxProvider.execute() 安全限制 | 危险命令被拦截，审计日志记录 |
| 单元测试 | FallbackManager.initialize() VM 可用 | 选择 VM 模式 |
| 单元测试 | FallbackManager.initialize() VM 不可用 | 降级到本地模式 |
| 集成测试 | 完整降级流程 | VM 失败 → 自动降级 → 命令仍可执行 |
| 集成测试 | 手动恢复降级 | 切换回 VM 模式成功 |
| 集成测试 | macOS Provider 集成 | Python → Swift CLI → VM 操作 |
| 集成测试 | 本地模式完整功能 | 所有工具在本地模式下正常执行 |
| E2E 测试 | 跨平台沙箱选择 | 各平台自动选择正确提供者 |
| 边界测试 | VM 启动中切换策略 | 策略变更后下次执行生效 |
| 边界测试 | 平台检测异常 | 异常被捕获，降级到本地模式，应用不崩溃 |
| 边界测试 | 检测缓存失效 | 静默重新检测，不阻塞用户 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 跨平台接口抽象不完全匹配 | 中 | 使用可选方法（有默认 NotImplementedError 实现）；每个平台文档化不支持的功能 |
| 降级后用户不知情 | 中 | **降级时弹出通知**；状态栏显示当前沙箱模式；本地模式提示安全说明 |
| LocalSandboxProvider 安全风险 | 高 | **本地模式是一等公民，安全措施必须健壮**：命令白名单、工作目录限制、审计日志、环境变量隔离 |
| Swift CLI 调用延迟影响性能 | 中 | 批量命令合并；长时间操作使用 WebSocket 代替多次 CLI 调用 |
| 配置热重载与运行中沙箱冲突 | 低 | 热重载仅影响新创建的沙箱；运行中的沙箱保持当前策略 |
| 多平台测试环境难以获取 | 高 | 使用 Mock 测试；CI 使用 Linux runner；macOS/Windows 手动测试 |
| 平台检测异常导致应用崩溃 | 中 | **所有检测函数包裹 try-catch**；异常时默认降级到本地模式；缓存检测结果 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.4 分层沙箱策略、7.5.4 跨平台抽象层、7.7 自动检测降级流程）
- EVOFLOW_IMPLEMENTATION_PLAN.md 第11节（第4期路线图依赖关系）
- DeerFlow 现有 `backend/packages/harness/deerflow/sandbox/` 模块
- Python ABC 文档: https://docs.python.org/3/library/abc.html
