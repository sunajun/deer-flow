# T31 - Windows WSL2 适配

## 元信息
- **任务ID**: T31
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P3
- **预估工期**: 6 天（增加一键启用脚本和 Windows 10/11 差异处理）
- **依赖任务**: T29
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
实现 Windows 平台基于 WSL2 的轻量沙箱，支持 WSL2 发行版导入、命令执行、工作目录共享，提供 WSL2 环境自动检测和**启动向导内一键启用脚本**，处理 Windows 10 与 Windows 11 的差异。

## Windows 10 vs Windows 11 差异

| 特性 | Windows 10 (1903+) | Windows 11 |
|------|-------------------|------------|
| WSL2 安装方式 | `dism.exe` 手动启用功能 | `wsl --install` 一键安装 |
| systemd 支持 | ❌（需手动配置） | ✅（WSL2 0.67.6+） |
| WSLg 图形支持 | ❌ | ✅ |
| `wsl --install` | 需手动指定 `--no-distribution` | 直接支持 |
| 重启要求 | 启用功能后**必须重启** | 启用功能后**必须重启** |
| Hyper-V 冲突 | 更常见 | 改善 |
| 默认 WSL 版本 | 可能默认 WSL1 | 默认 WSL2 |

## 详细实现步骤

### 步骤1: 创建 Windows 适配模块
- **文件**: `desktop/native/windows/`
- **操作**: 新建
- **内容**: 创建以下文件结构：
  ```
  desktop/native/windows/
  ├── wsl2-bridge.ts          WSL2 核心桥接类
  ├── wsl2-detector.ts        WSL2 检测与安装
  ├── wsl2-installer.ts       WSL2 一键安装脚本
  ├── wsl2-setup-wizard.ts    启动向导内一键启用集成
  ├── distro-manager.ts       发行版管理
  ├── workspace-mount.ts      工作目录挂载
  └── windows-version.ts      Windows 版本检测
  ```
- **验收**: TypeScript 编译无错误

### 步骤2: Windows 版本检测
- **文件**: `desktop/native/windows/windows-version.ts`
- **操作**: 新建
- **内容**: 精确检测 Windows 版本，区分 Windows 10 和 Windows 11：
  1. **版本检测**：
     ```typescript
     interface WindowsVersion {
         major: number;
         minor: number;
         build: number;
         isWindows10: boolean;
         isWindows11: boolean;
         isWSL2Supported: boolean;
         installMethod: "wsl_install" | "dism";
         needsRestart: boolean;
     }

     async function detectWindowsVersion(): Promise<WindowsVersion> {
         const result = await runCommand("cmd /c ver");
         const build = parseBuildNumber(result.stdout);
         return {
             major: 10,
             minor: 0,
             build,
             isWindows10: build < 22000,
             isWindows11: build >= 22000,
             isWSL2Supported: build >= 19041,
             installMethod: build >= 22000 ? "wsl_install" : "dism",
             needsRestart: true,
         };
     }
     ```
  2. **关键版本号**：
     - Build 19041+: WSL2 支持
     - Build 22000+: Windows 11
     - Build 22621+: WSLg 图形支持
  3. **功能可用性映射**：
     - 根据 build 号判断哪些功能可用
     - 影响 WSL2 安装方式和发行版配置
- **验收**: 正确区分 Windows 10 和 Windows 11；返回正确的安装方法

### 步骤3: WSL2 检测与安装
- **文件**: `desktop/native/windows/wsl2-detector.ts`
- **操作**: 新建
- **内容**: 实现 WSL2 环境检测：
  1. **WSL2 安装检测**：
     - 执行 `wsl --status` 检查 WSL 是否已安装
     - 检查默认版本是否为 WSL2（`wsl --version`）
     - 检查 Windows 版本（需 Windows 10 1903+ 或 Windows 11）
  2. **虚拟化支持检测**：
     - 检查 Hyper-V 是否已启用
     - 检查 BIOS 虚拟化（VT-x/AMD-V）是否开启
     - 执行 `wmic cpu get VirtualizationFirmwareEnabled`
  3. **DeerFlow 发行版检测**：
     - 执行 `wsl -l -v` 检查是否已导入 "DeerFlow" 发行版
     - 检查发行版状态（Running/Stopped）
  4. **返回检测结构**：
     ```typescript
     interface WSL2Support {
         wslInstalled: boolean;
         wsl2Default: boolean;
         hyperVEnabled: boolean;
         virtualizationEnabled: boolean;
         deerFlowDistroInstalled: boolean;
         windowsVersion: WindowsVersion;
         issues: string[];
         canAutoInstall: boolean;  // 是否可自动安装
         installMethod: "wsl_install" | "dism" | "manual";
     }
     ```
- **验收**: 在已安装 WSL2 的 Windows 上返回 `wslInstalled: true`；在未安装的机器上返回 `wslInstalled: false` 和安装建议

### 步骤4: WSL2 一键安装脚本
- **文件**: `desktop/native/windows/wsl2-installer.ts`
- **操作**: 新建
- **内容**: 实现 WSL2 自动安装（**核心改进：一键启用，无需用户手动操作**）：
  1. **Windows 11 一键安装**：
     ```typescript
     async function installWSL2Win11(): Promise<InstallResult> {
         // 1. 检测管理员权限
         if (!await isAdmin()) {
             await requestElevation();
         }
         // 2. 一键安装
         await runCommand('wsl --install --no-distribution');
         // 3. 设置默认版本
         await runCommand('wsl --set-default-version 2');
         // 4. 提示重启
         return { needsRestart: true, message: "WSL2 已安装，需要重启计算机" };
     }
     ```
  2. **Windows 10 安装**（更复杂）：
     ```typescript
     async function installWSL2Win10(): Promise<InstallResult> {
         // 1. 检测管理员权限
         if (!await isAdmin()) {
             await requestElevation();
         }
         // 2. 启用 WSL 功能
         await runCommand(
             'dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart'
         );
         // 3. 启用虚拟机平台
         await runCommand(
             'dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart'
         );
         // 4. 下载并安装 WSL2 Linux 内核更新包
         const wslUpdateUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi";
         const msiPath = path.join(os.tmpdir(), "wsl_update_x64.msi");
         await downloadFile(wslUpdateUrl, msiPath);
         await runCommand(`msiexec /i "${msiPath}" /quiet`);
         // 5. 设置默认版本
         await runCommand('wsl --set-default-version 2');
         // 6. 提示重启
         return { needsRestart: true, message: "WSL2 功能已启用，需要重启计算机" };
     }
     ```
  3. **权限处理**：
     - WSL 安装需要管理员权限
     - 检测当前是否有管理员权限（`net session` 命令）
     - 无管理员权限时：**自动请求 UAC 提权**
     - 使用 `shell.openPath` 或 `sudo-prompt` 包请求提权
  4. **重启处理**：
     - 某些步骤需要重启
     - 设置重启后自动继续安装的标记（注册表 RunOnce）
     - 用户选择稍后重启时保存安装进度
     - 重启后自动继续：检测安装标记 → 继续未完成步骤
  5. **安装进度反馈**：
     - 通过 IPC 通知渲染进程安装进度
     - 步骤：检测环境 → 启用功能 → 安装内核 → 设置默认版本 → 完成
  6. **安装失败回滚**：
     - 记录每步操作
     - 失败时提示用户手动操作步骤
     - 提供详细日志供排查
- **验收**: 在干净的 Windows 11 上运行安装脚本，WSL2 安装成功；在 Windows 10 上安装脚本正确处理 dism 方式

### 步骤5: 启动向导内一键启用集成
- **文件**: `desktop/native/windows/wsl2-setup-wizard.ts`
- **操作**: 新建
- **内容**: 将 WSL2 一键安装集成到首次启动向导的 Sandbox 步骤中：
  1. **向导内检测流程**：
     ```
     用户进入 Sandbox 步骤
     → 自动检测 WSL2 状态
     → 如果 WSL2 已安装且可用：显示"WSL2 已就绪"
     → 如果 WSL2 未安装但可安装：显示"一键启用 WSL2"按钮
     → 如果 WSL2 不可用（企业限制等）：显示"使用本地模式"
     ```
  2. **一键启用按钮**：
     - 点击"一键启用 WSL2"后：
       1. 请求管理员权限（UAC 弹窗）
       2. 显示安装进度条
       3. 安装完成后提示重启
       4. 重启后自动继续向导
     - 按钮文案根据 Windows 版本动态调整：
       - Windows 11: "一键启用 WSL2（推荐）"
       - Windows 10: "启用 WSL2（需要重启）"
  3. **重启后恢复**：
     - 重启前保存向导状态到 `localStorage`
     - 重启后 Electron 自启动，恢复向导到 Sandbox 步骤
     - 检测 WSL2 安装成功，自动进入下一步
  4. **降级选项**：
     - 始终显示"跳过，使用本地模式"选项
     - 安装失败时自动提示降级
  5. **UI 设计**：
     - 安装进度：步骤指示器 + 当前步骤描述 + 进度条
     - 错误处理：友好错误信息 + 重试按钮 + 手动安装指南链接
- **验收**: 在首次启动向导中一键启用 WSL2，重启后自动继续配置

### 步骤6: WSL2 核心桥接类
- **文件**: `desktop/native/windows/wsl2-bridge.ts`
- **操作**: 新建
- **内容**: 实现 `WSL2Sandbox` 类：
  1. **类定义**：
     ```typescript
     export class WSL2Sandbox {
         private distroName: string = "DeerFlow";
         private initialized: boolean = false;

         async init(imagePath: string): Promise<void>
         async execute(command: string, options?: ExecuteOptions): Promise<CommandResult>
         async start(): Promise<void>
         async stop(): Promise<void>
         async isRunning(): Promise<boolean>
         async dispose(): Promise<void>
     }
     ```
  2. **init() — 发行版导入**：
     - 执行 `wsl --import DeerFlow <install-path> <tar-gz-path> --version 2`
     - `install-path`: `%LOCALAPPDATA%/DeerFlow/wsl-distro/`
     - `tar-gz-path`: `resources/vm-images/deerflow-rootfs.tar.gz`
     - 导入后设置默认用户：在 WSL 内创建 `/etc/wsl.conf`
       ```ini
       [user]
       default=sandbox
       ```
  3. **execute() — 命令执行**：
     ```typescript
     async execute(command: string, options?: ExecuteOptions): Promise<CommandResult> {
         const cwd = options?.cwd ? `--cd "${options.cwd}"` : "";
         const envArgs = options?.env
             ? Object.entries(options.env).map(([k, v]) => `-e ${k}="${v}"`).join(" ")
             : "";
         const timeout = options?.timeout || 300;
         const cmd = `wsl -d ${this.distroName} ${cwd} ${envArgs} -- bash -c "${command}"`;
         const result = await runWithTimeout(cmd, timeout * 1000);
         return {
             exitCode: result.exitCode,
             stdout: result.stdout,
             stderr: result.stderr,
         };
     }
     ```
  4. **start() — 启动发行版**：
     - 执行 `wsl -d DeerFlow -- echo ready` 预热
     - 等待响应确认发行版可用
  5. **stop() — 停止发行版**：
     - 执行 `wsl -t DeerFlow` 终止
  6. **isRunning() — 状态检查**：
     - 解析 `wsl -l -v` 输出，检查 DeerFlow 行的 STATE 列
  7. **dispose() — 清理**：
     - 执行 `wsl --unregister DeerFlow` 删除发行版
     - 清理安装目录
- **验收**: 发行版导入成功，命令执行返回正确结果，停止/启动生命周期正常

### 步骤7: 发行版管理
- **文件**: `desktop/native/windows/distro-manager.ts`
- **操作**: 新建
- **内容**: 管理 DeerFlow WSL2 发行版：
  1. **发行版导入**：
     - 从 `deerflow-rootfs.tar.gz` 导入
     - 导入前检查磁盘空间（至少 2GB）
     - 导入后自动配置：设置默认用户、时区、语言
  2. **发行版更新**：
     - 比较当前版本与最新版本
     - 更新流程：导出用户数据 → 注销旧发行版 → 导入新发行版 → 恢复用户数据
     - 通过 `wsl --export` / `wsl --import` 实现
  3. **发行版状态监控**：
     - 定期检查 WSL 发行版健康状态
     - 检测 WSL 服务异常（`wsl --status`）
     - 异常时自动修复（重启 WSL 服务：`wsl --shutdown`）
  4. **用户数据管理**：
     - 用户数据存储路径：`/home/sandbox/` 在 WSL 内
     - 备份路径：`%LOCALAPPDATA%/DeerFlow/backup/` 在 Windows
     - 支持导出/导入用户数据
- **验收**: 发行版更新流程完整；用户数据在更新后保留

### 步骤8: 工作目录共享
- **文件**: `desktop/native/windows/workspace-mount.ts`
- **操作**: 新建
- **内容**: 实现 Windows ↔ WSL2 工作目录共享：
  1. **Windows → WSL2 自动挂载**：
     - WSL2 默认将 Windows 盘挂载到 `/mnt/c/`、`/mnt/d/` 等
     - 工作目录默认：`C:\Users\{username}\DeerFlow\workspace`
     - 在 WSL2 内路径：`/mnt/c/Users/{username}/DeerFlow/workspace`
     - 创建符号链接：`ln -s /mnt/c/Users/.../workspace /home/sandbox/workspace`
  2. **性能优化**：
     - 跨文件系统（/mnt/c）IO 性能较差（约 5-10x 慢于 WSL2 原生 ext4）
     - 选项 A（默认）：工作目录放在 WSL2 原生文件系统 `/home/sandbox/workspace`，通过 `\\wsl$\DeerFlow\home\sandbox\workspace` 从 Windows 访问
     - 选项 B：使用 `/mnt/c` 路径，性能差但 Windows 原生可访问
     - 向导中让用户选择方案
  3. **路径转换工具**：
     ```typescript
     class PathConverter {
         windowsToWsl(windowsPath: string): string {
             return windowsPath
                 .replace("C:\\", "/mnt/c/")
                 .replace("\\", "/");
         }
         wslToWindows(wslPath: string): string {
             return `\\\\wsl$\\DeerFlow${wslPath}`.replace(/\//g, "\\");
         }
     }
     ```
  4. **文件权限映射**：
     - WSL2 的 `/etc/wsl.conf` 配置：
       ```ini
       [automount]
       enabled = true
       options = "metadata,umask=22,fmask=11"
       ```
     - 确保 Windows 文件在 WSL2 中有正确的权限
- **验收**: Windows 文件可在 WSL2 中读写；WSL2 文件可在 Windows 资源管理器中访问

### 步骤9: Windows 特定错误处理
- **文件**: `desktop/native/windows/wsl2-bridge.ts`（扩展）
- **操作**: 改造
- **内容**: 处理以下 Windows 特定错误场景：
  1. **WSL 未安装**：
     - 错误：`wsl` 命令不存在
     - 处理：**调用启动向导内一键启用脚本**（步骤5），或降级到本地模式
  2. **WSL 版本 1（非 WSL2）**：
     - 错误：`wsl --set-default-version 2` 未执行
     - 处理：自动升级到 WSL2
  3. **发行版导入失败**：
     - 错误：磁盘空间不足、tar.gz 文件损坏
     - 处理：检查磁盘空间、校验文件 SHA256、提示重新下载
  4. **WSL 服务崩溃**：
     - 错误：`wsl` 命令超时无响应
     - 处理：`wsl --shutdown` 重启 WSL 服务，然后重试
  5. **Hyper-V 冲突**：
     - 错误：其他虚拟化软件（VMware/VirtualBox）冲突
     - 处理：提示关闭冲突软件；WSL2 与 VirtualBox 6.1+ 兼容
  6. **企业环境限制**：
     - 错误：组策略禁止安装 WSL
     - 处理：提示联系 IT 管理员；降级到本地模式
  7. **中文路径问题**：
     - 错误：Windows 用户名含中文字符导致 WSL 路径异常
     - 处理：使用 8.3 短路径名替代；或使用 WSL2 原生文件系统
  8. **Windows 10 特有问题**：
     - 错误：dism 启用功能后未重启
     - 处理：检测功能启用状态，提示重启并保存安装进度
  9. **Windows 11 特有问题**：
     - 错误：`wsl --install` 下载超时
     - 处理：提供离线安装包下载链接；或使用 dism 方式降级安装
- **验收**: 每种错误场景都有用户友好的中文提示和恢复建议

### 步骤10: Windows 安装器代码签名
- **文件**: `desktop/scripts/sign/sign-windows-installer.sh`
- **操作**: 新建
- **内容**: Windows 安装器**必须签名**，否则触发 SmartScreen 警告：
  1. **NSIS 安装器签名**：
     - electron-builder 自动签名 NSIS 安装器
     - 需要配置 `certificateFile` 和 `certificatePassword`
     - 签名命令：
       ```bash
       signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 \
           /f "$WIN_CERT_FILE" /p "$WIN_CERT_PASSWORD" \
           DeerFlow-Setup-0.1.0.exe
       ```
  2. **可执行文件签名**：
     - `deerflow-backend.exe`（Python 后端）必须签名
     - 所有内嵌的 `.exe` 和 `.dll` 都需签名
  3. **CI 集成**：
     - 证书存储在 GitHub Secrets
     - CI 中自动签名所有可执行文件和安装器
     - 签名失败阻止发布
  4. **SmartScreen 信誉**：
     - EV 证书：立即获得信誉，不触发 SmartScreen
     - OV 证书：需积累下载量，初期可能触发 SmartScreen
     - 建议使用 EV 证书
- **验收**: 签名后的安装器不触发 SmartScreen 警告；`signtool verify /pa` 通过

### 步骤11: 创建 WSL2 rootfs 构建脚本
- **文件**: `scripts/build-vm-image/build-wsl2.sh`
- **操作**: 新建
- **内容**: 构建 WSL2 发行版的 rootfs.tar.gz：
  1. **Docker 构建**：
     - 基于 `scripts/build-vm-image/Dockerfile` 构建
     - 运行容器后导出文件系统：`docker export <container> | gzip > deerflow-rootfs.tar.gz`
  2. **WSL2 优化**：
     - 安装 `init` 系统兼容层
     - Windows 11: 配置 systemd（WSL2 0.67.6+ 支持）
     - Windows 10: 使用 sysvinit
     - 配置 `/etc/wsl.conf`
     - 创建 `sandbox` 用户
     - 安装 Python 3.12 + Node.js 20 + 常用工具
  3. **大小优化**：
     - 清理 apt 缓存：`rm -rf /var/lib/apt/lists/*`
     - 清理 pip 缓存：`rm -rf /root/.cache/pip`
     - 删除不必要的文件：`/usr/share/doc/`、`/usr/share/man/`
     - 目标大小：~60MB（压缩后）
  4. **版本信息**：
     - 在 `/etc/deerflow-version` 写入版本号和构建时间
     - 用于后续版本检查和更新
- **验收**: 构建的 rootfs.tar.gz 可通过 `wsl --import` 成功导入，大小 < 70MB

## 验收标准
- [ ] WSL2 环境检测准确，能区分 WSL1 和 WSL2
- [ ] **启动向导内一键启用 WSL2 在 Windows 11 上工作正常**
- [ ] **Windows 10 上安装脚本正确处理 dism 方式和重启流程**
- [ ] DeerFlow 发行版可导入、启动、停止
- [ ] 命令执行返回正确的 stdout/stderr/exitCode
- [ ] 工作目录共享正常，双向可读写
- [ ] 发行版更新流程完整，用户数据保留
- [ ] 所有 Windows 特定错误有中文提示和恢复方案
- [ ] rootfs.tar.gz 可构建且大小 < 70MB
- [ ] **Windows 安装器代码签名通过，不触发 SmartScreen 警告**
- [ ] **重启后向导自动恢复，WSL2 安装继续**

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | WSL2Detector.detect() 已安装 | 返回 wslInstalled=true, wsl2Default=true |
| 单元测试 | WSL2Detector.detect() 未安装 | 返回 wslInstalled=false, issues 含安装建议 |
| 单元测试 | detectWindowsVersion() Win11 | isWindows11=true, installMethod="wsl_install" |
| 单元测试 | detectWindowsVersion() Win10 | isWindows10=true, installMethod="dism" |
| 单元测试 | WSL2Sandbox.init() 正常导入 | 发行版列表包含 "DeerFlow" |
| 单元测试 | WSL2Sandbox.execute("echo hello") | stdout="hello\n", exitCode=0 |
| 单元测试 | WSL2Sandbox.stop() | 发行版状态变为 Stopped |
| 集成测试 | 完整生命周期 | 导入→启动→执行→停止→注销 |
| 集成测试 | 工作目录共享 | Windows 写文件→WSL2 读取→WSL2 写文件→Windows 读取 |
| 集成测试 | 一键启用 WSL2 (Win11) | 向导内点击按钮 → 安装成功 → 重启提示 |
| 集成测试 | 一键启用 WSL2 (Win10) | dism 方式安装 → 重启 → 继续配置 |
| E2E 测试 | WSL2 安装+DeerFlow 配置 | 从无 WSL 到完整可用 |
| E2E 测试 | 重启后向导恢复 | 重启后自动继续向导，WSL2 已就绪 |
| 边界测试 | WSL 服务崩溃恢复 | 自动重启 WSL 服务后继续 |
| 边界测试 | 中文用户名路径 | 路径转换正确，无乱码 |
| 边界测试 | 企业环境限制 | 降级到本地模式，提示联系 IT |
| 签名测试 | 安装器签名验证 | `signtool verify /pa` 通过，无 SmartScreen |
| 性能测试 | 命令执行延迟 | < 200ms（不含命令本身耗时） |
| 性能测试 | 发行版启动时间 | < 3s |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| WSL 安装需要管理员权限 | 高 | **启动向导内自动请求 UAC 提权**；提供手动安装指南 |
| 企业环境禁止安装 WSL | 中 | 降级到本地模式；提供管理员安装指南 |
| /mnt/c 跨文件系统性能差 | 高 | 默认使用 WSL2 原生文件系统；通过 `\\wsl$` 路径从 Windows 访问 |
| WSL2 与 VMware/VirtualBox 冲突 | 中 | 提示升级 VirtualBox 6.1+；提供降级到本地模式选项 |
| Windows 更新后 WSL 行为变化 | 中 | 维护多版本兼容层；CI 测试多个 Windows 版本 |
| 中文路径编码问题 | 中 | 使用 8.3 短路径名；WSL2 原生文件系统避免此问题 |
| rootfs 构建体积过大 | 低 | 逐步优化 Dockerfile；使用多阶段构建 |
| Windows 10 安装流程复杂 | 高 | **一键启用脚本自动处理 dism 方式**；重启后自动继续；提供详细手动指南 |
| Windows 11 `wsl --install` 网络问题 | 中 | 提供离线安装包；降级到 dism 方式 |
| 安装器未签名触发 SmartScreen | 高 | **代码签名为必须步骤**；使用 EV 证书；CI 中集成签名 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.5.2 Windows WSL2 适配）
- Microsoft WSL 文档: https://learn.microsoft.com/en-us/windows/wsl/
- WSL --import 参考: https://learn.microsoft.com/en-us/windows/wsl/basic-commands#import
- WSL 文件系统互操作: https://learn.microsoft.com/en-us/windows/wsl/filesystems
- Windows 10 vs 11 WSL 差异: https://learn.microsoft.com/en-us/windows/wsl/compare-versions
- Windows 代码签名: https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools
