# EvoFlow 任务文档审查报告

> 审查日期：2026-05-22
> 修复日期：2026-05-22
> 审查范围：T01~T35 全部 35 个任务文档
> 对照基线：EVOFLOW_IMPLEMENTATION_PLAN.md + DeerFlow 2.0 实际代码
> **状态：全部问题已修复 ✅**

---

## 修复总览

| 类别 | 问题数 | 已修复 | 状态 |
|------|--------|--------|------|
| 致命问题（CRITICAL） | 7 | 7 | ✅ 全部修复 |
| 重大问题（MAJOR） | 10 | 10 | ✅ 全部修复 |
| 轻微问题（MINOR） | 10 | 10 | ✅ 全部修复 |
| 跨任务一致性问题 | 4 | 4 | ✅ 全部修复 |
| **合计** | **31** | **31** | **✅** |

---

## 一、致命问题（CRITICAL）— ✅ 全部已修复

### C1. lead_agent 不是 StateGraph，DAG 编排方案不可行 ✅ 已修复

**涉及任务**：T03, T04, T05, T06

**原问题**：方案假设 lead_agent 使用 StateGraph，可通过 `add_node()`/`add_conditional_edges()` 添加 DAG 调度节点。实际代码使用 `create_agent()` 创建 ReAct agent。

**修复方案**：采用方案 A — DAG 编排实现为**独立 LangGraph StateGraph（PlanGraph）**，lead_agent 通过 `plan_tool` 工具与之交互（类似 `task_tool` 模式）。

**具体修改**：
- T04 完全重写：从"在 lead_agent 图中添加节点"改为"独立 PlanGraph + plan_tool"
- 新增 `PlanState` TypedDict 作为 PlanGraph 的独立状态
- `_dispatch_subagent` 复用 `SubagentExecutor.execute_async()` 机制
- `plan_tool` 注册到 `BUILTIN_TOOLS`，通过 `subagent_enabled` 参数控制

### C2. AgentState 文件路径和类名错误 ✅ 已修复

**涉及任务**：T01, T02, T03, T04

**修复**：所有引用统一修正为：
- 文件路径：`backend/packages/harness/deerflow/agents/thread_state.py`
- 类名：`ThreadState`（继承自 `langchain.agents.AgentState`）

### C3. TypedDict 不支持 Pydantic 模型字段 ✅ 已修复

**涉及任务**：T01, T03, T07

**修复**：所有 ThreadState 新增字段使用 `NotRequired[dict | None]` 模式：
- `goal_snapshot: NotRequired[dict | None]`（而非 `GoalSnapshot | None`）
- `plan: NotRequired[dict | None]`（而非 `PlanDAG | None`）
- `scene_state: NotRequired[dict | None]`（而非 `SceneState | None`）
- 中间件/服务内部做 dict ↔ Pydantic 模型转换

### C4. 中间件接口与 LangChain AgentMiddleware 不兼容 ✅ 已修复

**涉及任务**：T01, T02, T08

**修复**：
- `GoalTrackerMiddleware` 继承 `AgentMiddleware[ThreadState]`
- 使用标准钩子：`before_agent`（注入目标摘要）、`after_model`（检测方向变更）
- `on_plan_created`/`on_subtask_completed`/`on_direction_change` 改为公开业务方法，由 PlanEngine 直接调用
- `SceneMiddleware` 继承 `AgentMiddleware[ThreadState]`，使用 `after_model`（检查 tool_calls）、`after_agent`（自动淡化）、`before_agent`（意图检测）

### C5. get_available_tools 签名完全不同 ✅ 已修复

**涉及任务**：T09

**修复**：新增 `allowed_tools: set[str] | None = None` 关键字参数，在工具去重步骤后做场景过滤。

### C6. Gateway 启动/关闭使用 lifespan 而非 on_event ✅ 已修复

**涉及任务**：T14

**修复**：在 `lifespan` 函数的 `yield` 前启动调度服务，`yield` 后关闭。删除所有 `@app.on_event("startup")` 引用。

### C7. agents.py 路由文件已存在 ✅ 已修复

**涉及任务**：T16

**修复**：新建独立路由文件 `agent_configs.py`，前缀 `/api/agent-configs`，避免覆盖现有 `agents.py`。

---

## 二、重大问题（MAJOR）— ✅ 全部已修复

### M1. PlanDAG.edges 使用 tuple 类型 ✅ 已修复
`edges: list[tuple[str, str]]` → `edges: list[list[str]]`

### M2. get_channel_manager 不存在 ✅ 已修复
改用 `get_channel_service()` from `app.channels.service`

### M3. SkillInstaller 类不存在 ✅ 已修复
T17 新增 `SkillInstaller` 类，封装现有 `safe_extract_skill_archive`、`SkillAlreadyExistsError` 等函数

### M4. IM 命令系统与现有 commands.py 冲突 ✅ 已修复
T23 明确扩展 `KNOWN_CHANNEL_COMMANDS` frozenset，保持现有命令兼容

### M5. 前端路由结构不匹配 ✅ 已修复
T12、T19、T27 明确说明修改 `workspace-sidebar.tsx` 添加导航项

### M6. 配置系统使用 Pydantic AppConfig ✅ 已修复
T06 新增 `PlanConfig` + `load_plan_config_from_dict`，T15 新增 `SchedulerConfig`，T28 新增 `MarketplaceConfig`

### M7. DAG 执行中子代理派发机制未与现有 task_tool 对齐 ✅ 已修复
T04 的 `_dispatch_subagent` 复用 `SubagentExecutor.execute_async()` 机制

### M8. Claude Code 多会话与现有 ACP 工具关系不清 ✅ 已修复
T20 明确 Claude Code 会话是 ACP 的特化场景，复用 ACP 通信层

### M9. 数据库持久化方案未指定数据库类型 ✅ 已修复
T15 明确使用 SQLAlchemy + `get_session_factory()` from `deerflow.persistence.engine`

### M10. Electron + Python 后端打包可行性风险 ✅ 已修复
T29 新增隐式导入扫描步骤、打包后冒烟测试、Nuitka 替代方案评估

---

## 三、轻微问题（MINOR）— ✅ 全部已修复

| 编号 | 问题 | 修复方式 |
|------|------|---------|
| m1 | get_ready_nodes() 有副作用 | 分离为 `get_ready_nodes()`（纯查询）+ `get_manual_waiting_nodes()` |
| m2 | _find_downstream 用 list.pop(0) | 改用 `collections.deque.popleft()` |
| m3 | 意图检测关键词硬编码 | 提取到 `SceneConfig.keywords` 配置 |
| m4 | 内存存储无上限 | 添加 `max_tasks=10000` + LRU 淘汰 |
| m5 | cron 判断逻辑有误 | 改用 `croniter.match()` + `last_fired_cron_time` 去重 |
| m6 | 缺少 macOS 代码签名 | T29/T30/T35 新增签名和公证步骤 |
| m7 | macOS 11+ 和 Intel Mac | T30 明确系统要求，双架构支持 |
| m8 | 自动更新需要代码签名 | T35 新增签名约束章节 |
| m9 | 缺少错误处理步骤 | 各任务补充具体错误处理逻辑 |
| m10 | SSE 流未处理客户端断连 | T22 使用 `request.is_disconnected()` 检测 |

---

## 四、跨任务一致性问题 — ✅ 全部已修复

| 编号 | 问题 | 修复方式 |
|------|------|---------|
| X1 | 中间件注册方式不一致 | 统一通过 `custom_middlewares` 参数注册到 `_build_middlewares()` |
| X2 | 状态字段扩展分散 | 统一使用 `NotRequired[dict | None]` 模式 |
| X3 | API 路由注册方式不一致 | 统一在 `create_app()` 中 `app.include_router()` |
| X4 | 配置更新分散 | 每个任务明确新增 Pydantic 配置类 + `load_*_from_dict` |

---

## 五、修复后的架构要点

### DAG 编排架构（最关键修正）

```
lead_agent (create_agent)
    │
    ├── plan_tool (新增内置工具)
    │       │
    │       └── PlanGraph (独立 StateGraph)
    │               ├── plan_create_node
    │               ├── plan_execute_dag_node → SubagentExecutor
    │               ├── plan_supervise_node
    │               └── plan_reorchestrate_node
    │
    ├── task_tool (现有子代理工具)
    └── ... 其他工具
```

### 中间件架构

```
AgentMiddleware[ThreadState]
    ├── GoalTrackerMiddleware
    │   ├── before_agent → inject_to_prompt
    │   ├── after_model → 检测方向变更
    │   └── 公开方法: on_plan_created, on_subtask_completed, on_direction_change
    ├── SceneMiddleware
    │   ├── after_model → 检查 tool_calls 场景过滤
    │   ├── after_agent → 自动淡化
    │   └── before_agent → 意图检测
    └── PermissionMiddleware
        └── wrap_tool_call → 权限校验
```

### 状态扩展

```python
class ThreadState(AgentState):
    # 现有字段
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
    # 新增字段（全部 dict，JSON 可序列化）
    goal_snapshot: NotRequired[dict | None]      # T01
    scene_state: NotRequired[dict | None]        # T07
```

### 路由注册

```python
# create_app() 中新增
app.include_router(plans.router)          # T05: /api/plans
app.include_router(scenes.router)         # T09: /api/scenes
app.include_router(tasks.router)          # T11: /api/tasks
app.include_router(schedules.router)      # T14: /api/schedules
app.include_router(agent_configs.router)  # T16: /api/agent-configs（非 agents.py）
app.include_router(claude_sessions.router)# T22: /api/claude-sessions
app.include_router(marketplace.router)    # T27: /api/marketplace
```
