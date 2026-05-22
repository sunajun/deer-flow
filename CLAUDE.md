# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

DeerFlow 2.0 是 ByteDance 开源的 **Super Agent Harness**（v1 与 v2 无共享代码），编排 sub-agents、memory、sandboxes，由可扩展 skills 驱动。这是一个 monorepo，含以下顶层目录：

- `backend/` — Python 3.12+ 后端，**双层分包架构**：`packages/harness/deerflow/` 是可发布的 agent 引擎（PyPI 包 `deerflow-harness`，import `deerflow.*`），`app/` 是 FastAPI Gateway + IM 渠道（import `app.*`）。**单向依赖**：app → harness，反向由 `backend/tests/test_harness_boundary.py` 在 CI 强制校验。详见 [`backend/CLAUDE.md`](./backend/CLAUDE.md)。
- `frontend/` — Next.js 16 + React 19 + TypeScript 5.8 + Tailwind 4，使用 pnpm 10.26.2 和 Turbopack。详见 [`frontend/CLAUDE.md`](./frontend/CLAUDE.md)。
- `skills/{public,custom}/` — 内置和自定义技能（`SKILL.md` 含 YAML frontmatter）。`custom/` 默认 gitignore。
- `docker/` — `docker-compose-dev.yaml`、`docker-compose.yaml`、`nginx/`（统一代理）、`provisioner/`（K8s 沙箱编排）。
- `scripts/` — `serve.sh`、`docker.sh`、`deploy.sh`、`check.py`、`doctor.py`、`setup_wizard.py` 等。
- `config.yaml` / `extensions_config.json` — 主配置位于**项目根目录**（不是 backend/），由 `config.example.yaml` / `extensions_config.example.json` 拷贝生成。

## Common Commands (Root)

所有命令通过根 `Makefile` 暴露。**先 `make check` 校验依赖，再 `make install` 安装**。

| 命令 | 用途 |
|------|------|
| `make setup` | 交互式新手配置向导 |
| `make doctor` | 检查配置与系统依赖 |
| `make config` / `make config-upgrade` | 生成 / 升级 `config.yaml`（合并 example 新字段） |
| `make install` | 安装前后端依赖 + pre-commit hooks |
| `make dev` | 本地开发模式（Gateway + Frontend + Nginx，热重载，`localhost:2026`） |
| `make dev-daemon` | dev 后台模式 |
| `make start` / `make start-daemon` | 生产模式（无热重载） |
| `make stop` | 停所有服务 |
| `make clean` | 停服务 + 清理 `.deer-flow/`、`.langgraph_api/`、`logs/*.log` |
| `make up` / `make down` | 生产 Docker 启停（构建镜像） |
| `make docker-init` | 拉取 sandbox 镜像（首次） |
| `make docker-start` / `make docker-stop` / `make docker-logs` | Docker 开发环境（mode-aware，按 `config.yaml` 决定是否启 provisioner） |
| `make setup-sandbox` | 预拉 sandbox 容器镜像 |
| `make detect-thread-boundaries` | 盘点 async/线程边界点 |

**单独跑子项目**：`cd backend && make {dev,gateway,test,lint,format}`；`cd frontend && pnpm {dev,build,check,test,test:e2e}`。

## Architecture Highlights (Root-Level)

完整的后端中间件、API 路由、沙箱、子代理、记忆、MCP、IM 渠道细节都在 [`backend/CLAUDE.md`](./backend/CLAUDE.md)。这里只列**跨子项目**的关键事实：

### 进程拓扑与端口路由

```
Browser → Nginx :2026  ┬→ Frontend :3000          (非 /api/* 请求)
                       ├→ Gateway :8001 /api/*    (REST API)
                       └→ Gateway :8001 /api/*    (← /api/langgraph/* 重写后)
                                                  (LangGraph-compatible runtime)
Provisioner :8002 (可选，仅 sandbox=provisioner/k8s 时启动)
```

- Gateway 进程内嵌 LangGraph runtime（`RunManager` + `run_agent()` + `StreamBridge`，源于 `packages/harness/deerflow/runtime/`），**不再有独立 LangGraph 进程**。
- Nginx 重写 `/api/langgraph/*` → Gateway `/api/*`，统一同源，CORS/CSRF 默认关闭；分离源部署要设 `GATEWAY_CORS_ORIGINS`。

### 配置文件位置与解析顺序

`config.yaml` 与 `extensions_config.json` 解析优先级：
1. 显式 `config_path` 参数
2. `DEER_FLOW_CONFIG_PATH` / `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 环境变量
3. 当前目录（`backend/`）
4. **父目录（项目根，推荐）**

值以 `$` 开头解析为环境变量。`config.example.yaml` 含 `config_version` 字段，启动时若用户版本落后会警告，跑 `make config-upgrade` 自动合并。

**热重载边界**：`get_app_config()` 按 mtime 自动 reload，所以 `models[*]`、`summarization`、`memory`、`subagents`、`tools[*]`、system prompt 等改完下一条消息即生效。但 `database.*`、`checkpointer.*`、`run_events.*`、`stream_bridge.*`、`sandbox.use`、`log_level`、`channels.*` 需要**重启进程**。详见 backend/CLAUDE.md "Config Hot-Reload Boundary"。

### 沙箱虚拟路径

Agent 看到的虚拟路径 → 物理路径映射：
```
/mnt/user-data/{workspace,uploads,outputs}  →  backend/.deer-flow/users/{user_id}/threads/{thread_id}/user-data/...
/mnt/acp-workspace                            →  backend/.deer-flow/users/{user_id}/threads/{thread_id}/acp-workspace/
/mnt/skills                                   →  deer-flow/skills/
```

本地沙箱用 `PathMapping` 翻译，Docker/AIO 沙箱用 volume mount。`user_id` 无认证模式下默认 `"default"`。

## Development Conventions

### 后端（Python）
- **TDD 强制**：每个新特性 / bug 修复必须配 `backend/tests/test_<feature>.py`，跑 `cd backend && make test`。
- **Harness 边界**：`packages/harness/deerflow/` 严禁 `import app.*`，CI 校验。
- **Lint/Format**：`ruff`，line length **240**，Python 3.12+ 类型注解，双引号，空格缩进。
- **包管理**：`uv`（不是 pip），新增依赖 `cd backend && uv add <pkg>`。
- **文档同步**：改后端代码必须同步更新 `backend/CLAUDE.md`、`README.md`（项目内部硬性要求）。

### 前端（TypeScript）
- 提交前必跑 `pnpm check`（lint + typecheck）。
- 测试：单元测试 `tests/unit/` 镜像 `src/` 布局（Vitest），E2E `tests/e2e/`（Playwright + Chromium，mock 后端）。
- **不要手改** `src/components/ui/`（Shadcn）和 `src/components/ai-elements/`（Vercel AI SDK），它们由 registry 生成。
- Import 顺序由 ESLint 强制；未用变量加 `_` 前缀；条件 className 用 `cn()`；路径别名 `@/* → src/*`。

### 提交流程
1. 改前 `git checkout -b feature/xxx`。
2. 改后端跑 `cd backend && make format && make test`；改前端跑 `cd frontend && pnpm format:write && pnpm check && pnpm test`。
3. CI 跑 `backend-unit-tests.yml`、`frontend-unit-tests.yml`、`e2e-tests.yml`（仅 frontend/ 变更触发）、`lint-check.yml`。
4. **不要跳过 pre-commit hooks**（`make install` 已装），任何 `--no-verify` 必须先问用户。

## Extension Points

新增三类扩展（详细配置示例见 `config.example.yaml` 与 `extensions_config.example.json`）：

1. **Skill**：在 `skills/custom/` 新建目录写 `SKILL.md`，或 `POST /api/skills/install` 上传 `.skill` ZIP，再在 `extensions_config.json` 的 `skills` 启用。
2. **LLM Provider**：`config.yaml` 的 `models[]` 加条目，`use` 字段填 LangChain 类路径（如 `langchain_openai:ChatOpenAI`），必要时实现 `deerflow.models.base` 子类（思考 / 视觉适配）。
3. **Tool / MCP Server**：Python 工具在 `config.yaml` 的 `tools[]` 配 `use: 模块:函数`；MCP 工具在 `extensions_config.json` 的 `mcpServers` 加（stdio/HTTP/SSE），HTTP/SSE 支持 OAuth `client_credentials` / `refresh_token` 自动续期。

## Reference Docs

- 后端深入：[`backend/CLAUDE.md`](./backend/CLAUDE.md)（约 600 行，覆盖 18 个中间件、所有 API 路由、沙箱/子代理/记忆/MCP/IM/Embedded Client 全部细节）
- 前端深入：[`frontend/CLAUDE.md`](./frontend/CLAUDE.md)
- 协作流程：[`CONTRIBUTING.md`](./CONTRIBUTING.md)
- 项目总览（已有的中文分析）：[`PROJECT_ANALYSIS.md`](./PROJECT_ANALYSIS.md)
- 后端模块文档：[`backend/docs/`](./backend/docs/)（CONFIGURATION、ARCHITECTURE、API、SETUP、FILE_UPLOAD、PATH_EXAMPLES、summarization、plan_mode_usage、GUARDRAILS、STREAMING、MCP_SERVER）
