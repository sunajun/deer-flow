# T29 - Electron 骨架 + 内嵌 Python 后端 + 启动向导

## 元信息
- **任务ID**: T29
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P1
- **预估工期**: 4 天（增加 PyInstaller 隐式导入扫描和冒烟测试）
- **依赖任务**: 无
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
搭建 Electron 桌面应用骨架，内嵌 PyInstaller/Nuitka 打包的 Python 后端子进程，实现首次启动向导，为后续沙箱适配和桌面端功能奠定基础。重点解决 FastAPI + LangGraph + LangChain 的隐式导入问题，确保打包后功能完整。

## 详细实现步骤

### 步骤1: 创建 desktop/ 项目结构
- **文件**: `desktop/package.json`
- **操作**: 新建
- **内容**: 定义 Electron 桌面端项目，包含以下依赖：
  - `electron` (^33.x) 作为主框架
  - `electron-builder` 用于打包
  - `electron-updater` 用于自动更新
  - `react` (^19.x) + `react-dom` 用于渲染进程 UI
  - `typescript` (^5.8.x) 编译
  - `vite` + `vite-plugin-electron` 构建
  - `@electron/remote` 主进程与渲染进程通信
  - 项目名 `deerflow-desktop`，版本 `0.1.0`
  - scripts: `dev`（开发模式热重载）、`build`（构建前端）、`pack`（打包桌面应用）、`dist`（分发打包）
- **验收**: `cd desktop && pnpm install` 成功，无依赖冲突

### 步骤2: Electron 主进程实现
- **文件**: `desktop/electron/main.ts`
- **操作**: 新建
- **内容**: 实现以下核心逻辑：
  1. **窗口管理**：
     - `createMainWindow()`: 创建 BrowserWindow，加载 `dist/index.html`（生产）或 `localhost:3000`（开发）
     - 窗口尺寸 1280x800，最小 960x600，默认最大化
     - 窗口关闭时隐藏到托盘而非退出（`close` 事件 `e.preventDefault()`）
     - 支持 macOS `window-all-closed` 不退出应用
  2. **应用生命周期**：
     - `app.whenReady()`: 初始化窗口、系统托盘、Python 后端
     - `app.before-quit()`: 优雅关闭 Python 后端子进程、停止 VM
     - `app.activate()` (macOS): 重新创建窗口
  3. **单实例锁**：`app.requestSingleInstanceLock()`，第二实例时聚焦已有窗口
  4. **协议注册**：注册 `deerflow://` 深度链接协议，用于外部调用
  5. **启动顺序**：先启动 Python 后端 → 等待健康检查通过 → 打开主窗口
- **验收**: `pnpm dev` 启动后能弹出 Electron 窗口，console 无报错

### 步骤3: 预加载脚本实现
- **文件**: `desktop/electron/preload.ts`
- **操作**: 新建
- **内容**: 通过 `contextBridge.exposeInMainWorld` 暴露以下 API 给渲染进程：
  1. **系统信息**：
     - `getPlatform(): string` — 返回 `darwin` / `win32` / `linux`
     - `getAppVersion(): string` — 应用版本号
  2. **Python 后端状态**：
     - `onBackendStatus(callback: (status: string) => void): void` — 监听后端状态变化（starting/ready/error/stopped）
     - `restartBackend(): Promise<void>` — 重启后端
  3. **沙箱检测**：
     - `detectSandbox(): Promise<{type: string, available: boolean}>` — 检测当前平台可用沙箱
  4. **文件系统**：
     - `selectDirectory(): Promise<string | null>` — 打开目录选择对话框
     - `openInExplorer(path: string): void` — 在系统文件管理器中打开
  5. **深度链接**：
     - `onDeepLink(callback: (url: string) => void): void` — 监听 deerflow:// 协议调用
  6. **自动更新**：
     - `onUpdateAvailable(callback: (info: any) => void): void`
     - `onUpdateDownloaded(callback: () => void): void`
     - `installUpdate(): void` — 安装已下载的更新
  7. 类型定义导出到 `desktop/electron/preload.d.ts`
- **验收**: 渲染进程 `window.deerflow` 可访问上述 API，TypeScript 类型正确

### 步骤4: Python 后端子进程管理
- **文件**: `desktop/electron/python-backend.ts`
- **操作**: 新建
- **内容**: 实现 `PythonBackendManager` 类：
  1. **后端路径解析**：
     - 开发模式：使用 `../../backend/` 目录，通过 `uv run` 启动
     - 生产模式：使用 `resources/python-backend/deerflow-backend`（PyInstaller 单文件可执行文件）
     - 路径通过 `process.resourcesPath` + 平台判断确定
  2. **启动流程**：
     - `start()`: spawn Python 后端子进程
     - 传入环境变量：`DEER_FLOW_CONFIG_PATH`、`GATEWAY_PORT=8001`、`GATEWAY_HOST=127.0.0.1`
     - 捕获 stdout/stderr，解析关键日志判断启动阶段
  3. **健康检查**：
     - 启动后轮询 `http://127.0.0.1:8001/api/health`（最多 30 次，间隔 1s）
     - 健康检查通过后通过 IPC 通知渲染进程 `backend-status: ready`
     - 健康检查超时（30s）后通知 `backend-status: error`，附带错误信息
  4. **优雅关闭**：
     - `stop()`: 先发送 SIGTERM，等待 5s
     - 若未退出则 SIGKILL 强制终止
     - Windows 使用 `taskkill /PID /F` 作为后备
  5. **异常处理**：
     - 子进程意外退出时自动重启（最多 3 次，间隔 10s）
     - 重启失败后通知渲染进程显示错误页面
  6. **端口冲突检测**：
     - 启动前检查 8001 端口是否被占用
     - 被占用时自动选择下一个可用端口（8002-8010）
     - 端口变更通知渲染进程
- **验收**:
  - 开发模式：`PythonBackendManager` 能启动 Python 后端，健康检查通过
  - 模拟 PyInstaller 模式：能在 `resources/` 目录放置二进制并成功启动
  - 关闭 Electron 时 Python 后端进程被正确终止

### 步骤5: PyInstaller 隐式导入扫描
- **文件**: `desktop/scripts/scan-hidden-imports.py`
- **操作**: 新建
- **内容**: 自动扫描 FastAPI + LangGraph + LangChain 的隐式导入，生成 hidden-imports 列表：
  1. **扫描原理**：
     - 使用 `importlib` 动态导入所有 deerflow 后端模块
     - 递归遍历 `sys.modules` 收集所有已加载模块名
     - 使用 `pkgutil.walk_packages` 发现子包
     - 对比 PyInstaller 静态分析结果，找出遗漏的隐式导入
  2. **已知隐式导入清单**：
     ```python
     KNOWN_HIDDEN_IMPORTS = [
         # FastAPI / Starlette
         "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
         "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
         "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
         "uvicorn.lifespan", "uvicorn.lifespan.on",
         "starlette.responses", "starlette.routing", "starlette.middleware",
         # LangChain
         "langchain_community", "langchain_core", "langchain_openai",
         "langchain_anthropic", "langchain_text_splitters",
         # LangGraph
         "langgraph", "langgraph.graph", "langgraph.prebuilt",
         "langgraph.checkpoint", "langgraph.pregel",
         # Pydantic
         "pydantic.deprecated.decorator", "pydantic._internal._generate_schema",
         # HTTP 客户端
         "httpx", "httpcore", "anyio", "sniffio",
         # YAML / 配置
         "yaml", "pyyaml",
         # 其他
         "multidict", "yarl", "frozenlist", "aiosignal",
     ]
     ```
  3. **扫描脚本**：
     ```python
     def scan_hidden_imports(package_path: str) -> list[str]:
         sys.path.insert(0, package_path)
         import app.gateway.main
         import app.config
         modules = sorted(sys.modules.keys())
         hidden = [m for m in modules if not any(
             m.startswith(prefix) for prefix in ["_frozen_importlib", "importlib", "encodings"]
         )]
         return hidden
     ```
  4. **输出格式**：
     - 生成 `desktop/scripts/hidden-imports.txt`，每行一个模块名
     - 供 PyInstaller spec 文件引用
  5. **CI 集成**：
     - 每次 `backend/` 目录变更时自动运行扫描
     - 扫描结果与 `hidden-imports.txt` 对比，有新增时 CI 报警
- **验收**: 扫描脚本能发现至少 50 个隐式导入；打包后启动不出现 `ModuleNotFoundError`

### 步骤6: PyInstaller 打包配置
- **文件**: `desktop/scripts/build-backend.spec`
- **操作**: 新建
- **内容**: PyInstaller spec 文件，用于将 Python 后端打包为单文件可执行：
  1. **入口点**：`backend/app/gateway/main.py` → `deerflow-backend`
  2. **数据文件包含**：
     - `backend/packages/` 全部 Python 包
     - `skills/public/` 内置技能
     - `config.example.yaml` 默认配置模板
  3. **隐式导入**：
     - 从 `hidden-imports.txt` 读取所有隐式导入
     - LangChain、LangGraph、FastAPI、uvicorn 等动态加载模块
     - 使用步骤5的扫描结果自动填充
  4. **排除项**：`tests/`、`docs/`、`*.pyc`、`__pycache__`、`.git/`
  5. **平台特定**：
     - macOS: `--target-architecture universal2`
     - Windows: 单文件 `--onefile`，icon 设置
     - Linux: 单文件 `--onefile`
  6. **构建脚本** `desktop/scripts/build-backend.sh`：
     - 检测平台 → 运行隐式导入扫描 → 调用 `pyinstaller`
     - 输出到 `desktop/resources/python-backend/`
     - 构建后执行冒烟测试（见步骤7）
- **验收**: 在 macOS 上执行 `./desktop/scripts/build-backend.sh` 生成可执行文件

### 步骤7: 打包后冒烟测试
- **文件**: `desktop/scripts/smoke-test.sh`
- **操作**: 新建
- **内容**: PyInstaller 打包后必须执行的冒烟测试，确保所有功能正常：
  1. **启动测试**：
     - 执行打包后的 `deerflow-backend` 二进制
     - 等待健康检查通过（`/api/health` 返回 200）
     - 超时 30s 则标记失败
  2. **核心 API 测试**：
     - `GET /api/health` → 200
     - `GET /api/config` → 200（验证配置加载正常）
     - `POST /api/chat/completions` → 验证 LangChain/LangGraph 调用链完整
     - `GET /api/skills` → 200（验证技能加载正常）
  3. **隐式导入验证**：
     - 通过 API 触发涉及 LangChain/LangGraph 的完整调用链
     - 确认无 `ModuleNotFoundError` 或 `ImportError`
     - 检查 stderr 日志中无导入相关警告
  4. **资源清理**：
     - 测试完成后终止后端进程
     - 报告测试结果（PASS/FAIL + 详情）
  5. **CI 集成**：
     - 打包步骤后自动执行冒烟测试
     - 冒烟测试失败则阻止发布
  6. **多平台冒烟测试**：
     - macOS: 在 universal2 架构上测试
     - Windows: 在 x64 上测试
     - Linux: 在 x64 上测试
- **验收**: 打包后的二进制通过所有冒烟测试用例，无 `ModuleNotFoundError`

### 步骤8: Nuitka 替代方案评估与备选
- **文件**: `desktop/scripts/build-backend-nuitka.sh`
- **操作**: 新建
- **内容**: 作为 PyInstaller 的替代方案，评估并准备 Nuitka 打包脚本：
  1. **Nuitka 优势**：
     - 编译为原生代码，无需运行时解压，启动速度更快
     - 自动跟踪所有导入，隐式导入问题更少
     - 更好的反逆向保护
     - 生成更小的二进制（配合 `--lto=yes`）
  2. **Nuitka 劣势**：
     - 需要 C 编译器（macOS: Xcode CLT, Windows: MSVC, Linux: gcc）
     - 编译时间更长（5-15 分钟 vs PyInstaller 的 1-3 分钟）
     - 某些动态特性（如 `eval`、`exec`）需要显式标记
  3. **构建脚本**：
     ```bash
     #!/bin/bash
     set -euo pipefail
     python -m nuitka \
         --standalone \
         --onefile \
         --lto=yes \
         --output-filename=deerflow-backend \
         --output-dir=resources/python-backend/ \
         --include-data-dir=backend/packages=packages \
         --include-data-dir=skills/public=skills \
         --enable-plugin=pydantic \
         --enable-plugin=anti-bloat \
         --follow-import-to=app \
         --follow-import-to=langchain \
         --follow-import-to=langgraph \
         backend/app/gateway/main.py
     ```
  4. **决策标准**：
     - 如果 PyInstaller 冒烟测试频繁失败 → 切换到 Nuitka
     - 如果启动速度 > 10s → 评估 Nuitka
     - 如果打包体积 > 200MB → 评估 Nuitka
  5. **双轨并行**：
     - CI 中同时运行 PyInstaller 和 Nuitka 构建
     - 对比两者的冒烟测试结果和性能指标
- **验收**: Nuitka 构建脚本可生成可执行文件；冒烟测试通过；记录与 PyInstaller 的对比数据

### 步骤9: macOS 代码签名设置
- **文件**: `desktop/scripts/sign/setup-macos-signing.sh`
- **操作**: 新建
- **内容**: macOS 代码签名前置准备（**必须步骤，非可选**）：
  1. **Apple Developer 账号准备**：
     - 注册 Apple Developer Program（$99/年）
     - 创建 Developer ID Application 证书
     - 下载并安装证书到 Keychain
  2. **证书配置**：
     ```bash
     security import developer-id.p12 -k ~/Library/Keychains/build.keychain \
         -P "$CERT_PASSWORD" -T /usr/bin/codesign
     security unlock-keychain -p "$KEYCHAIN_PASSWORD" ~/Library/Keychains/build.keychain
     ```
  3. **Entitlements 文件**：
     - `desktop/assets/entitlements.mac.plist`：JIT、虚拟化、无符号内存权限
     - `desktop/assets/entitlements.mac.inherit.plist`：子进程继承权限
  4. **签名验证**：
     - `codesign --verify --deep --strict --verbose=2 deerflow-backend`
     - `codesign -dvvv deerflow-backend`
  5. **CI 集成**：
     - 证书存储在 GitHub Secrets（base64 编码）
     - CI 中自动安装证书并签名
     - 签名失败阻止发布
  6. **关键说明**：
     - **macOS 上未签名的应用无法被用户正常打开**（Gatekeeper 拦截）
     - **electron-updater 自动更新仅对签名应用生效**
     - 开发阶段可使用 `xattr -cr` 绕过，但不可用于发布
- **验收**: 签名后的二进制通过 `codesign --verify`；用户双击可正常打开

### 步骤10: Windows 代码签名设置
- **文件**: `desktop/scripts/sign/setup-windows-signing.sh`
- **操作**: 新建
- **内容**: Windows 代码签名前置准备（**必须步骤，非可选**）：
  1. **代码签名证书获取**：
     - 推荐 EV 证书（立即获得 SmartScreen 信誉）
     - 或 OV 证书（需逐步建立信誉）
     - 供应商：DigiCert、Sectigo、GlobalSign
  2. **签名工具**：
     - Windows SDK 自带 `signtool.exe`
     - 时间戳服务器：`http://timestamp.digicert.com`
     - 签名命令：
       ```bash
       signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 \
           /f deerflow-cert.pfx /p "$CERT_PASSWORD" deerflow-backend.exe
       ```
  3. **CI 集成**：
     - 证书存储在 GitHub Secrets
     - CI 中使用 `signtool` 签名所有可执行文件
     - 签名失败阻止发布
  4. **关键说明**：
     - 未签名的 Windows 应用会触发 SmartScreen 警告
     - EV 证书签名可立即消除 SmartScreen 拦截
     - OV 证书需要积累下载量建立信誉
- **验收**: 签名后的 EXE 不触发 SmartScreen 警告；`signtool verify` 通过

### 步骤11: 首次启动向导
- **文件**: `desktop/src/setup-wizard/SetupWizard.tsx`
- **操作**: 新建
- **内容**: 实现 5 步向导组件：
  1. **Welcome 步骤**：
     - 展示 DeerFlow Logo 和欢迎文案
     - "开始配置" 按钮
     - 检测是否首次启动（`localStorage.getItem('deerflow-setup-complete')`）
  2. **Sandbox 步骤**：
     - 自动检测当前平台虚拟化能力（调用 `window.deerflow.detectSandbox()`）
     - 展示检测结果：macOS Virtualization.framework / Windows WSL2 / Linux KVM
     - 选择沙箱策略：STRICT / SELECTIVE（推荐）/ LOCAL
     - 无虚拟化时自动选择 LOCAL 并显示提示
     - 检测耗时可能较长，显示加载动画
  3. **API Key 步骤**：
     - 输入 LLM API 密钥（支持多个 Provider）
     - 默认展示 OpenAI / Anthropic / 自定义三种
     - 可选 "跳过，稍后配置"
     - 密钥写入 `config.yaml` 的 `models[*].api_key` 字段
  4. **Skills 步骤**：
     - 展示预装技能列表（勾选框）
     - 推荐技能：web-search、code-review、file-manager
     - 安装进度展示
  5. **Ready 步骤**：
     - 配置摘要（沙箱模式、API Key 状态、已选技能）
     - "启动 DeerFlow" 按钮
     - 点击后：写入配置 → 标记首次启动完成 → 跳转主界面
  6. **向导状态持久化**：
     - 中途退出保存当前步骤到 `localStorage`
     - 下次启动恢复到中断步骤
- **验收**: 首次启动时自动显示向导，5 步流程走完后进入主界面；关闭重启后不再显示向导

### 步骤12: 向导子组件
- **文件**: `desktop/src/setup-wizard/` 目录下多个文件
- **操作**: 新建
- **内容**:
  1. `StepWelcome.tsx` — 欢迎页，含 Logo、版本号、系统需求说明
  2. `StepSandbox.tsx` — 沙箱配置页，含检测动画、策略选择、说明文案
  3. `StepApiKey.tsx` — API 密钥配置页，含 Provider 选择、密钥输入、验证按钮
  4. `StepSkills.tsx` — 技能预选页，含技能卡片列表、安装进度
  5. `StepReady.tsx` — 就绪页，含配置摘要、启动按钮
  6. `WizardLayout.tsx` — 通用布局：步骤指示器、前进/后退按钮
- **验收**: 每个步骤组件可独立渲染，交互逻辑正确

### 步骤13: electron-builder 打包配置
- **文件**: `desktop/electron-builder.yml`
- **操作**: 新建
- **内容**:
  ```yaml
  appId: com.deerflow.desktop
  productName: DeerFlow
  copyright: Copyright © 2026 DeerFlow

  directories:
    output: dist
    buildResources: resources

  files:
    - dist/**/*
    - electron/**/*
    - src/**/*
    - "!**/node_modules/**/*"

  extraResources:
    - from: resources/python-backend
      to: python-backend
      filter:
        - "**/*"
    - from: resources/vm-images
      to: vm-images
      filter:
        - "**/*"

  mac:
    category: public.app-category.developer-tools
    target:
      - target: dmg
        arch:
          - universal
    icon: assets/icon.icns
    hardenedRuntime: true
    gatekeeperAssess: false
    entitlements: assets/entitlements.mac.plist
    entitlementsInherit: assets/entitlements.mac.inherit.plist
    identity: "Developer ID Application: DeerFlow Team (XXXXXXXXXX)"

  win:
    target:
      - target: nsis
        arch:
          - x64
    icon: assets/icon.ico
    certificateFile: "${WIN_CERT_FILE}"
    certificatePassword: "${WIN_CERT_PASSWORD}"
    signAndEditExecutable: true
    signingHashAlgorithms:
      - sha256
    rfc3161TimeStampServer: "http://timestamp.digicert.com"
    timeStampServer: "http://timestamp.digicert.com"

  nsis:
    oneClick: false
    allowToChangeInstallationDirectory: true
    installerIcon: assets/icon.ico
    uninstallerIcon: assets/icon.ico

  linux:
    target:
      - target: AppImage
        arch:
          - x64
    icon: assets/icon.png
    category: Development

  publish:
    provider: github
    owner: deerflow
    repo: deerflow
  ```
- **验收**: `pnpm pack` 可生成对应平台安装包（开发机上测试）

### 步骤14: TypeScript 配置
- **文件**: `desktop/tsconfig.json`
- **操作**: 新建
- **内容**: TypeScript 编译配置：
  - `target`: ES2022
  - `module`: ESNext
  - `moduleResolution`: bundler
  - `jsx`: react-jsx
  - `paths`: `@/* → src/*`、`@electron/* → electron/*`
  - `strict`: true
  - 包含 `electron/`、`src/` 目录
  - 排除 `node_modules/`、`dist/`
- **验收**: `tsc --noEmit` 无类型错误

### 步骤15: Vite 构建配置
- **文件**: `desktop/vite.config.ts`
- **操作**: 新建
- **内容**: Vite + Electron 插件配置：
  - `vite-plugin-electron` 配置主进程和预加载脚本入口
  - 主进程入口: `electron/main.ts`
  - 预加载入口: `electron/preload.ts`
  - 渲染进程入口: `index.html` → `src/main.tsx`
  - 开发代理：`/api/*` → `http://127.0.0.1:8001`
  - 构建输出: `dist/`
- **验收**: `pnpm dev` 同时启动 Vite 和 Electron，热重载正常

## 验收标准
- [ ] `desktop/` 项目结构完整，`pnpm install` 无错误
- [ ] Electron 主进程可启动，创建主窗口
- [ ] Python 后端子进程可被管理（启动、健康检查、关闭）
- [ ] 首次启动向导 5 步流程完整可走通
- [ ] 向导完成后配置写入 `config.yaml`
- [ ] `pnpm pack` 可生成平台安装包
- [ ] 单实例锁生效，不会启动多个窗口
- [ ] 窗口关闭到托盘，不退出应用
- [ ] **PyInstaller 隐式导入扫描通过，打包后无 `ModuleNotFoundError`**
- [ ] **打包后冒烟测试全部通过（健康检查、核心 API、LangChain 调用链）**
- [ ] **macOS 代码签名通过 `codesign --verify`**
- [ ] **Windows 代码签名通过 `signtool verify`**
- [ ] **Nuitka 备选方案构建脚本可用，冒烟测试通过**

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | PythonBackendManager.start() 启动子进程 | 子进程启动，健康检查通过，状态变为 ready |
| 单元测试 | PythonBackendManager.stop() 优雅关闭 | SIGTERM 发送后进程退出，无僵尸进程 |
| 单元测试 | PythonBackendManager 端口冲突检测 | 8001 占用时自动选择 8002 |
| 单元测试 | SetupWizard 步骤切换 | 可前进/后退，数据保留 |
| 集成测试 | 完整首次启动流程 | 向导 → 配置写入 → 主界面加载 → 后端就绪 |
| 集成测试 | 非首次启动 | 跳过向导，直接进入主界面 |
| 冒烟测试 | PyInstaller 打包后健康检查 | `/api/health` 返回 200 |
| 冒烟测试 | PyInstaller 打包后 LangChain 调用 | 无 `ModuleNotFoundError`，完整调用链成功 |
| 冒烟测试 | PyInstaller 打包后技能加载 | `/api/skills` 返回技能列表 |
| 冒烟测试 | Nuitka 打包后核心 API | 所有核心 API 正常响应 |
| E2E 测试 | 窗口关闭到托盘 | 关闭窗口后托盘图标存在，点击恢复窗口 |
| E2E 测试 | 单实例锁 | 第二次启动时聚焦已有窗口 |
| 签名测试 | macOS codesign 验证 | `codesign --verify --deep --strict` 通过 |
| 签名测试 | Windows signtool 验证 | `signtool verify /pa` 通过 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| PyInstaller 打包体积过大（>150MB） | 高 | 使用 `--exclude-module` 排除不必要的库；使用 UPX 压缩；考虑目录模式代替单文件模式；评估 Nuitka |
| PyInstaller 隐式导入遗漏 | 高 | **步骤5 自动扫描隐式导入**；维护 hidden-imports 列表；CI 中自动对比扫描结果；**打包后冒烟测试验证** |
| PyInstaller 打包后运行时崩溃 | 中 | **步骤7 冒烟测试覆盖核心 API**；多平台 CI 测试；Nuitka 作为备选方案 |
| macOS 代码签名缺失导致无法运行 | 高 | **步骤9 为必须步骤**；提前准备 Apple Developer 账号；CI 中集成签名流程；**未签名应用不可发布** |
| Windows SmartScreen 拦截 | 高 | **步骤10 为必须步骤**；使用 EV 证书签名；CI 中集成签名流程 |
| 首次启动 Python 后端启动慢（>10s） | 高 | 显示启动进度动画；使用 PyInstaller 目录模式加速启动；评估 Nuitka（启动更快） |
| Electron 与 Vite HMR 配置复杂 | 中 | 使用 `vite-plugin-electron` 简化配置；参考 Electron 官方模板 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.3 整体打包架构、7.4 项目结构、7.8 首次启动向导）
- EVOFLOW_IMPLEMENTATION_PLAN.md 第11节（第4期路线图）
- DeerFlow 现有 `backend/app/gateway/main.py` Gateway 启动逻辑
- Electron 官方文档: https://www.electronjs.org/docs
- PyInstaller 隐式导入: https://pyinstaller.org/en/stable/when-things-go-wrong.html
- Nuitka 用户手册: https://nuitka.net/user-documentation/
- Apple 代码签名: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- Windows 代码签名: https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools
