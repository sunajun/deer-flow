# T35 - 系统托盘 + 控制台 + 打包发布

## 元信息
- **任务ID**: T35
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P7
- **预估工期**: 6 天（增加代码签名必须步骤和增量更新机制）
- **依赖任务**: T29
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
实现系统托盘、控制台 UI、自动更新和打包发布流程。**代码签名是自动更新的前提条件**：macOS 上 electron-updater 仅对已签名且已公证的应用生效，Windows 上 SmartScreen 仅对已签名的安装器放行。必须将签名和公证作为发布流水线的**必须步骤**。

## 关键约束

### 代码签名与自动更新的关系
| 平台 | 未签名后果 | 签名要求 | 自动更新 |
|------|-----------|---------|---------|
| macOS | Gatekeeper 拦截，用户无法打开 | Developer ID Application 证书 + 公证 | **仅签名+公证应用可自动更新** |
| Windows | SmartScreen 警告，用户恐惧 | EV/OV 代码签名证书 | 未签名也可更新，但用户体验差 |
| Linux | 无限制 | AppImage 无需签名 | 无自动更新（需手动下载） |

## 详细实现步骤

### 步骤1: 系统托盘实现
- **文件**: `desktop/electron/tray.ts`
- **操作**: 新建
- **内容**: 实现系统托盘功能：
  1. **托盘图标**：
     - 默认图标：DeerFlow Logo（16x16 / 32x32）
     - 状态图标：运行中（绿色）、错误（红色）、更新可用（蓝色）
     - macOS: 使用 Template 图标（自动适配深色/浅色模式）
     - Windows: 使用 .ico 格式
     - Linux: 使用 .png 格式
  2. **托盘菜单**：
     ```
     DeerFlow (版本号)
     ─────────────
     🟢 运行中 / 🔴 已停止
     ─────────────
     打开主窗口
     沙箱状态 →  ▸ macOS VM / WSL2 / Firecracker / 本地模式
     ─────────────
     暂停沙箱 / 恢复沙箱
     重启后端
     ─────────────
     检查更新...
     ─────────────
     偏好设置...
     ─────────────
     退出 DeerFlow
     ```
  3. **托盘事件**：
     - 单击（macOS/Linux）：显示/隐藏主窗口
     - 双击（Windows）：显示主窗口
     - 右键：显示上下文菜单
  4. **状态指示**：
     - 后端状态变化时更新托盘图标和菜单
     - VM 状态变化时更新沙箱状态子菜单
     - 更新可用时在托盘图标上显示蓝色标记
  5. **通知**：
     - 后端启动成功：通知"DeerFlow 已就绪"
     - 后端错误：通知"后端异常，点击查看"
     - 更新可用：通知"新版本可用"
     - 更新下载完成：通知"点击重启安装更新"
- **验收**: 托盘图标显示正确；菜单项功能正常；状态变化时图标/菜单更新

### 步骤2: 控制台 UI 组件
- **文件**: `desktop/src/console/ConsolePanel.tsx`
- **操作**: 新建
- **内容**: 实现控制台面板组件：
  1. **布局**：
     - 底部抽屉式面板，可拖拽调整高度
     - 默认高度 200px，最小 100px，最大 600px
     - 可通过快捷键 `Ctrl+Shift+C` 切换显示/隐藏
  2. **Tab 页**：
     - **输出**：Agent 执行日志（实时流式显示）
     - **沙箱**：VM 状态、命令执行日志
     - **网络**：API 请求/响应日志
     - **系统**：后端启动日志、错误信息
  3. **输出 Tab**：
     - 实时显示 Agent 思考和执行过程
     - 语法高亮（代码块）
     - 可折叠的执行步骤
     - 搜索/过滤功能
  4. **沙箱 Tab**：
     - VM 状态指示器（运行中/已停止/错误）
     - 命令执行历史（时间戳 + 命令 + 退出码）
     - 点击命令展开 stdout/stderr
     - 快照列表和操作按钮
  5. **网络 Tab**：
     - API 请求列表（方法 + URL + 状态码 + 耗时）
     - 点击展开请求/响应详情
     - 请求体/响应体 JSON 格式化
  6. **系统 Tab**：
     - 后端启动日志（带时间戳）
     - Python 版本、工作目录
     - 错误日志高亮显示
     - 一键复制错误信息
  7. **通用功能**：
     - 自动滚动到底部（可关闭）
     - 清空日志按钮
     - 导出日志到文件
     - 字体大小调整
- **验收**: 控制台面板可显示/隐藏；四个 Tab 内容正确；实时日志流式显示

### 步骤3: 控制台子组件
- **文件**: `desktop/src/console/` 目录下多个文件
- **操作**: 新建
- **内容**:
  1. `OutputTab.tsx` — Agent 执行日志
  2. `SandboxTab.tsx` — 沙箱状态和命令日志
  3. `NetworkTab.tsx` — API 请求日志
  4. `SystemTab.tsx` — 系统日志
  5. `LogEntry.tsx` — 单条日志组件
  6. `ConsoleToolbar.tsx` — 控制台工具栏
- **验收**: 每个组件可独立渲染，交互正确

### 步骤4: 控制台日志收集
- **文件**: `desktop/electron/logger.ts`
- **操作**: 新建
- **内容**: 实现日志收集和分发系统：
  1. **日志源**：
     - Python 后端 stdout/stderr
     - Electron 主进程日志
     - VM 状态变化事件
     - API 请求/响应（拦截 HTTP）
  2. **日志格式**：
     ```typescript
     interface LogEntry {
         id: string;
         timestamp: number;
         level: "debug" | "info" | "warn" | "error";
         source: "backend" | "electron" | "sandbox" | "network";
         message: string;
         data?: any;
     }
     ```
  3. **日志传输**：
     - 主进程 → 渲染进程：通过 IPC `console:log` 通道
     - 渲染进程订阅：`window.deerflow.onConsoleLog(callback)`
  4. **日志持久化**：
     - 写入文件：`~/DeerFlow/logs/deerflow-{date}.log`
     - 日志轮转：保留最近 7 天
     - 单文件最大 10MB
  5. **性能保护**：
     - 日志缓冲：100ms 批量发送
     - 最大缓冲 1000 条，超出丢弃最旧的
     - 控制台未打开时不发送到渲染进程
- **验收**: 日志正确收集和分发；文件持久化正常；性能无明显影响

### 步骤5: 自动更新实现
- **文件**: `desktop/electron/updater.ts`
- **操作**: 新建
- **内容**: 实现 electron-updater 自动更新：
  1. **更新检查**：
     - 启动后 30s 检查一次
     - 之后每 4 小时检查一次
     - 用户可手动触发检查
     - 使用 GitHub Provider：`https://github.com/deerflow/deerflow/releases`
  2. **更新流程**：
     ```
     检查更新 → 发现新版本 → 下载 → 安装提示 → 重启
     ```
  3. **macOS 更新（必须签名+公证）**：
     - **electron-updater 在 macOS 上仅对已签名且已公证的应用生效**
     - 未签名应用无法使用自动更新功能
     - DMG 格式更新包必须签名
     - 更新包必须公证（notarized）
     - 代码签名验证：`electron-updater` 会验证更新包的签名
     - 签名不匹配时拒绝安装
  4. **Windows 更新**：
     - NSIS 安装器更新
     - 安装器必须签名（避免 SmartScreen 拦截）
     - 支持增量更新（见步骤6）
  5. **Linux 更新**：
     - AppImage 无自动更新
     - 提示用户手动下载新版本
     - 或使用 AppImageUpdate（支持 zsync 增量更新）
  6. **更新通知**：
     - 托盘通知
     - 主窗口内通知条
     - 用户可选择"稍后提醒"或"立即更新"
  7. **回滚机制**：
     - 更新前备份当前版本
     - 更新后首次启动失败时自动回滚
     - 回滚日志记录
  8. **更新配置**：
     ```typescript
     autoUpdater.autoDownload = false;  // 不自动下载，先通知用户
     autoUpdater.autoInstallOnAppQuit = true;  // 退出时自动安装
     autoUpdater.allowPrerelease = false;  // 不安装预发布版本
     ```
- **验收**: macOS 签名+公证应用可自动更新；Windows 签名安装器可自动更新；Linux 提示手动更新

### 步骤6: 增量更新机制
- **文件**: `desktop/electron/incremental-updater.ts`
- **操作**: 新建
- **内容**: **核心改进：增量更新减少下载量**：
  1. **增量更新原理**：
     - 计算新旧版本的二进制差异（bsdiff/xdelta）
     - 仅下载差异部分（通常 1-10MB vs 完整 100MB+）
     - 本地重建新版本
  2. **实现方案**：
     - **macOS**：使用 electron-updater 的 blockmap 增量更新
       - electron-builder 自动生成 blockmap 文件
       - electron-updater 支持基于 blockmap 的增量下载
       - 仅下载变化的 block
     - **Windows**：使用 NSIS 的差异补丁
       - electron-builder NSIS 支持 differential updater
       - 配置 `differentialPackage: true`
     - **Linux**：使用 AppImageUpdate + zsync
       - 生成 `.zsync` 元数据文件
       - AppImageUpdate 使用 zsync 增量下载
  3. **配置**：
     ```yaml
     # electron-builder.yml
     mac:
       publish:
         provider: github
     win:
       publish:
         provider: github
     linux:
       publish:
         provider: github
     # 启用差异更新
     mac:
       extendInfo:
         NSAppTransportSecurity:
           NSAllowsArbitraryLoads: true
     ```
  4. **回退策略**：
     - 增量更新失败时自动回退到全量更新
     - 首次安装必须使用全量包
     - 跨大版本更新使用全量包
  5. **更新大小监控**：
     - 记录每次更新的下载大小
     - 增量 vs 全量对比
     - 目标：增量更新大小 < 全量的 20%
- **验收**: 小版本更新时增量下载生效；增量失败时自动回退到全量

### 步骤7: macOS 代码签名与公证（必须步骤）
- **文件**: `desktop/scripts/sign/notarize-macos-app.sh`
- **操作**: 新建
- **内容**: macOS 应用**必须签名且公证**才能正常使用和自动更新：
  1. **签名流程**：
     ```bash
     # 1. 签名所有内嵌二进制
     find "DeerFlow.app/Contents/Resources" -type f \( -name "*.dylib" -o -name "*.so" -perm +111 \) \
         -exec codesign --force --options runtime \
         --entitlements assets/entitlements.mac.plist \
         --sign "Developer ID Application: DeerFlow Team" {} \;

     # 2. 签名 Swift CLI
     codesign --force --options runtime \
         --entitlements assets/entitlements.sandbox.plist \
         --sign "Developer ID Application: DeerFlow Team" \
         DeerFlow.app/Contents/Resources/DeerFlowSandboxCLI

     # 3. 签名 Python 后端二进制
     codesign --force --options runtime \
         --sign "Developer ID Application: DeerFlow Team" \
         DeerFlow.app/Contents/Resources/python-backend/deerflow-backend

     # 4. 签名主应用
     codesign --force --options runtime \
         --entitlements assets/entitlements.mac.plist \
         --sign "Developer ID Application: DeerFlow Team" \
         DeerFlow.app
     ```
  2. **公证流程**：
     ```bash
     # 1. 创建 DMG
     hdiutil create DeerFlow.dmg -srcfolder DeerFlow.app

     # 2. 提交公证
     xcrun notarytool submit DeerFlow.dmg \
         --apple-id "$APPLE_ID" \
         --password "$APPLE_APP_PASSWORD" \
         --team-id "$APPLE_TEAM_ID" \
         --wait

     # 3. Staple 公证票据
     xcrun stapler staple DeerFlow.dmg
     ```
  3. **electron-builder 自动签名配置**：
     ```yaml
     mac:
       hardenedRuntime: true
       gatekeeperAssess: false
       entitlements: assets/entitlements.mac.plist
       entitlementsInherit: assets/entitlements.mac.inherit.plist
       identity: "Developer ID Application: DeerFlow Team (XXXXXXXXXX)"
       notarize:
         teamId: "XXXXXXXXXX"
     ```
  4. **CI 集成**：
     - 证书和密码存储在 GitHub Secrets
     - CI 中自动安装证书到 Keychain
     - 构建后自动签名和公证
     - **签名或公证失败阻止发布**
  5. **关键说明**：
     - **未签名应用无法在 macOS 上正常打开**
     - **未公证应用在 macOS 12+ 上被 Gatekeeper 拦截**
     - **electron-updater 仅对已签名+公证的应用生效**
     - 开发阶段可用 `xattr -cr DeerFlow.app` 绕过，但**不可用于发布**
- **验收**: 签名+公证后的 DMG 在全新 macOS 上双击安装无警告；自动更新正常工作

### 步骤8: Windows 安装器签名（必须步骤）
- **文件**: `desktop/scripts/sign/sign-windows-release.sh`
- **操作**: 新建
- **内容**: Windows 安装器**必须签名**：
  1. **签名所有可执行文件**：
     ```bash
     # 签名 Python 后端
     signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 \
         /f "$WIN_CERT_FILE" /p "$WIN_CERT_PASSWORD" \
         deerflow-backend.exe

     # 签名 NSIS 安装器
     signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 \
         /f "$WIN_CERT_FILE" /p "$WIN_CERT_PASSWORD" \
         DeerFlow-Setup-0.1.0.exe
     ```
  2. **electron-builder 自动签名**：
     ```yaml
     win:
       certificateFile: "${WIN_CERT_FILE}"
       certificatePassword: "${WIN_CERT_PASSWORD}"
       signAndEditExecutable: true
       signingHashAlgorithms:
         - sha256
       rfc3161TimeStampServer: "http://timestamp.digicert.com"
     ```
  3. **SmartScreen 信誉**：
     - EV 证书：立即获得信誉
     - OV 证书：需积累下载量
     - 建议：首次发布使用 EV 证书
  4. **CI 集成**：
     - 证书存储在 GitHub Secrets
     - CI 中自动签名
     - **签名失败阻止发布**
- **验收**: 签名后的安装器不触发 SmartScreen 警告

### 步骤9: Linux AppImage 打包
- **文件**: `desktop/electron-builder.yml`（Linux 部分）
- **操作**: 改造
- **内容**: Linux AppImage 打包配置和要求：
  1. **AppImage 配置**：
     ```yaml
     linux:
       target:
         - target: AppImage
           arch:
             - x64
       icon: assets/icon.png
       category: Development
       maintainer: "DeerFlow Team"
       vendor: "DeerFlow"
       synopsis: "DeerFlow Desktop - AI Agent with VM Sandbox"
       description: "DeerFlow is an AI agent platform with lightweight VM sandbox for secure code execution."
     ```
  2. **AppImage 特殊要求**：
     - AppImage 是自包含的，无需安装
     - 需要 FUSE 才能运行：`sudo apt install libfuse2`
     - 无 FUSE 时可使用 `--appimage-extract` 解压运行
     - **AppImage 无需代码签名**（Linux 无此要求）
     - **AppImage 无自动更新**（需手动下载或使用 AppImageUpdate）
  3. **AppImage 内嵌资源**：
     - Python 后端二进制
     - Firecracker 二进制（仅 Linux）
     - VM 镜像（首次运行时下载，不内嵌）
     - DeerFlowSandboxCLI 不需要（Linux 不使用 Swift）
  4. **桌面集成**：
     - 生成 `.desktop` 文件
     - 注册 MIME 类型
     - 注册 `deerflow://` 协议
  5. **AppImageUpdate 支持**：
     - 生成 `.zsync` 文件用于增量更新
     - 用户可使用 AppImageUpdate 工具更新
     - 在应用内提示用户使用 AppImageUpdate
- **验收**: AppImage 可在 Ubuntu 22.04/24.04 上运行；桌面集成正常

### 步骤10: 偏好设置页面
- **文件**: `desktop/src/settings/SettingsPage.tsx`
- **操作**: 新建
- **内容**: 实现偏好设置页面：
  1. **通用设置**：
     - 启动时自动启动后端
     - 关闭窗口时行为（最小化到托盘/退出）
     - 日志级别
     - 数据目录
  2. **沙箱设置**：
     - 沙箱策略选择（STRICT/SELECTIVE/LOCAL）
     - VM 内存大小
     - VM CPU 核心数
     - 工作目录路径
     - 自动降级开关
  3. **API 设置**：
     - LLM Provider 配置
     - API Key 管理
     - 代理设置
  4. **更新设置**：
     - 自动检查更新开关
     - 更新频道（stable/beta）
     - 上次检查时间
  5. **关于页面**：
     - 版本号
     - 检查更新按钮
     - 开源许可
     - 反馈链接
- **验收**: 设置页面所有选项可修改并持久化

### 步骤11: 主窗口布局
- **文件**: `desktop/src/App.tsx`
- **操作**: 新建
- **内容**: 实现主窗口布局：
  1. **布局结构**：
     ```
     ┌────────────────────────────────────────┐
     │ 标题栏（拖拽区域）+ 窗口控制按钮       │
     ├────────────────────────────────────────┤
     │                                        │
     │            主内容区域                   │
     │         （DeerFlow Web UI）             │
     │                                        │
     ├────────────────────────────────────────┤
     │ 控制台面板（可折叠）                    │
     └────────────────────────────────────────┘
     ```
  2. **标题栏**：
     - 自定义标题栏（frameless window）
     - 拖拽区域
     - 最小化/最大化/关闭按钮
     - 沙箱状态指示器
  3. **主内容区域**：
     - 嵌入 DeerFlow Web UI（iframe 或直接渲染）
     - 开发模式：加载 localhost:3000
     - 生产模式：加载本地构建的 HTML
  4. **控制台面板**：
     - 底部抽屉，可拖拽调整高度
     - 快捷键 `Ctrl+Shift+C` 切换
- **验收**: 主窗口布局正确；控制台可折叠；Web UI 正常渲染

### 步骤12: 发布流水线
- **文件**: `.github/workflows/release-desktop.yml`
- **操作**: 新建
- **内容**: 实现完整的桌面应用发布流水线：
  1. **触发条件**：
     - tag `v*` 推送
     - 手动触发
  2. **构建矩阵**：
     ```yaml
     strategy:
       matrix:
         include:
           - os: macos-latest
             platform: mac
           - os: windows-latest
             platform: win
           - os: ubuntu-latest
             platform: linux
     ```
  3. **构建步骤**：
     - Checkout 代码
     - 安装 Node.js + pnpm
     - 构建 Python 后端（PyInstaller）
     - 运行 Python 后端冒烟测试
     - 构建前端
     - 打包 Electron 应用
     - **代码签名**（macOS/Windows）
     - **公证**（macOS）
     - 上传构建产物
  4. **发布步骤**：
     - 创建 GitHub Release
     - 上传三平台安装包
     - 生成 latest-mac.yml、latest-linux.yml
     - 更新自动更新 manifest
  5. **质量门禁**：
     - **冒烟测试必须通过**
     - **代码签名必须通过**
     - **macOS 公证必须通过**
     - 任何步骤失败阻止发布
  6. **回滚**：
     - 发布后发现严重问题时可快速回滚
     - 保留最近 3 个版本的下载链接
- **验收**: 完整的 tag → 构建 → 签名 → 公证 → 发布流水线可用

### 步骤13: 应用图标和资源
- **文件**: `desktop/assets/`
- **操作**: 新建
- **内容**: 准备应用图标和资源文件：
  1. `icon.icns` — macOS 图标（1024x1024）
  2. `icon.ico` — Windows 图标（256x256）
  3. `icon.png` — Linux 图标（512x512）
  4. `tray-iconTemplate.png` — macOS 托盘图标（Template 格式）
  5. `tray-icon.png` — Windows/Linux 托盘图标
  6. `entitlements.mac.plist` — macOS 权限声明
  7. `entitlements.mac.inherit.plist` — macOS 子进程权限
  8. `entitlements.sandbox.plist` — Swift CLI 权限
- **验收**: 图标在各平台显示正确；权限声明完整

## 验收标准
- [ ] 系统托盘图标显示，菜单功能正常
- [ ] 控制台面板四个 Tab 内容正确，实时日志流式显示
- [ ] 自动更新在 macOS（签名+公证）上正常工作
- [ ] 自动更新在 Windows（签名安装器）上正常工作
- [ ] Linux AppImage 可正常运行
- [ ] **macOS 代码签名和公证通过，全新 Mac 上安装无警告**
- [ ] **Windows 安装器签名通过，不触发 SmartScreen**
- [ ] **增量更新在小版本升级时生效**
- [ ] 偏好设置页面所有选项可修改并持久化
- [ ] 主窗口布局正确，Web UI 正常渲染
- [ ] 发布流水线可自动构建、签名、公证、发布三平台安装包
- [ ] 日志持久化和轮转正常

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | 托盘菜单点击 | 对应功能触发 |
| 单元测试 | 控制台日志缓冲 | 100ms 批量发送 |
| 单元测试 | 日志轮转 | 超过 7 天的日志被删除 |
| 集成测试 | 托盘 → 主窗口 | 单击托盘图标显示/隐藏主窗口 |
| 集成测试 | 控制台实时日志 | Agent 执行时日志实时显示 |
| 集成测试 | 自动更新检测 | 发现新版本时通知用户 |
| 集成测试 | 增量更新下载 | 小版本更新下载量 < 全量的 20% |
| E2E 测试 | 完整更新流程 | 检查 → 下载 → 安装 → 重启 → 新版本 |
| E2E 测试 | macOS 签名+公证应用 | 全新 Mac 上安装无 Gatekeeper 警告 |
| E2E 测试 | macOS 自动更新 | 签名+公证应用可自动更新 |
| E2E 测试 | Windows 签名安装器 | 不触发 SmartScreen |
| E2E 测试 | Linux AppImage 运行 | 双击可运行，桌面集成正常 |
| E2E 测试 | 偏好设置持久化 | 修改设置后重启应用设置保留 |
| 边界测试 | 更新中断恢复 | 下载中断后可恢复或重新下载 |
| 边界测试 | 增量更新失败回退 | 自动回退到全量更新 |
| 边界测试 | 日志文件过大 | 超过 10MB 时轮转 |
| 性能测试 | 控制台日志性能 | 1000 条/秒日志不影响 UI |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| macOS 未签名应用无法打开 | 高 | **代码签名和公证为必须步骤**；提前准备 Apple Developer 账号；CI 中集成签名和公证 |
| macOS 自动更新不工作 | 高 | **electron-updater 仅对签名+公证应用生效**；确保签名和公证流程正确；测试自动更新 |
| Windows SmartScreen 拦截 | 高 | **安装器签名为必须步骤**；使用 EV 证书；CI 中集成签名 |
| electron-updater 与 electron-builder 版本不兼容 | 中 | 固定版本号；测试更新流程 |
| AppImage 在某些 Linux 发行版上不工作 | 中 | 提供备选安装方式（deb/rpm）；文档说明 FUSE 依赖 |
| 增量更新差异计算错误 | 低 | 增量失败时自动回退到全量；保留全量更新包 |
| 公证耗时过长影响发布 | 中 | 公证通常 2-5 分钟；CI 中使用 `--wait` 等待；超时时报警 |
| 控制台日志量过大影响性能 | 中 | 日志缓冲和限流；最大缓冲 1000 条；控制台未打开时不发送到渲染进程 |
| Apple Developer 证书过期 | 低 | 设置证书过期提醒；提前续期；CI 中检测证书有效期 |
| Windows 代码签名证书硬件令牌 | 中 | EV 证书可能需要 USB 令牌；CI 中使用云签名服务（如 DigiCert ONE） |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.3 整体打包架构、7.8 首次启动向导）
- electron-updater 文档: https://www.electron.build/auto-update
- electron-builder 代码签名: https://www.electron.build/code-signing
- Apple 公证指南: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- Windows 代码签名: https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools
- AppImage 文档: https://docs.appimage.org/
- AppImageUpdate: https://github.com/AppImage/AppImageUpdate
- electron-builder 增量更新: https://www.electron.build/auto-update#differential-updating
