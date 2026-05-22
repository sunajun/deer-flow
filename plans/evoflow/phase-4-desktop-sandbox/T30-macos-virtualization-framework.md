# T30 - macOS Virtualization.framework 适配

## 元信息
- **任务ID**: T30
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P2
- **预估工期**: 10 天（2 周）
- **依赖任务**: T29
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
实现 macOS 平台基于 Virtualization.framework 的轻量 VM 沙箱，支持 VM 启动/停止、命令执行、文件共享（virtiofs）、快照恢复，通过 Swift 原生模块与 Electron 通信。**最低系统要求 macOS 11 (Big Sur)**，同时支持 Apple Silicon 和 Intel Mac 两种架构。

## 系统要求

### 最低要求
- **macOS 11.0 (Big Sur)** 及以上 — Virtualization.framework 从 macOS 11 开始提供
- Apple Silicon (M1/M2/M3/M4) 或 Intel Mac (需支持 VT-x)
- 至少 4GB 可用内存（VM 需分配 2GB）

### 功能版本差异
| 功能 | macOS 11 (Big Sur) | macOS 12 (Monterey) | macOS 13 (Ventura) | macOS 14 (Sonoma)+ |
|------|-------------------|--------------------|--------------------|--------------------|
| 基础 VM 启停 | ✅ | ✅ | ✅ | ✅ |
| virtiofs 文件共享 | ✅ | ✅ | ✅ | ✅ |
| 原生快照 API | ❌ | ❌ | ❌ | ✅ |
| 嵌套虚拟化 | ❌ | ❌ | ❌ | ✅ (M3+) |
| USB 设备直通 | ❌ | ❌ | ✅ | ✅ |
| Rosetta Linux | ❌ | ✅ | ✅ | ✅ |

## 详细实现步骤

### 步骤1: 创建 Swift 原生模块目录结构
- **文件**: `desktop/native/macos/`
- **操作**: 新建
- **内容**: 创建以下文件结构：
  ```
  desktop/native/macos/
  ├── Package.swift                    Swift Package 定义
  ├── Sources/
  │   └── DeerFlowSandbox/
  │       ├── VirtualMachine.swift      VM 核心类
  │       ├── SSHClient.swift           SSH 连接封装
  │       ├── SnapshotManager.swift     快照管理
  │       ├── VirtualizationDetector.swift  虚拟化能力检测
  │       ├── DeerFlowSandbox.swift     公共 API 入口
  │       └── PlatformCompatibility.swift  Apple Silicon / Intel 兼容层
  ├── Tests/
  │   └── DeerFlowSandboxTests/
  │       ├── VirtualMachineTests.swift
  │       ├── DetectionTests.swift
  │       └── CompatibilityTests.swift
  └── Makefile                         构建脚本
  ```
- **验收**: `swift build` 编译成功

### 步骤2: VirtualizationDetector — 虚拟化能力检测
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/VirtualizationDetector.swift`
- **操作**: 新建
- **内容**: 检测当前 Mac 是否支持 Virtualization.framework：
  1. **系统版本检测**：
     - **macOS 11.0+ (Big Sur) 为最低要求**，低于此版本直接返回不支持
     - 使用 `ProcessInfo.processInfo.operatingSystemVersion` 检测
     - 不同 macOS 版本功能差异见上方版本差异表
  2. **芯片架构检测**：
     - Apple Silicon (M1/M2/M3/M4)：原生支持，性能最优
       - VM 使用 ARM64 Linux 镜像
       - 启动时间 < 5s，virtiofs 性能优秀
     - Intel Mac：支持但需确认 VT-x 已启用
       - VM 使用 x86_64 Linux 镜像
       - 启动时间 < 8s，virtiofs 性能略低于 Apple Silicon
       - 部分旧款 Intel Mac 可能不支持虚拟化（需检测）
     - 使用 `var sysinfo = utsname(); uname(&sysinfo)` 获取机器标识
     - 通过 `sysctlbyname("machdep.cpu.brand_string")` 区分芯片类型
  3. **框架加载检测**：尝试 `import Virtualization`，捕获错误
  4. **权限检测**：检查应用是否有虚拟化权限（沙盒应用不可用）
  5. **返回结构体**：
     ```swift
     struct VirtualizationSupport {
         let isSupported: Bool
         let chipArchitecture: ChipArchitecture  // .appleSilicon / .intel
         let macOSVersion: OperatingSystemVersion
         let minimumRequirement: String  // "macOS 11.0 (Big Sur)"
         let reason: String?             // 不支持时的原因
         let supportedFeatures: Set<VMFeature>  // 支持的功能集
     }

     enum ChipArchitecture: String {
         case appleSilicon = "apple_silicon"
         case intel = "intel"
     }

     enum VMFeature: String {
         case basicVM, virtiofs, snapshot, nestedVirtualization, rosettaLinux
     }
     ```
  6. **Intel Mac 特殊检测**：
     - 检查 VT-x 支持：`sysctlbyname("machdep.cpu.features")` 包含 "VMX"
     - 检查 EPT 支持：`sysctlbyname("machdep.cpu.features")` 包含 "EPT"
     - 不支持时返回 `isSupported: false`，reason 说明需要支持 VT-x+EPT 的 CPU
- **验收**: 在 Apple Silicon Mac 上返回 `isSupported: true`；在 macOS 10.15 上返回 `isSupported: false` 附带原因；在 Intel Mac 上正确区分支持/不支持

### 步骤3: DeerFlowSandbox 核心 VM 类
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/VirtualMachine.swift`
- **操作**: 新建
- **内容**: 实现 `DeerFlowSandbox` 类，遵循 `VZVirtualMachineDelegate`：
  1. **属性**：
     - `vm: VZVirtualMachine?` — 虚拟机实例
     - `sshClient: SSHClient?` — SSH 连接
     - `state: VMState` — 当前状态（stopped/starting/running/paused/error）
     - `config: VMConfig` — VM 配置
     - `chipArchitecture: ChipArchitecture` — 当前架构
  2. **VMConfig 结构体**（架构感知）：
     ```swift
     struct VMConfig {
         var imagePath: String           // 磁盘镜像路径
         var kernelPath: String?         // 内核路径（macOS 13+ 可选）
         var memoryMB: Int               // 内存大小
         var cpuCount: Int               // CPU 核心数
         var workspacePath: String       // 宿主工作目录
         var sshPort: Int = 22           // SSH 端口（VM 内部）
         var architecture: ChipArchitecture  // 目标架构

         // Apple Silicon 推荐配置
         static func appleSiliconDefault() -> VMConfig {
             return VMConfig(
                 imagePath: "", memoryMB: 2048, cpuCount: 2,
                 workspacePath: "", architecture: .appleSilicon
             )
         }

         // Intel Mac 推荐配置
         static func intelDefault() -> VMConfig {
             return VMConfig(
                 imagePath: "", memoryMB: 2048, cpuCount: 2,
                 workspacePath: "", architecture: .intel
             )
         }
     }
     ```
  3. **start() 方法**（架构感知）：
     - 根据 `chipArchitecture` 选择正确的磁盘镜像：
       - Apple Silicon: 使用 ARM64 镜像
       - Intel: 使用 x86_64 镜像
     - 创建 `VZDiskImageStorageDeviceAttachment`，加载磁盘镜像（读写模式）
     - 配置 `VZVirtualMachineConfiguration`：
       - `cpuCount`、`memorySize`
       - 磁盘设备：`VZVirtioBlockDeviceConfiguration`
       - 网络设备：`VZVirtioNetworkDeviceConfiguration` + NAT
       - 串口设备：`VZVirtioConsoleDeviceConfiguration`（用于调试）
       - 目录共享：`VZVirtioFileSystemDeviceConfiguration`（tag: "deerflow-workspace"）
       - 引导加载器：`VZLinuxBootLoader`（内核路径从镜像中提取）
       - **Apple Silicon 额外配置**：`VZMacPlatformConfiguration`（如需 macOS VM）
     - 调用 `config.validate()` 确保配置合法
     - 创建 `VZVirtualMachine` 实例
     - 设置 self 为 delegate
     - 调用 `vm.start()` 异步启动
     - 状态变更：stopped → starting → running
     - 启动后等待 SSH 就绪（轮询连接）
  4. **execute() 方法**：
     - 通过 SSH 连接执行命令
     - 支持超时设置（默认 300s）
     - 返回命令退出码、stdout、stderr
     - 支持 streaming 输出（通过 delegate 回调）
  5. **stop() 方法**：
     - 优雅停止：`vm.stop()`
     - 超时后强制停止
     - 状态变更：running → stopped
  6. **pause() / resume() 方法**：
     - `vm.pause()` / `vm.resume()`
     - 状态变更：running ↔ paused
  7. **VZVirtualMachineDelegate 实现**：
     - `guestDidStop`: VM 意外停止时清理资源、通知上层
     - `virtualMachine(_:didChangeStateTo:)`: 状态变化通知
- **验收**: VM 可在 Apple Silicon 和 Intel Mac 上启动、SSH 连接成功、命令执行返回结果

### 步骤4: virtiofs 目录共享
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/VirtualMachine.swift`（在步骤3基础上扩展）
- **操作**: 新建
- **内容**: 在 VM 配置中添加 virtiofs 共享目录：
  1. **共享目录设置**：
     - 宿主路径：`~/DeerFlow/workspace/`（可通过 config 自定义）
     - `VZSharedDirectory` 指向宿主工作目录，`readOnly: false`
     - `VZSingleDirectoryShare` 包装
     - `VZVirtioFileSystemDeviceConfiguration`，tag 为 `"deerflow-workspace"`
  2. **VM 内挂载**：
     - VM 启动后通过 SSH 执行：`mkdir -p /mnt/workspace && mount -t virtiofs deerflow-workspace /mnt/workspace`
     - 设置权限：`chown sandbox:sandbox /mnt/workspace`
  3. **文件同步**：
     - 宿主写入的文件立即可在 VM 内访问
     - VM 内写入的文件立即可在宿主访问
     - 符号链接正确处理
  4. **架构差异处理**：
     - Apple Silicon：virtiofs 性能优秀，读写延迟 < 5ms
     - Intel Mac：virtiofs 性能略低，读写延迟约 10-20ms
     - Intel Mac 上大文件传输（>100MB）可考虑使用 SCP 替代
  5. **多线程安全**：virtiofs 操作天然线程安全，无需额外锁
- **验收**: 宿主写入文件后 VM 内 `cat /mnt/workspace/test.txt` 可读取；VM 内写入文件后宿主可读取；Apple Silicon 和 Intel Mac 均正常

### 步骤5: SSHClient 封装
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/SSHClient.swift`
- **操作**: 新建
- **内容**: 封装 SSH 连接用于命令执行：
  1. **连接建立**：
     - 使用 `NMSSH` 或 Swift NIO SSH 库
     - 连接参数：host（VM 内网 IP，通常 192.168.64.2）、port 22、用户名 sandbox
     - 认证方式：SSH 密钥（内嵌在 VM 镜像中），非密码
  2. **连接重试**：
     - VM 启动后 SSH 服务需要几秒才就绪
     - 轮询间隔 1s，最多 30 次（30s 超时）
     - 连接成功后缓存 session
  3. **execute() 方法**：
     ```swift
     func execute(command: String, timeout: TimeInterval = 300) async throws -> CommandResult {
         // 执行命令，捕获 stdout/stderr
         // 超时处理：使用 Task + withTimeout
     }
     ```
  4. **streaming 输出**：
     - 支持实时获取 stdout/stderr 行
     - 通过 delegate 回调：`onStdout(line:)` / `onStderr(line:)`
  5. **连接保活**：
     - 每 60s 发送 keepalive 包
     - 断开后自动重连（最多 3 次）
  6. **SCP 文件传输**（可选）：
     - `upload(localPath:, remotePath:)`
     - `download(remotePath:, localPath:)`
- **验收**: SSH 连接 VM 成功，执行 `uname -a` 返回 Linux 内核信息；长命令 streaming 输出正常

### 步骤6: 快照保存/恢复
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/SnapshotManager.swift`
- **操作**: 新建
- **内容**: 实现 VM 快照管理：
  1. **保存快照**：
     - 使用 `VZVirtualMachine.saveSnapshot(name:)` (macOS 14+)
     - macOS 13 及以下使用磁盘镜像复制方式模拟快照
     - 快照存储路径：`~/DeerFlow/snapshots/{vm_id}/{snapshot_name}/`
     - 快照元数据：时间戳、描述、VM 配置快照、架构信息
  2. **恢复快照**：
     - 使用 `VZVirtualMachine.restoreSnapshot(name:)` (macOS 14+)
     - 目标亚秒级恢复（macOS 14+ 原生支持）
     - macOS 13 降级方案：停止 VM → 复制快照镜像覆盖当前 → 重启
  3. **快照列表**：
     - `listSnapshots() -> [SnapshotInfo]`
     - 返回名称、创建时间、大小
  4. **快照删除**：
     - `deleteSnapshot(name:)` 删除指定快照
  5. **自动快照**：
     - VM 启动后自动创建 `boot` 快照
     - 每小时自动创建 `auto-{timestamp}` 快照（可配置）
     - 最多保留 10 个自动快照，超出删除最旧的
  6. **版本兼容**：
     - 检测 macOS 版本，14+ 使用原生 API
     - 13 及以下使用文件复制方案，恢复时间约 5-10s（需告知用户）
     - **macOS 11 (Big Sur) 快照降级方案**：仅支持文件复制，恢复时间 10-15s
- **验收**: 创建快照后恢复，VM 状态与快照时一致（文件内容、运行进程）；macOS 14+ 恢复时间 <1s

### 步骤7: 公共 API 入口
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/DeerFlowSandbox.swift`
- **操作**: 新建
- **内容**: 提供 Electron 可调用的公共 API：
  ```swift
  @objc public class DeerFlowSandboxAPI: NSObject {
      @objc public static func detectSupport() -> [String: Any]
      @objc public static func createSandbox(config: [String: Any]) -> String  // 返回 sandbox_id
      @objc public static func startSandbox(id: String) -> Bool
      @objc public static func stopSandbox(id: String) -> Bool
      @objc public static func executeInSandbox(id: String, command: String, timeout: Int) -> [String: Any]
      @objc public static func pauseSandbox(id: String) -> Bool
      @objc public static func resumeSandbox(id: String) -> Bool
      @objc public static func saveSnapshot(id: String, name: String) -> Bool
      @objc public static func restoreSnapshot(id: String, name: String) -> Bool
      @objc public static func listSnapshots(id: String) -> [[String: Any]]
      @objc public static func deleteSnapshot(id: String, name: String) -> Bool
  }
  ```
- **验收**: Objective-C 运行时可调用所有方法

### 步骤8: Swift ↔ Electron 桥接
- **文件**: `desktop/electron/vm-manager.ts`
- **操作**: 新建
- **内容**: 实现 Electron 主进程与 Swift 原生模块的通信桥接：
  1. **通信方式**：使用 `node-ffi-napi` 或 `node-pty` 方式调用编译后的动态库
     - 方案 A：将 Swift 模块编译为 `.dylib`，通过 `ffi-napi` 直接调用
     - 方案 B：将 Swift 模块编译为 CLI 工具，通过 `child_process.spawn` 调用，JSON 通信
     - **推荐方案 B**：避免 FFI 兼容性问题，CLI 方式更稳定
  2. **Swift CLI 封装**：
     - 编译为 `DeerFlowSandboxCLI` 可执行文件
     - 命令格式：`DeerFlowSandboxCLI <action> --id <id> [--args <json>]`
     - 输出 JSON 格式结果
  3. **VMSandboxManager 类**（TypeScript）：
     ```typescript
     class VMSandboxManager {
         private cliPath: string;
         async detectSupport(): Promise<VirtualizationSupport>
         async createSandbox(config: VMConfig): Promise<string>
         async startSandbox(id: string): Promise<boolean>
         async stopSandbox(id: string): Promise<boolean>
         async execute(id: string, command: string, timeout?: number): Promise<CommandResult>
         async pauseSandbox(id: string): Promise<boolean>
         async resumeSandbox(id: string): Promise<boolean>
         async saveSnapshot(id: string, name: string): Promise<boolean>
         async restoreSnapshot(id: string, name: string): Promise<boolean>
     }
     ```
  4. **流式输出**：长时间命令通过 WebSocket 或 stdio pipe 传输
- **验收**: TypeScript 调用 `VMSandboxManager` 方法，Swift CLI 正确执行并返回结果

### 步骤9: VM 生命周期集成到 Electron
- **文件**: `desktop/electron/main.ts`（改造）
- **操作**: 改造
- **内容**: 在 T29 的 main.ts 中集成 VM 管理：
  1. 应用启动时调用 `VMSandboxManager.detectSupport()`
  2. 首次启动向导中根据检测结果配置沙箱
  3. 配置为 VM 模式时，Python 后端启动后自动启动 VM
  4. 应用退出时先停止 VM 再停止 Python 后端
  5. VM 状态变化通过 IPC 通知渲染进程
  6. VM 启动失败时降级到本地模式并通知用户
- **验收**: Electron 启动后 VM 自动启动，关闭时 VM 正确停止

### 步骤10: Swift 原生模块代码签名
- **文件**: `desktop/native/macos/Makefile`
- **操作**: 改造
- **内容**: Swift 原生模块编译后必须签名，否则无法加载：
  1. **编译签名**：
     - 编译 CLI 后使用 `codesign` 签名
     - 签名命令：`codesign --force --sign "Developer ID Application: DeerFlow Team" DeerFlowSandboxCLI`
     - 确保签名与主应用一致
  2. **Hardened Runtime**：
     - 编译时启用 hardened runtime：`codesign --options runtime`
     - 配合 entitlements 文件授权虚拟化权限
  3. **Entitlements 配置**：
     ```xml
     <key>com.apple.security.virtualization</key>
     <true/>
     <key>com.apple.security.cs.allow-jit</key>
     <true/>
     <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
     <true/>
     ```
  4. **CI 集成**：
     - CI 中编译后自动签名
     - 签名验证：`codesign --verify --deep --strict DeerFlowSandboxCLI`
  5. **Makefile 签名目标**：
     ```makefile
     sign: build
         codesign --force --options runtime \
             --entitlements ../../assets/entitlements.sandbox.plist \
             --sign "$(SIGNING_IDENTITY)" \
             .build/release/DeerFlowSandboxCLI
     ```
- **验收**: 签名后的 CLI 通过 `codesign --verify`；在 macOS 上可正常加载和执行

### 步骤11: Apple 公证（Notarization）
- **文件**: `desktop/scripts/notarize-macos.sh`
- **操作**: 新建
- **内容**: macOS 应用**必须经过 Apple 公证**，否则用户无法打开：
  1. **公证流程**：
     ```bash
     # 1. 提交公证
     xcrun notarytool submit DeerFlow.dmg \
         --apple-id "$APPLE_ID" \
         --password "$APPLE_APP_PASSWORD" \
         --team-id "$APPLE_TEAM_ID" \
         --wait

     # 2. Staple 公证票据
     xcrun stapler staple DeerFlow.dmg
     ```
  2. **公证要求**：
     - 所有可执行文件必须使用 Developer ID 签名
     - 启用 Hardened Runtime
     - 包含 secure timestamp
     - 不包含不安全的 entitlements
  3. **Swift CLI 公证**：
     - CLI 二进制作为主应用的一部分被签名和公证
     - 确保 CLI 的 entitlements 不与主应用冲突
  4. **CI 集成**：
     - 签名 → 公证 → Staple 作为发布流水线的必须步骤
     - 公证失败阻止发布
     - 公证通常需要 2-5 分钟
  5. **关键说明**：
     - **未公证的应用在 macOS 12+ 上会被 Gatekeeper 拦截**
     - **electron-updater 自动更新仅对已公证的应用生效**
     - 用户可通过 `xattr -cr` 绕过，但不可用于发布版本
- **验收**: 公证后的 DMG 在全新 macOS 上双击安装无警告；`spctl --assess --type install DeerFlow.dmg` 通过

### 步骤12: Apple Silicon vs Intel 兼容测试
- **文件**: `desktop/native/macos/Tests/DeerFlowSandboxTests/CompatibilityTests.swift`
- **操作**: 新建
- **内容**: 编写跨架构兼容测试：
  1. Apple Silicon (M1/M2/M3/M4) 上的 VM 启动和命令执行
  2. Intel Mac 上的 VM 启动和命令执行
  3. Universal Binary 编译验证
  4. 内存限制测试（1GB/2GB/4GB）
  5. CPU 核心数配置测试（1/2/4 核）
  6. virtiofs 大文件传输测试
  7. 快照保存/恢复跨重启测试
  8. **macOS 11 (Big Sur) 基础功能测试**（无原生快照）
  9. **macOS 12/13 功能测试**（virtiofs + 文件复制快照）
  10. **macOS 14+ 功能测试**（原生快照 API）
  11. Intel Mac VT-x 检测测试
- **验收**: 在两种架构上所有测试通过；macOS 11-15 各版本功能正确

### 步骤13: macOS 特定错误处理
- **文件**: `desktop/native/macos/Sources/DeerFlowSandbox/VirtualMachine.swift`（扩展）
- **操作**: 改造
- **内容**: 处理以下 macOS 特定错误场景：
  1. **系统版本过低（< macOS 11）**：
     - 检测：`ProcessInfo.processInfo.operatingSystemVersion < 11.0`
     - 处理：**明确提示需要 macOS 11 (Big Sur) 或更高版本**；降级到本地模式
     - 错误信息："DeerFlow 虚拟化沙箱需要 macOS 11 (Big Sur) 或更高版本。当前系统为 macOS {version}。将降级到本地模式运行。"
  2. **虚拟化权限不足**：
     - 错误：`VZErrorDomain error 1` — 需要虚拟化权限
     - 处理：提示用户在系统偏好设置中授予权限
  3. **磁盘镜像损坏**：
     - 错误：`VZErrorDomain error 2` — 镜像文件无效
     - 处理：提示重新下载/恢复镜像
  4. **内存不足**：
     - 错误：无法分配 VM 内存
     - 处理：降低 VM 内存配置，或提示关闭其他应用
  5. **Intel Mac 不支持 VT-x**：
     - 检测：`sysctlbyname("machdep.cpu.features")` 不包含 "VMX"
     - 处理：提示此 Mac 不支持虚拟化；降级到本地模式
  6. **VM 已在运行**：
     - 错误：尝试启动第二个 VM
     - 处理：复用已有 VM 或提示先停止
  7. **系统睡眠/唤醒**：
     - Mac 睡眠时 VM 自动暂停
     - 唤醒时自动恢复 VM
     - 恢复失败时重启 VM
  8. **架构不匹配**：
     - 错误：Apple Silicon Mac 加载 x86_64 镜像（或反之）
     - 处理：自动选择正确架构的镜像；提示用户下载对应版本
- **验收**: 每种错误场景都有用户友好的提示和恢复建议

## 验收标准
- [ ] Swift 模块编译成功，CLI 工具可执行
- [ ] **macOS 11+ 最低要求检测正确，低于 11.0 明确提示并降级**
- [ ] VM 可在 Apple Silicon Mac 上启动，状态正确流转
- [ ] VM 可在 Intel Mac 上启动（如有测试环境）
- [ ] SSH 命令执行正常，stdout/stderr 正确捕获
- [ ] virtiofs 共享目录读写正常，双向同步
- [ ] 快照保存和恢复功能正常（macOS 14+ 亚秒级，macOS 11-13 文件复制方式）
- [ ] Electron 通过 CLI 桥接调用 Swift 模块无异常
- [ ] 所有 macOS 特定错误有明确提示和恢复方案
- [ ] VM 启动/停止/暂停/恢复生命周期完整
- [ ] **Swift CLI 代码签名通过 `codesign --verify`**
- [ ] **应用公证通过，全新 macOS 上安装无 Gatekeeper 警告**

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | VirtualizationDetector.detectSupport() Apple Silicon | 返回 isSupported=true, chipArchitecture=.appleSilicon |
| 单元测试 | VirtualizationDetector.detectSupport() Intel Mac | 返回 isSupported=true, chipArchitecture=.intel |
| 单元测试 | VirtualizationDetector.detectSupport() macOS 10.15 | 返回 isSupported=false, reason="需要 macOS 11+" |
| 单元测试 | VirtualizationDetector.detectSupport() 无 VT-x Intel | 返回 isSupported=false, reason="CPU 不支持 VT-x" |
| 单元测试 | DeerFlowSandbox.start() Apple Silicon | 状态流转 stopped→starting→running，使用 ARM64 镜像 |
| 单元测试 | DeerFlowSandbox.start() Intel Mac | 状态流转 stopped→starting→running，使用 x86_64 镜像 |
| 单元测试 | DeerFlowSandbox.execute("uname -a") | Apple Silicon 返回 aarch64；Intel 返回 x86_64 |
| 单元测试 | DeerFlowSandbox.stop() 优雅停止 | 状态流转 running→stopped |
| 集成测试 | virtiofs 文件共享 | 宿主写入→VM 读取→VM 写入→宿主读取 全链路 |
| 集成测试 | 快照保存+恢复 | 恢复后文件内容、环境变量与快照时一致 |
| 集成测试 | Electron ↔ Swift CLI 桥接 | TypeScript 调用正确映射到 Swift 方法 |
| 兼容测试 | macOS 11 Big Sur 基础功能 | VM 启停、命令执行、virtiofs 正常；快照使用文件复制 |
| 兼容测试 | macOS 14 Sonoma 原生快照 | 快照保存/恢复 <1s |
| E2E 测试 | 完整 VM 生命周期 | 启动→执行命令→暂停→恢复→快照→恢复→停止 |
| 边界测试 | 内存不足场景 | 降低内存配置后可启动 |
| 边界测试 | 磁盘镜像损坏 | 返回明确错误信息 |
| 边界测试 | 架构不匹配 | 自动选择正确镜像或提示 |
| 性能测试 | VM 启动时间 Apple Silicon | < 5s |
| 性能测试 | VM 启动时间 Intel Mac | < 8s |
| 性能测试 | 快照恢复时间 macOS 14+ | < 1s |
| 性能测试 | 命令执行延迟 | SSH 执行延迟 < 100ms |
| 签名测试 | Swift CLI codesign 验证 | `codesign --verify --deep --strict` 通过 |
| 签名测试 | 应用公证验证 | `spctl --assess --type install` 通过 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| macOS 11 (Big Sur) 功能受限 | 高 | 明确文档化各版本功能差异；Big Sur 不支持原生快照，使用文件复制方案 |
| macOS 14 以下不支持原生快照 API | 高 | 实现文件复制降级方案，恢复时间 5-15s；Big Sur 上明确告知用户 |
| virtiofs 在 Intel Mac 上性能不佳 | 中 | 提供 SCP 作为备选方案；Intel Mac 使用 SCP 传输大文件 |
| Intel Mac 旧型号不支持 VT-x | 中 | 启动前检测 VT-x+EPT；不支持时降级到本地模式 |
| SSH 库选择困难（Swift 生态不如 C 丰富） | 中 | 使用 libssh2 C 库通过 Swift 桥接；或使用 NMSSH |
| Apple Silicon 模拟 x86 VM 性能差 | 低 | VM 镜像使用 ARM64 原生架构，不模拟 x86；Intel Mac 使用 x86_64 镜像 |
| macOS 更新破坏 Virtualization.framework 兼容性 | 低 | 维护多版本兼容层；在 CI 中测试多个 macOS 版本 |
| Swift CLI 通信延迟 | 中 | 批量命令合并；长连接 WebSocket 代替多次 CLI 调用 |
| 代码签名/公证失败 | 中 | 提前准备 Apple Developer 账号；CI 中测试签名和公证流程；**未公证应用不可发布** |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.5.1 macOS Virtualization.framework 原生实现、7.5.4 跨平台抽象层）
- Apple Virtualization.framework 文档: https://developer.apple.com/documentation/virtualization
- VZVirtualMachine API 参考: https://developer.apple.com/documentation/virtualization/vzvirtualmachine
- virtiofs 规范: https://virtio-fs.gitlab.io/
- Apple 代码签名与公证: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- macOS 版本兼容性: https://developer.apple.com/documentation/virtualization/vzvirtualmachineconfiguration#declarations
