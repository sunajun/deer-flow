# EvoFlow 能力补齐 — 开发计划总览索引

> 版本：v1.0 | 日期：2026-05-22
> 基础项目：DeerFlow 2.0 (commit `253542ea`)
> 方案文档：[EVOFLOW_IMPLEMENTATION_PLAN.md](../../EVOFLOW_IMPLEMENTATION_PLAN.md)

---

## 总体概览

| 维度 | 数值 |
|------|------|
| 总任务数 | 35 |
| 总阶段数 | 4 |
| 总预估工期 | 16 周（1人全栈串行） |
| 覆盖差距 | 差距1~10（EvoFlow 八大核心支柱 + 架构层 + 命令层） |

---

## 阶段路线图

```
第1期 (3周): 基础编排增强 ──── T01~T06
    │
    ↓
第2期 (2.5周): 场景与观测 ─── T07~T15
    │
    ↓
第3期 (2.5周): 治理与协同 ─── T16~T28
    │
    ↓
第4期 (8周): 桌面客户端与SOLO沙箱 ── T29~T35
```

---

## Phase 1 — 基础编排增强（3 周）

> 交付目标：Plan + DAG + 目标追踪可端到端运行

| 任务ID | 文档 | 标题 | 工期 | 依赖 | 关联差距 |
|--------|------|------|------|------|----------|
| T01 | [T01-goal-models-middleware.md](phase-1-basic-orchestration/T01-goal-models-middleware.md) | 目标快照数据模型与中间件 | 2天 | 无 | 差距5 |
| T02 | [T02-goal-direction-realign.md](phase-1-basic-orchestration/T02-goal-direction-realign.md) | 目标方向变更再对齐与测试 | 2天 | T01 | 差距5 |
| T03 | [T03-dag-models-engine.md](phase-1-basic-orchestration/T03-dag-models-engine.md) | DAG 数据模型与 PlanEngine 骨架 | 3天 | 无（与T01并行） | 差距1 |
| T04 | [T04-dag-langgraph-nodes.md](phase-1-basic-orchestration/T04-dag-langgraph-nodes.md) | LangGraph DAG 调度节点与子代理并行派发 | 4天 | T03 | 差距1 |
| T05 | [T05-dag-verification-reorchestrate.md](phase-1-basic-orchestration/T05-dag-verification-reorchestrate.md) | DAG 验收校验、重编排与 API | 3天 | T04 | 差距1 |
| T06 | [T06-dag-integration-e2e.md](phase-1-basic-orchestration/T06-dag-integration-e2e.md) | DAG 集成测试、E2E 测试与文档更新 | 2天 | T05 | 差距1 |

**依赖关系**：
```
T01 ──→ T02
T03 ──→ T04 ──→ T05 ──→ T06
（T01/T02 与 T03/T04/T05/T06 可并行）
```

**关键产出**：
- `backend/packages/harness/deerflow/goal/` — 目标追踪模块
- `backend/packages/harness/deerflow/plan/` — DAG 编排模块
- `backend/app/gateway/routers/plans.py` — Plan API
- AgentState 扩展：`goal_snapshot`、`plan`、`plan_approved`、`active_node_ids`

---

## Phase 2 — 场景与观测（2.5 周）

> 交付目标：场景切换 + 任务追踪 + 定时调度可用

| 任务ID | 文档 | 标题 | 工期 | 依赖 | 关联差距 |
|--------|------|------|------|------|----------|
| T07 | [T07-scene-models-registry.md](phase-2-scene-observability/T07-scene-models-registry.md) | 场景数据模型、注册表与基础过滤 | 3天 | T04 | 差距2 |
| T08 | [T08-scene-middleware-auto-deactivate.md](phase-2-scene-observability/T08-scene-middleware-auto-deactivate.md) | SceneMiddleware、自动淡化与意图检测 | 3天 | T07 | 差距2 |
| T09 | [T09-scene-tool-assembly-api.md](phase-2-scene-observability/T09-scene-tool-assembly-api.md) | 场景工具装配改造、场景切换工具与 API | 3天 | T08 | 差距2 |
| T10 | [T10-task-center-models-service.md](phase-2-scene-observability/T10-task-center-models-service.md) | 任务中心数据模型与服务层 | 3天 | 无（与T07并行） | 差距8 |
| T11 | [T11-task-center-api-logs.md](phase-2-scene-observability/T11-task-center-api-logs.md) | 任务中心 API 路由与日志存储 | 2天 | T10 | 差距8 |
| T12 | [T12-task-center-frontend.md](phase-2-scene-observability/T12-task-center-frontend.md) | 任务中心前端页面与集成测试 | 2天 | T11 | 差距8 |
| T13 | [T13-scheduler-models-service.md](phase-2-scene-observability/T13-scheduler-models-service.md) | 定时任务数据模型与调度服务 | 3天 | T10 | 差距4 |
| T14 | [T14-scheduler-execution-notification.md](phase-2-scene-observability/T14-scheduler-execution-notification.md) | 定时任务执行触发与 IM 推送 | 3天 | T13 | 差距4 |
| T15 | [T15-scheduler-persistence-test.md](phase-2-scene-observability/T15-scheduler-persistence-test.md) | 定时任务持久化与完整测试 | 2天 | T14 | 差距4 |

**依赖关系**：
```
T07 ──→ T08 ──→ T09          （场景系统）
T10 ──→ T11 ──→ T12          （任务中心）
T10 ──→ T13 ──→ T14 ──→ T15  （定时任务）
（场景系统与任务中心/定时任务可并行）
```

**关键产出**：
- `backend/packages/harness/deerflow/scene/` — 场景模块
- `backend/packages/harness/deerflow/scheduler/` — 定时任务模块
- `backend/app/gateway/services/task_center_service.py` — 任务中心服务
- `backend/app/gateway/routers/schedules.py` — 定时任务 API
- `frontend/src/app/workspace/tasks/` — 任务中心前端页面

---

## Phase 3 — 治理与协同（2.5 周）

> 交付目标：多会话委派 + 技能市场 + IM 命令完整可用

| 任务ID | 文档 | 标题 | 工期 | 依赖 | 关联差距 |
|--------|------|------|------|------|----------|
| T16 | [T16-agent-config-management.md](phase-3-governance-collaboration/T16-agent-config-management.md) | 智能体配置管理与版本追踪 | 3天 | T09 | 差距9 |
| T17 | [T17-skill-lifecycle-management.md](phase-3-governance-collaboration/T17-skill-lifecycle-management.md) | 技能生命周期管理与市场对接 | 3天 | T16 | 差距9 |
| T18 | [T18-governance-permission.md](phase-3-governance-collaboration/T18-governance-permission.md) | 权限治理 + API | 2天 | T16 | 差距9 |
| T19 | [T19-governance-frontend.md](phase-3-governance-collaboration/T19-governance-frontend.md) | 前端治理页面 + 集成测试 | 2天 | T16,T17,T18 | 差距9 |
| T20 | [T20-claude-session-models-manager.md](phase-3-governance-collaboration/T20-claude-session-models-manager.md) | Claude Code 多会话数据模型 + SessionManager 骨架 | 3天 | 无 | 差距3 |
| T21 | [T21-claude-session-acp-stream.md](phase-3-governance-collaboration/T21-claude-session-acp-stream.md) | Claude Code 会话 ACP 通信适配 + 输出流 | 4天 | T20 | 差距3 |
| T22 | [T22-claude-session-tools-api.md](phase-3-governance-collaboration/T22-claude-session-tools-api.md) | Claude Code 会话 LangGraph 工具 + API + 测试 | 3天 | T20,T21 | 差距3 |
| T23 | [T23-im-commands-base-core.md](phase-3-governance-collaboration/T23-im-commands-base-core.md) | IM 命令基类 + 核心命令实现 | 3天 | 无 | 差距10 |
| T24 | [T24-im-commands-cross-channel.md](phase-3-governance-collaboration/T24-im-commands-cross-channel.md) | IM 命令跨渠道响应适配 | 2天 | T23 | 差距10 |
| T25 | [T25-im-commands-integration.md](phase-3-governance-collaboration/T25-im-commands-integration.md) | IM 命令集成测试 | 2天 | T23,T24 | 差距10 |
| T26 | [T26-marketplace-models-registry.md](phase-3-governance-collaboration/T26-marketplace-models-registry.md) | 技能/MCP 市场数据模型 + Registry + 安装流程 | 4天 | T17 | 差距6 |
| T27 | [T27-marketplace-api-frontend.md](phase-3-governance-collaboration/T27-marketplace-api-frontend.md) | 技能/MCP 市场 API + 前端市场页 | 4天 | T26 | 差距6 |
| T28 | [T28-marketplace-updates-test.md](phase-3-governance-collaboration/T28-marketplace-updates-test.md) | 技能/MCP 市场更新检查 + 测试 | 2天 | T26 | 差距6 |

**依赖关系**：
```
T16 ──→ T17 ──→ T26 ──→ T27
                 └──→ T28
T16 ──→ T18 ──→ T19（还需T17）
T20 ──→ T21 ──→ T22          （Claude多会话）
T23 ──→ T24 ──→ T25          （IM命令）
（治理面/Claude多会话/IM命令/市场可并行）
```

**关键产出**：
- `backend/packages/harness/deerflow/config/` — 智能体配置管理
- `backend/packages/harness/deerflow/skills/manager.py` — 技能生命周期管理
- `backend/packages/harness/deerflow/claude_session/` — Claude 多会话模块
- `backend/packages/harness/deerflow/marketplace/` — 技能市场模块
- `backend/app/channels/commands/` — IM 命令系统
- `frontend/src/app/workspace/governance/` — 治理前端页面
- `frontend/src/app/workspace/marketplace/` — 市场前端页面

---

## Phase 4 — 桌面客户端与 SOLO 沙箱（8 周）

> 交付目标：无需 Docker 开箱即用桌面版，完整对齐 EvoFlow 能力

| 任务ID | 文档 | 标题 | 工期 | 依赖 | 关联差距 |
|--------|------|------|------|------|----------|
| T29 | [T29-electron-skeleton-python-backend.md](phase-4-desktop-sandbox/T29-electron-skeleton-python-backend.md) | Electron 骨架 + 内嵌 Python 后端 + 启动向导 | 3天 | 无 | 差距7 |
| T30 | [T30-macos-virtualization-framework.md](phase-4-desktop-sandbox/T30-macos-virtualization-framework.md) | macOS Virtualization.framework 适配 | 2周 | T29 | 差距7 |
| T31 | [T31-windows-wsl2.md](phase-4-desktop-sandbox/T31-windows-wsl2.md) | Windows WSL2 适配 | 1周 | T29 | 差距7 |
| T32 | [T32-linux-firecracker.md](phase-4-desktop-sandbox/T32-linux-firecracker.md) | Linux Firecracker 适配 | 1周 | T29 | 差距7 |
| T33 | [T33-cross-platform-abstraction.md](phase-4-desktop-sandbox/T33-cross-platform-abstraction.md) | 跨平台抽象层 + 自动检测降级 | 1周 | T30,T31,T32 | 差距7 |
| T34 | [T34-vm-image-build.md](phase-4-desktop-sandbox/T34-vm-image-build.md) | VM 镜像构建 + 集成测试 | 1周 | T30,T31,T32,T33 | 差距7 |
| T35 | [T35-tray-console-packaging.md](phase-4-desktop-sandbox/T35-tray-console-packaging.md) | 系统托盘 + Claude 控制台 + 打包 | 1周 | T29,T30,T31,T32,T33 | 差距7 |

**依赖关系**：
```
T29 ──→ T30（macOS VM）
     ──→ T31（Windows WSL2）──┐
     ──→ T32（Linux FC）──────┤
                               ↓
                         T33（跨平台抽象层）
                               ↓
                         T34（VM镜像构建）
T29 + T30/T31/T32 + T33 ──→ T35（托盘+控制台+打包）
（T30/T31/T32 可并行）
```

**关键产出**：
- `desktop/` — Electron 桌面端完整项目
- `desktop/electron/vm-manager.ts` — VM 生命周期管理
- `desktop/native/macos/VirtualMachine.swift` — macOS 原生 VM
- `desktop/native/windows/wsl2-bridge.ts` — Windows WSL2 适配
- `backend/packages/harness/deerflow/sandbox/` — 沙箱策略与路由
- 三平台安装包：`.dmg` / `.exe` / `.AppImage`

---

## 全局依赖矩阵

```
Phase 1:  T01→T02 | T03→T04→T05→T06
                ↓
Phase 2:  T04→T07→T08→T09 | T10→T11→T12 | T10→T13→T14→T15
                ↓
Phase 3:  T09→T16→T17→T26→T27
                    └──→T28
               T16→T18→T19
               T20→T21→T22 | T23→T24→T25
                ↓
Phase 4:  T29→T30/T31/T32→T33→T34
          T29+T30/T31/T32+T33→T35
```

---

## 关联差距映射

| 差距 | 涵盖任务 | 阶段 | 核心交付 |
|------|---------|------|---------|
| 差距1 - 显式 DAG 编排 | T03, T04, T05, T06 | Phase 1 | PlanDAG + PlanEngine + DAG 调度节点 |
| 差距2 - 多场景系统 | T07, T08, T09 | Phase 2 | Scene 模型 + SceneMiddleware + 场景过滤 |
| 差距3 - Claude Code 多会话 | T20, T21, T22 | Phase 3 | ClaudeSessionManager + ACP 通信 + SSE 输出 |
| 差距4 - 定时任务 | T13, T14, T15 | Phase 2 | SchedulerService + cron 调度 + IM 推送 |
| 差距5 - 核心目标/子问题状态 | T01, T02 | Phase 1 | GoalSnapshot + GoalTrackerMiddleware |
| 差距6 - 技能/MCP 市场 | T26, T27, T28 | Phase 3 | MarketplaceRegistry + 安装流程 + 前端市场 |
| 差距7 - 桌面客户端 + SOLO 沙箱 | T29~T35 | Phase 4 | Electron + 内嵌 Python + 三平台 VM 沙箱 |
| 差距8 - 任务中心与观测面 | T10, T11, T12 | Phase 2 | TaskCenterService + 日志存储 + 前端页面 |
| 差距9 - 统一治理面 | T16, T17, T18, T19 | Phase 3 | AgentConfig + SkillManager + 权限治理 |
| 差距10 - IM 渠道命令对齐 | T23, T24, T25 | Phase 3 | 命令基类 + 跨渠道适配 + 集成测试 |

---

## 新增模块文件清单汇总

| 模块路径 | 所属差距 | 任务 |
|---------|---------|------|
| `backend/packages/harness/deerflow/goal/` | 差距5 | T01, T02 |
| `backend/packages/harness/deerflow/plan/` | 差距1 | T03, T04, T05 |
| `backend/packages/harness/deerflow/scene/` | 差距2 | T07, T08, T09 |
| `backend/packages/harness/deerflow/scheduler/` | 差距4 | T13, T14, T15 |
| `backend/packages/harness/deerflow/claude_session/` | 差距3 | T20, T21, T22 |
| `backend/packages/harness/deerflow/marketplace/` | 差距6 | T26, T27, T28 |
| `backend/packages/harness/deerflow/config/` | 差距9 | T16 |
| `backend/packages/harness/deerflow/skills/manager.py` | 差距9 | T17 |
| `backend/packages/harness/deerflow/sandbox/` | 差距7 | T30~T34 |
| `backend/app/channels/commands/` | 差距10 | T23, T24, T25 |
| `backend/app/gateway/services/task_center_service.py` | 差距8 | T10 |
| `backend/app/gateway/routers/plans.py` | 差距1 | T05 |
| `backend/app/gateway/routers/schedules.py` | 差距4 | T14 |
| `backend/app/gateway/routers/agents.py` | 差距9 | T16 |
| `backend/app/gateway/routers/marketplace.py` | 差距6 | T27 |
| `backend/app/gateway/routers/claude_sessions.py` | 差距3 | T22 |
| `frontend/src/app/workspace/tasks/` | 差距8 | T12 |
| `frontend/src/app/workspace/governance/` | 差距9 | T19 |
| `frontend/src/app/workspace/marketplace/` | 差距6 | T27 |
| `desktop/` | 差距7 | T29~T35 |

---

## 新增中间件清单

| 中间件 | 所属差距 | 任务 | 职责 |
|--------|---------|------|------|
| GoalTrackerMiddleware | 差距5 | T01, T02 | 目标快照注入、子问题状态更新、方向变更再对齐 |
| SceneMiddleware | 差距2 | T08 | 工具调用拦截、场景过滤、自动淡化、意图检测 |
| ScheduleMiddleware | 差距4 | T13 | 定时任务触发拦截 |
| ClaudeSessionMiddleware | 差距3 | T20 | Claude Code 会话生命周期管理 |
| PermissionMiddleware | 差距9 | T18 | 角色权限校验、工具白名单 |

---

## 新增 API 路由汇总

| 路由前缀 | 差距 | 任务 | 核心端点 |
|---------|------|------|---------|
| `/api/plans` | 差距1 | T05 | CRUD + approve + retry + reorchestrate + progress(SSE) |
| `/api/scenes` | 差距2 | T09 | activate + deactivate + list_active |
| `/api/claude-sessions` | 差距3 | T22 | create + send + terminate + stream(SSE) + list |
| `/api/schedules` | 差距4 | T14 | CRUD + pause + resume + trigger + runs |
| `/api/goals` | 差距5 | T02 | get + update_direction + list_sub_problems |
| `/api/tasks` | 差距8 | T11 | list + detail + logs + retry + rerun + cancel + export |
| `/api/agents` | 差距9 | T16 | CRUD + versions + rollback |
| `/api/skills` | 差距9 | T17 | install + uninstall + enable + disable + check-updates |
| `/api/governance/roles` | 差距9 | T18 | list + update |
| `/api/marketplace` | 差距6 | T27 | search + install + uninstall + updates + package detail |

---

## 配置增量汇总

所有新增配置将添加到 `config.example.yaml`，详见方案文档附录 A：

- `plan:` — DAG 编排配置
- `scenes:` — 场景系统配置
- `claude_sessions:` — Claude 多会话配置
- `scheduler:` — 定时任务配置
- `marketplace:` — 技能市场配置
- `governance:` — 治理权限配置

---

## 风险总览

| 风险 | 概率 | 影响范围 | 缓解措施 |
|------|------|---------|---------|
| LangGraph StateGraph 扩展点不足 | 中 | Phase 1 | 提前做 POC 验证 |
| macOS Virtualization.framework 兼容性 | 中 | Phase 4 | 提供本地模式降级 |
| Windows WSL2 启用复杂 | 中 | Phase 4 | 首次启动向导提供一键启用脚本 |
| Claude Code ACP 协议变更 | 低 | Phase 3 | 抽象通信层，协议变更只改适配器 |
| Electron 包体过大 | 低 | Phase 4 | Web 安装器 + 增量更新 + VM 镜像可选下载 |
| 市场 Registry 无开源方案 | 中 | Phase 3 | 第一版用 GitHub Repo + JSON 索引 |

---

## 人力与工期估算

| 方案 | 工期 | 所需人力 | 备注 |
|------|------|---------|------|
| 串行（完整 SOLO 沙箱） | 16 周 | 1 人全栈 | 含 macOS/Windows/Linux 全平台沙箱适配 |
| 串行（无 SOLO 沙箱，Docker 模式） | 10 周 | 1 人全栈 | 适合企业内部部署，用户预装 Docker |
| 并行（2 人） | 10 周 | 1 后端 + 1 前端 | 后端负责沙箱+业务，前端负责页面 |
| 并行（3 人） | 8 周 | 2 后端 + 1 前端 | 1 个后端做沙箱适配，1 个做业务功能 |
| 并行（4 人） | 7 周 | 2 后端 + 1 前端 + 1 客户端 | 客户端开发负责 macOS/Windows 原生虚拟化模块 |
