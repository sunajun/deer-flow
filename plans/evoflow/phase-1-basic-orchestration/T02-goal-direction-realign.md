# T02 - 目标方向变更再对齐与测试

## 元信息
- **任务ID**: T02
- **阶段**: 第1期 - 基础编排增强
- **优先级**: P1
- **预估工期**: 2 天
- **依赖任务**: T01
- **关联差距**: 差距5 - 核心目标/子问题状态

## 目标
实现目标方向变更时的再对齐机制，以及 Plan 创建/子任务完成的业务方法调用链，完成目标追踪模块的完整测试。

## 详细实现步骤

### 步骤1: 实现 on_plan_created 业务方法
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py`
- **操作**: 续写
- **内容**: Plan 创建时自动生成 GoalSnapshot。此方法是 `GoalTrackerMiddleware` 的**公开业务方法**，由 `PlanEngine` 在创建 Plan 后直接调用，**不是**中间件钩子。
```python
def on_plan_created(self, state: ThreadState, plan: dict) -> dict:
    """Plan 创建时，从 Plan 生成 GoalSnapshot。由 PlanEngine 直接调用。

    Args:
        state: 当前 ThreadState（用于读取已有 goal_snapshot）。
        plan: PlanDAG 的 dict 表示（plan.model_dump()）。

    Returns:
        状态更新 dict，包含新的 goal_snapshot。
    """
    snapshot = GoalSnapshot(
        goal_id=f"goal_{plan.get('plan_id', 'unknown')}",
        core_goal=plan.get("goal", ""),
        non_goals=[],
        acceptance_criteria=plan.get("acceptance_criteria", []),
        sub_problems=[
            SubProblem(
                id=f"sub_{node_id}",
                title=node_data.get("title", ""),
                description=node_data.get("description", ""),
                acceptance_criteria=node_data.get("acceptance_criteria", []),
                assigned_to=node_data.get("assignee"),
            )
            for node_id, node_data in plan.get("nodes", {}).items()
        ],
    )
    return self._put_snapshot(snapshot)
```
- **验收**: Plan 创建后自动生成 GoalSnapshot，子问题与 DAG 节点一一对应

### 步骤2: 实现 on_subtask_completed 业务方法
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py`
- **操作**: 续写
- **内容**: 子任务完成时更新对应子问题状态。此方法是 `GoalTrackerMiddleware` 的**公开业务方法**，由 `PlanEngine` 在子任务完成后直接调用。
```python
def on_subtask_completed(self, state: ThreadState, node_id: str, result: str) -> dict:
    """子任务完成时，更新子问题状态。由 PlanEngine 直接调用。

    Args:
        state: 当前 ThreadState。
        node_id: 完成的 DAG 节点 ID。
        result: 子任务执行结果摘要。

    Returns:
        状态更新 dict，包含更新后的 goal_snapshot。
    """
    snapshot = self._get_snapshot(state)
    if snapshot is None:
        return {}
    for sub in snapshot.sub_problems:
        if sub.id == f"sub_{node_id}":
            sub.status = ProblemStatus.RESOLVED
            sub.result_summary = str(result)[:500]
            break
    return self._put_snapshot(snapshot)
```
- **验收**: 子任务完成后对应子问题标记为 RESOLVED

### 步骤3: 实现 on_direction_change 再对齐
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py`
- **操作**: 续写
- **内容**: 方向变更时记录变更历史、递增对齐版本、重置未完成子问题。此方法是 `GoalTrackerMiddleware` 的**公开业务方法**，由 `PlanEngine` 在检测到方向变更后直接调用。
```python
def on_direction_change(self, state: ThreadState, new_direction: str) -> dict:
    """方向变更时触发再对齐。由 PlanEngine 直接调用。

    Args:
        state: 当前 ThreadState。
        new_direction: 新的核心目标方向。

    Returns:
        状态更新 dict，包含更新后的 goal_snapshot。
    """
    snapshot = self._get_snapshot(state)
    if snapshot is None:
        return {}
    snapshot.direction_changes.append({
        "from": snapshot.core_goal,
        "to": new_direction,
        "at": datetime.now().isoformat(),
    })
    snapshot.core_goal = new_direction
    snapshot.alignment_version += 1
    snapshot.last_aligned_at = datetime.now()
    for sub in snapshot.sub_problems:
        if sub.status not in (ProblemStatus.RESOLVED, ProblemStatus.DROPPED):
            sub.status = ProblemStatus.OPEN
    return self._put_snapshot(snapshot)
```
- **验收**: 方向变更后对齐版本+1，未完成子问题重置为 OPEN

### 步骤4: 实现中间件标准钩子中的状态变更检测
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/goal_middleware.py`
- **操作**: 续写
- **内容**: 中间件的标准钩子（`after_model`、`after_agent`）用于检测相关状态变化。例如 `after_model` 可以检测 lead_agent 是否发出了方向变更的工具调用，然后触发 `on_direction_change`。
```python
@override
def after_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
    """检测模型输出中的方向变更信号。"""
    messages = state.get("messages", [])
    if not messages:
        return None
    from langchain_core.messages import AIMessage
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None or not last_ai.tool_calls:
        return None
    for tc in last_ai.tool_calls:
        if tc.get("name") == "change_direction" and tc.get("args", {}).get("new_direction"):
            return self.on_direction_change(state, tc["args"]["new_direction"])
    return None

@override
async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
    return self.after_model(state, runtime)
```
- **验收**: `after_model` 能检测 `change_direction` 工具调用并触发再对齐

### 步骤5: 创建完整测试
- **文件**: `backend/tests/test_goal_tracker.py`
- **操作**: 新建
- **内容**: 测试所有中间件方法和边界情况
```python
# 测试用例：
# test_goal_snapshot_creation - 基本创建
# test_on_plan_created - Plan→GoalSnapshot 转换
# test_on_subtask_completed - 子任务完成状态更新
# test_on_direction_change - 方向变更再对齐
# test_direction_change_resets_unfinished - 未完成子问题重置
# test_direction_change_preserves_resolved - 已完成子问题保留
# test_inject_to_prompt_full - 完整 prompt 注入
# test_inject_to_prompt_no_snapshot - 无快照返回空
# test_alignment_version_increments - 版本递增
# test_direction_change_history - 变更历史记录
# test_before_agent_injects_reminder - before_agent 注入消息
# test_before_agent_no_snapshot_returns_none - 无快照返回 None
# test_after_model_detects_direction_change - after_model 检测方向变更
# test_dict_roundtrip_serialization - dict ↔ GoalSnapshot 往返
```
- **验收**: `cd backend && make test` 通过

### 步骤6: 注册中间件到中间件链
- **文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
- **操作**: 改造
- **内容**: 在 `_build_middlewares()` 函数中，通过 `custom_middlewares` 参数注入 `GoalTrackerMiddleware`。**不要**直接修改 `_build_middlewares` 内部逻辑。
```python
from deerflow.agents.middlewares.goal_middleware import GoalTrackerMiddleware

goal_middleware = GoalTrackerMiddleware()
middlewares = _build_middlewares(
    config,
    model_name=model_name,
    agent_name=agent_name,
    custom_middlewares=[goal_middleware],
    app_config=resolved_app_config,
)
```
- **验收**: 中间件在 agent 初始化时通过 `custom_middlewares` 参数被加载

## 验收标准
- [ ] `on_plan_created` 正确从 PlanDAG dict 生成 GoalSnapshot
- [ ] `on_subtask_completed` 正确更新子问题状态为 RESOLVED
- [ ] `on_direction_change` 记录变更历史并递增对齐版本
- [ ] 方向变更后未完成子问题重置为 OPEN，已完成/已丢弃的保留
- [ ] `after_model` 标准钩子能检测方向变更工具调用
- [ ] `before_agent` 标准钩子能注入目标摘要
- [ ] 所有测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | on_plan_created 生成快照 | 子问题数=DAG节点数 |
| 单元测试 | on_subtask_completed | 子问题状态→RESOLVED |
| 单元测试 | on_direction_change | 版本+1, 核心目标更新 |
| 单元测试 | 再对齐重置未完成子问题 | OPEN/IN_PROGRESS→OPEN |
| 单元测试 | 再对齐保留已完成子问题 | RESOLVED 不变 |
| 单元测试 | 多次方向变更 | 变更历史有3条记录 |
| 单元测试 | inject_to_prompt 含变更历史 | 包含对齐版本 |
| 单元测试 | after_model 检测 change_direction | 触发 on_direction_change |
| 单元测试 | before_agent 注入 reminder | 返回 HumanMessage |
| 单元测试 | dict 序列化往返 | model_validate/model_dump 一致 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 方向变更频繁导致子问题反复重置 | 中 | 可选：保留 IN_PROGRESS 状态不重置 |
| result_summary 过长 | 低 | 截断为 500 字符 |
| after_model 误判方向变更 | 低 | 仅匹配特定工具名 `change_direction` |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第5节
- `backend/packages/harness/deerflow/agents/middlewares/todo_middleware.py` - after_model + hook_config 参考
- `backend/packages/harness/deerflow/agents/middlewares/dynamic_context_middleware.py` - before_agent 注入参考
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py` - _build_middlewares 和 custom_middlewares 参数
