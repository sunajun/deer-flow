# 🦌 DeerFlow 2.0 项目架构与功能详细分析

> 文档版本：2026-05-22
> 分析对象：`bytedance/deer-flow` (main 分支)
> 项目定位：开源 **Super Agent Harness**，编排 sub-agents、memory、sandboxes，由可扩展 skills 驱动

---

## 目录

- [一、项目概览](#一项目概览)
- [二、顶层目录结构](#二顶层目录结构)
- [三、后端架构深度分析](#三后端架构深度分析)
- [四、前端架构深度分析](#四前端架构深度分析)
- [五、核心功能模块](#五核心功能模块)
- [六、配置与扩展机制](#六配置与扩展机制)
- [七、技术栈全景](#七技术栈全景)
- [八、部署方案](#八部署方案)
- [九、关键设计亮点](#九关键设计亮点)

---

## 一、项目概览

**DeerFlow** = **D**eep **E**xploration and **E**fficient **R**esearch **Flow**

由字节跳动 (ByteDance) 开源，2026 年 2 月 28 日发布 2.0 版本后登顶 GitHub Trending 第一。**2.0 是从零重写的版本**，与 1.x 无任何代码共享：

| 维度 | DeerFlow 1.x | DeerFlow 2.0 |
|------|--------------|--------------|
| 定位 | Deep Research 框架 | **Super Agent Harness** |
| 抽象 | 固定研究流程 | 通用 agent 编排平台 |
| 能力 | 网络研究 + 报告 | sub-agents + sandbox + memory + skills + MCP |
| 维护 | `main-1.x` 分支 (仍接受贡献) | `main` 分支 (主线开发) |

**核心理念**：把 LLM 当作"操作系统内核"，DeerFlow 提供 harness（外壳），编排 sub-agents、长期记忆、沙箱执行、可插拔技能、IM 渠道，做"几乎一切"。

---

## 二、顶层目录结构

```
deer-flow/
├── backend/                    Python 后端（双层架构：harness + app）
├── frontend/                   Next.js 16 + React 19 前端
├── docker/                     Docker / Kubernetes 部署编排
├── skills/                     20+ 官方内置技能
├── scripts/                    维护脚本（配置、诊断、部署）
├── docs/                       项目文档
├── .github/                    CI/CD 工作流
├── .agent/ .claude/            Agent 辅助配置
├── pr-build/                   PR 构建产物
├── README*.md                  多语言主文档（en/zh/ja/fr/ru）
├── Install.md                  面向 coding agent 的一句话安装指南
├── Makefile                    统一入口（30+ make 命令）
├── config.example.yaml         主配置模板（43.4KB，包含所有可调项）
├── .env.example                环境变量模板（2.6KB，API Keys）
├── extensions_config.example.json   MCP 服务器与自定义技能配置
├── deer-flow.code-workspace    VS Code 工作区配置
└── CODE_OF_CONDUCT.md / CONTRIBUTING.md / LICENSE / SECURITY.md
```

### 2.1 关键文件解读

| 文件 | 作用 |
|------|------|
| `Makefile` | 统一开发入口：`make dev` 启动本地开发，`make up` 启动生产，`make docker-start` 启动 Docker 开发，`make gateway` 单独启后端 |
| `config.example.yaml` | 主配置（43.4KB），含 LLM/工具/沙箱/子代理/记忆/技能/数据库/IM/护栏全部配置 |
| `.env.example` | 第三方服务密钥（搜索、IM、追踪） |
| `extensions_config.example.json` | MCP 服务器、技能开关与上传 |

### 2.2 内置技能 (`skills/public/`)

20+ 官方技能，覆盖以下场景：

- **研究类**：`deep-research`、`academic-paper-review`、`systematic-literature-review`
- **生成类**：`report-generation`、`ppt-generation`、`newsletter-generation`、`podcast-generation`
- **开发类**：`code-documentation`、`frontend-design`、`vercel-deploy-claimable`
- **数据类**：`data-analysis`、`chart-visualization`（20+ 图表类型）
- **工具类**：`claude-to-deerflow`、`skill-creator`、`find-skills`

### 2.3 部署目录 (`docker/`)

| 文件 | 用途 |
|------|------|
| `docker-compose.yaml` | 生产环境编排 |
| `docker-compose-dev.yaml` | 开发环境（支持源码热重载） |
| `nginx/nginx.conf` | 反向代理（前端 / API / LangGraph 统一到 `2026` 端口） |
| `provisioner/` | Kubernetes 沙箱编排服务（生产级别） |

### 2.4 CI/CD (`.github/workflows/`)

- `backend-unit-tests.yml` — Python 单元测试
- `frontend-unit-tests.yml` — TypeScript 单元测试
- `e2e-tests.yml` — 端到端测试
- `lint-check.yml` — 代码风格与质量
- `container.yaml` — Docker 镜像构建发布

---

## 三、后端架构深度分析

后端采用**严格分层架构**：**Harness 框架层（可发布为独立包）** + **App 应用层**。依赖方向单向：**App → Harness**，反向严禁，由 `backend/tests/test_harness_boundary.py` 自动校验。

### 3.1 核心依赖（`backend/pyproject.toml`）

| 类别 | 依赖 |
|------|------|
| Python | `>= 3.12` |
| Web 框架 | `FastAPI >= 0.115.0` + Uvicorn |
| Agent 编排 | `LangGraph SDK >= 0.1.51` + LangChain 全家桶 |
| 沙箱 | Docker / Apple Container |
| IM SDK | 飞书 / Slack / Telegram / 企业微信 / 钉钉 |
| 可选 | `postgres`（PostgreSQL）、`discord`（Discord 渠道） |
| 包管理 | `uv` |

### 3.2 Harness 框架层 (`backend/packages/harness/deerflow/`)

作为独立 PyPI 包 **`deerflow-harness`** 发布，是 DeerFlow 的核心引擎。

| 模块 | 路径 | 职责 |
|------|------|------|
| **Agent 系统** | `agents/` | 主代理编排、中间件、记忆、线程状态 |
| 主代理 | `agents/lead_agent/agent.py` | LangGraph 图定义、工具组装、system prompt 构造 |
| **中间件** | `agents/middlewares/` | **18 个中间件**，覆盖错误处理、循环检测、记忆注入、上下文压缩等全生命周期 |
| **记忆** | `agents/memory/` | 长期记忆提取、存储、注入，per-user 隔离 |
| **沙箱** | `sandbox/` | 抽象接口 + 本地实现 + 文件/命令工具 |
| **子代理** | `subagents/` | 子代理调度、并行执行、结果汇总 |
| **工具** | `tools/` | 内置工具（文件展示、澄清询问、图片查看）+ MCP 接入 |
| **MCP 集成** | `mcp/` | 多服务器管理、OAuth、懒加载 |
| **模型层** | `models/` | 多 LLM 厂商适配、思考模式、视觉能力 |
| **技能** | `skills/` | 技能发现、加载、解析、按需注入 |
| **配置** | `config/` | 配置解析、热重载、环境变量替换 |
| **社区扩展** | `community/` | Tavily、Jina、Firecrawl、AIO Sandbox |
| **嵌入式客户端** | `client.py` | 无需启 HTTP 服务即可直接调用全部能力（Python 内嵌） |

### 3.3 App 应用层 (`backend/app/`)

对外暴露服务的应用层。

| 模块 | 路径 | 职责 |
|------|------|------|
| **Gateway API** | `gateway/` | FastAPI 服务入口 |
| **API 路由** | `gateway/routers/` | **14 个路由模块**：模型、技能、内存、上传、线程、运行、用户等 |
| **认证** | `gateway/auth/` | JWT、用户管理、权限控制 |
| **IM 渠道** | `channels/` | 7 个渠道：飞书、Slack、Telegram、企业微信、钉钉、Discord、微信 |
| **渠道管理** | `channels/manager.py` | 消息路由、线程映射、命令解析 |

### 3.4 启动流程

```
make dev (或 make gateway)
    ↓
backend/app/gateway/app.py  (FastAPI 初始化)
    ↓
Gateway 进程内嵌 Agent 运行时
    ↓
对外暴露 /api/langgraph/*  (LangGraph 兼容协议)
默认 8001 端口，Nginx 统一代理到 2026 端口
```

### 3.5 测试组织 (`backend/tests/`)

- 全模块单元测试（gateway 兼容、内存更新、沙箱模式检测等）
- **边界检测**：`test_harness_boundary.py` 强制校验 Harness 层不引用 App 层
- 集成测试：Docker 沙箱、Provisioner 配置场景

---

## 四、前端架构深度分析

### 4.1 技术栈（`frontend/package.json`）

| 类别 | 选型 |
|------|------|
| 框架 | Next.js **16** + React **19** + TypeScript **5.8** |
| UI | Radix UI + Shadcn UI + **Tailwind CSS 4** |
| 状态 | TanStack React Query |
| AI | Vercel AI SDK + LangGraph SDK |
| 可视化 | `@xyflow/react`（流程图）、`shiki`（代码高亮）、`katex`（数学公式） |
| 构建 | **Turbopack** + pnpm 10.26.2 |
| 测试 | Vitest + Playwright |

### 4.2 目录与路由（`frontend/src/`）

采用 **Next.js App Router**：

```
src/app/
├── page.tsx                                    着陆页
├── workspace/
│   ├── chats/[thread_id]/page.tsx              聊天工作区（核心交互）
│   └── agents/                                 自定义 Agent 管理
├── [lang]/docs/[[...mdxPath]]/page.tsx         多语言文档
└── (auth)/
    ├── login/                                  登录
    └── setup/                                  初始化向导
```

### 4.3 组件组织

| 目录 | 内容 |
|------|------|
| `components/ui/` | Shadcn UI 基础组件（自动生成） |
| `components/ai-elements/` | AI 相关组件：消息、思考过程、任务、Artifact |
| `components/workspace/` | 工作区页面组件 |
| `components/landing/` | 着陆页组件 |
| `core/` | 业务逻辑：线程管理、API 客户端、Artifact、i18n、settings |
| `hooks/` | 共享 React Hooks |
| `lib/` | 通用工具函数 |

### 4.4 通信与体验

- **API 协议**：通过 LangGraph SDK 对接后端，**SSE 流式响应**
- **状态层**：TanStack Query 管服务端态，localStorage 存用户偏好
- **国际化**：内置 i18n，支持中英文
- **主题**：`next-themes` 明暗切换
- **响应式**：Tailwind 4 全端适配

### 4.5 关键页面能力

- **聊天**：流式消息、代码高亮、数学公式、Artifact 预览、任务状态
- **流程可视化**：`@xyflow/react` 图形化展示子代理执行
- **技能管理**：浏览、启停、安装
- **模型选择**：动态切换 LLM，开关思考模式
- **Artifact**：展示与下载 agent 产物（报告/代码/PPT 等）

---

## 五、核心功能模块

### 5.1 Skills & Tools 系统

| 维度 | 实现 |
|------|------|
| 加载 | `backend/packages/harness/deerflow/skills/loader.py` 递归扫描 `skills/`，解析 `SKILL.md` 的 YAML frontmatter |
| 注册 | 状态保存在 `extensions_config.json`，Gateway API `/api/skills/` 管理 |
| **按需注入** | 仅当任务需要时才加载技能内容到上下文，**节省 token** |
| 工具组装 | `get_available_tools()` 动态组装：**配置工具 + MCP 工具 + 内置工具 + 子代理工具** 四类 |

### 5.2 Claude Code 集成

- 实现：`skills/public/claude-to-deerflow/SKILL.md` 提供 CLI 桥接技能
- 能力：发消息、选模式、健康检查、线程管理、文件上传
- 协议：直接走 DeerFlow 公开 REST API

### 5.3 Sub-Agents 子代理系统

| 维度 | 实现 |
|------|------|
| 内置类型 | `general-purpose`、`bash`，**支持自定义** |
| 调度 | `subagents/executor.py` **双线程池**，**最多 3 个并行子代理** |
| 流程 | `task()` 工具调用 → 后台线程 → **每 5 秒轮询** → SSE 推送结果 |
| 超时 | 默认 **15 分钟**，按类型可单独配置 |
| 隔离 | 每个子代理独立上下文、独立工具集、独立执行环境 |

### 5.4 Sandbox 沙箱

**三层抽象**：`Sandbox` 接口 → `SandboxProvider` → 具体实现。

| 模式 | 实现 | 适用场景 |
|------|------|---------|
| **本地** | `LocalSandboxProvider` (`sandbox/local/`) | 开发环境，直接在宿主执行 |
| **Docker** | `AioSandboxProvider` (`community/aio_sandbox/`) | 默认推荐，完整开发环境镜像 |
| **Kubernetes** | 通过 `docker/provisioner/` 调度 Pod | 生产级别，大规模隔离 |

**统一虚拟路径**：

```
/mnt/user-data/{workspace, uploads, outputs}
        ↓ 映射到 ↓
backend/.deer-flow/users/{user_id}/threads/{thread_id}/user-data/
```

**内置文件/命令工具**：`bash`、`ls`、`read_file`、`write_file`、`str_replace`、`glob`、`grep`

### 5.5 Context Engineering

- **子代理上下文隔离**：互不干扰
- **摘要压缩**：`SummarizationMiddleware` 在接近 token 限制时自动压缩历史，**保留最近 10 条**
- **技能保留**：最近加载的 **5 个技能文件** 不被压缩，避免丢失指令
- **动态注入**：`DynamicContextMiddleware` 按运行时状态注入

### 5.6 Long-Term Memory

| 维度 | 实现 |
|------|------|
| 存储 | 默认本地 JSON `backend/.deer-flow/users/{user_id}/memory.json` |
| 隔离 | per-user |
| 提取 | `agents/memory/updater.py` 用 LLM 从对话中自动抽取事实和偏好 |
| 去重 | 基于内容哈希 |
| 注入 | `MemoryMiddleware` 对话前注入到 system prompt，**最多 2000 tokens** |

### 5.7 MCP Server 集成

- **多服务器**：stdio / HTTP / SSE 三种传输
- **OAuth**：HTTP/SSE 支持 `client_credentials` 和 `refresh_token`，自动续期
- **懒加载**：MCP 工具不预加载，通过 `tool_search` **运行时发现** ，省 token
- **热更新**：`extensions_config.json` 变更自动重载，无需重启

### 5.8 IM 渠道集成

| 维度 | 设计 |
|------|------|
| 支持 | 飞书、Slack、Telegram、企业微信、钉钉、Discord、微信 |
| 连接 | **outbound only**（WebSocket / 长轮询），**无需公网 IP** |
| 架构 | `MessageBus` 异步队列 + `ChannelManager` 路由 |
| 命令 | 统一 `/new`、`/status`、`/models`、`/memory`、`/help` |
| 映射 | `store.py` 持久化外部 chat_id ↔ DeerFlow thread_id |

---

## 六、配置与扩展机制

### 6.1 `config.example.yaml` 结构（20+ 模块）

| 模块 | 说明 |
|------|------|
| `models[]` | 多厂商 LLM，含 API key、参数、思考/视觉能力开关 |
| `tools[]` | 工具实现，支持多搜索后端切换 |
| `sandbox` | 沙箱选型、执行模式、挂载目录 |
| `subagents` | 超时、最大轮次、自定义子代理 |
| `skills` | 技能目录、容器挂载路径 |
| `memory` | 开关、存储路径、提取参数 |
| `database` | SQLite（默认）/ PostgreSQL |
| `channels` | 各 IM 渠道凭据 |
| `guardrails` | 工具调用前置授权（白名单 / OAP 策略） |

### 6.2 三类扩展

**① 添加新 Skill**

1. 在 `skills/custom/` 新建目录，写 `SKILL.md`（YAML frontmatter + 内容）
2. 或通过 `POST /api/skills/install` 上传 `.skill` 压缩包
3. 在 `extensions_config.json` 启用

**② 添加新 LLM Provider**

1. `config.yaml` → `models[]` 新增条目，`use` 指向 LangChain 类路径（如 `langchain_openai:ChatOpenAI`）
2. 填 API 密钥/端点/参数
3. 特殊适配（思考、视觉）继承 `deerflow.models.base` 实现自定义

**③ 添加新 Tool / MCP Server**

- **Python 工具**：实现函数 → `config.yaml` 的 `tools[]` 配置 `use: 模块:函数`
- **MCP 工具**：`extensions_config.json` 的 `mcpServers` 新增（stdio/HTTP/SSE）

---

## 七、技术栈全景

### 7.1 后端

| 层次 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| Web | FastAPI 0.115+ + Uvicorn |
| Agent | LangGraph + LangChain |
| 包管理 | uv |
| 沙箱 | Docker / Apple Container / Kubernetes |
| 数据库 | SQLite（默认）/ PostgreSQL |
| 可观测 | LangSmith / Langfuse |
| 部署 | Docker Compose / Kubernetes |

### 7.2 前端

| 层次 | 技术 |
|------|------|
| 语言 | TypeScript 5.8+ |
| 框架 | Next.js 16 + React 19 |
| UI | Radix UI + Shadcn UI + Tailwind 4 |
| 状态 | TanStack React Query |
| AI | Vercel AI SDK + LangGraph SDK |
| 构建 | Turbopack + pnpm |
| 测试 | Vitest + Playwright |

---

## 八、部署方案

### 8.1 推荐硬件配置

| 场景 | 配置 | 启动命令 |
|------|------|---------|
| 本地体验 | 4 vCPU + 8GB | `make dev` |
| 开发环境 | 8 vCPU + 16GB | `make docker-start` |
| 生产环境 | 16 vCPU + 32GB | `make up` |

### 8.2 端口与路由

- 后端 Gateway：默认 `8001`
- 前端：默认 `3000`
- Nginx 统一代理：`2026`（生产）

### 8.3 Docker 编排

- **开发**：`docker/docker-compose-dev.yaml`（源码挂载，热重载）
- **生产**：`docker/docker-compose.yaml`（构建镜像，优化性能）
- **K8s 沙箱**：`docker/provisioner/` 提供 Pod 调度服务

---

## 九、关键设计亮点

### 9.1 双层分包架构

```
┌─────────────────────────────────┐
│ App 层 (backend/app/)           │  对外服务：Gateway API + IM 渠道
│  ↓ 单向依赖                      │
├─────────────────────────────────┤
│ Harness 层                       │  核心引擎，可独立发布
│ (backend/packages/harness/      │  PyPI: deerflow-harness
│  deerflow/)                     │  支持 Python 直接嵌入使用
└─────────────────────────────────┘
```

- App 层从不被 Harness 层引用，由测试强制校验
- Harness 可作为库嵌入任何 Python 项目，无需启 HTTP 服务

### 9.2 18 个中间件流水线

Agent 执行过程被切分为 18 个中间件，覆盖错误处理、循环检测、记忆注入、上下文压缩、动态注入等全生命周期。**新增能力 = 加一个中间件**，与核心解耦。

### 9.3 子代理 + 沙箱 + 技能 = "Super Agent"

- **子代理** 提供并行计算单元
- **沙箱** 提供安全执行环境
- **技能** 提供按需注入的领域知识
- **MCP/IM** 提供外部连接器
- **记忆** 提供跨会话上下文

五大原语组合，可覆盖几乎任何 agent 场景。

### 9.4 Token 优化策略

| 策略 | 效果 |
|------|------|
| 技能按需注入 | 不用的技能不消耗 token |
| MCP 工具懒加载 | 通过 `tool_search` 运行时发现 |
| 自动摘要压缩 | 保留近 10 条 + 近 5 个技能文件 |
| 记忆 token 上限 | 注入控制在 2000 tokens 内 |

### 9.5 全渠道 outbound 设计

7 个 IM 渠道全部使用 outbound 连接，**无需公网 IP / 反向代理**，企业内网可直接部署。

---

## 附录：关键文件速查表

| 功能 | 文件 |
|------|------|
| 主代理图定义 | `backend/packages/harness/deerflow/agents/lead_agent/agent.py` |
| 中间件目录 | `backend/packages/harness/deerflow/agents/middlewares/` |
| 子代理调度 | `backend/packages/harness/deerflow/subagents/executor.py` |
| 沙箱接口 | `backend/packages/harness/deerflow/sandbox/` |
| 技能加载 | `backend/packages/harness/deerflow/skills/loader.py` |
| MCP 管理 | `backend/packages/harness/deerflow/mcp/` |
| 嵌入式客户端 | `backend/packages/harness/deerflow/client.py` |
| Gateway 入口 | `backend/app/gateway/app.py` |
| API 路由 | `backend/app/gateway/routers/` |
| IM 消息总线 | `backend/app/channels/message_bus.py` |
| 边界测试 | `backend/tests/test_harness_boundary.py` |
| 前端聊天页 | `frontend/src/app/workspace/chats/[thread_id]/page.tsx` |
| Nginx 配置 | `docker/nginx/nginx.conf` |
| 主配置模板 | `config.example.yaml` |
| 扩展配置 | `extensions_config.example.json` |

---

**文档生成时间**：2026-05-22
**分析依据**：项目 main 分支最新代码 (commit `253542ea`)
**适用版本**：DeerFlow 2.0
