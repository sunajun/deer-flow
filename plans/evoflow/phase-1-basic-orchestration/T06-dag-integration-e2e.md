# T06 - DAG 集成测试、E2E 测试与文档更新

## 元信息
- **任务ID**: T06
- **阶段**: 第1期 - 基础编排增强
- **优先级**: P4
- **预估工期**: 2 天
- **依赖任务**: T05
- **关联差距**: 差距1 - 显式 DAG 编排

## 目标
完成 DAG 编排的集成测试和 E2E 测试，覆盖并行执行、结果传递、失败重编排等关键场景，更新相关文档和配置。

## 详细实现步骤

### 步骤1: 创建 PlanEngine 集成测试
- **文件**: `backend/tests/test_plan_engine.py`
- **操作**: 新建
- **内容**: 使用 mock LLM 测试 PlanEngine
```python
# 测试用例：
# test_create_from_intent_simple - 简单任务拆分
# test_create_from_intent_complex - 复杂多步骤任务
# test_verify_acceptance_pass - 验收通过
# test_verify_acceptance_fail - 验收失败
# test_reorchestrate_retry - 重试策略
# test_reorchestrate_split - 拆分策略
# test_reorchestrate_change_assignee - 换代理策略
# test_find_downstream_direct - 直接下游
# test_find_downstream_transitive - 传递下游
# test_find_downstream_diamond - 菱形依赖
```
- **验收**: mock LLM 场景下所有测试通过

### 步骤2: DAG 并行执行 + 结果传递集成测试
- **文件**: `backend/tests/test_plan_engine.py`
- **操作**: 续写
- **内容**: 测试子代理并行派发和上下文传递。**关键**: 测试 `_dispatch_subagent` 复用 `SubagentExecutor` 的机制。
```python
# 测试用例：
# test_parallel_execution - A→[B,C]→D 并行执行
# test_context_passing - B 的结果传递给 D
# test_context_from_multiple - D 从 B 和 C 都继承上下文
# test_linear_execution - A→B→C 串行执行
# test_mixed_execution - 混合并行和串行
# test_dispatch_subagent_uses_executor - _dispatch_subagent 调用 SubagentExecutor.execute_async
```
- **验收**: 并行执行正确，上下文传递完整

### 步骤3: 失败节点重编排流程测试
- **文件**: `backend/tests/test_plan_engine.py`
- **操作**: 续写
- **内容**: 测试失败处理和重编排
```python
# 测试用例：
# test_single_node_failure - 单节点失败
# test_cascading_failure - 级联失败（B失败→C不执行）
# test_reorchestrate_after_failure - 失败后重编排
# test_max_reorchestrate_retries - 超过最大重编排次数
# test_partial_failure - 部分节点失败，其余成功
```
- **验收**: 失败检测正确，重编排后可恢复

### 步骤4: 边界条件测试
- **文件**: `backend/tests/test_plan_engine.py`
- **操作**: 续写
- **内容**: 测试各种边界情况
```python
# 测试用例：
# test_empty_dag - 空图（无节点）
# test_single_node_dag - 单节点图
# test_circular_dependency - 环形依赖
# test_all_nodes_fail - 全部失败
# test_barrier_waiting - 闸口等待
# test_node_timeout - 节点超时
# test_orphan_node - 孤立节点
# test_self_dependency - 自依赖
```
- **验收**: 边界情况均有合理处理

### 步骤5: E2E 测试
- **文件**: `backend/tests/test_plan_e2e.py`
- **操作**: 新建
- **内容**: 端到端 Plan 流程测试。**关键**: 测试 PlanGraph 作为独立 StateGraph 通过 plan_tool 被调用的完整流程。
```python
# 测试用例：
# test_full_plan_lifecycle - Plan→确认→执行→验收→完成
# test_plan_with_approval_rejection - Plan 确认拒绝
# test_plan_with_failure_and_retry - 失败+重试+成功
# test_plan_api_crud - API CRUD 全流程
# test_plan_progress_sse - SSE 进度推送
# test_plan_tool_invocation - lead_agent 通过 plan_tool 调用 PlanGraph
# test_plan_graph_independent_state - PlanGraph 状态独立于 ThreadState
```
- **验收**: 端到端流程顺畅

### 步骤6: 更新后端文档
- **文件**: `backend/CLAUDE.md`
- **操作**: 改造
- **内容**: 新增 plan 模块文档，反映 PlanGraph 独立架构（不是 lead_agent 修改）
  - 模块位置和职责
  - PlanDAG 数据模型说明
  - **PlanGraph 独立 StateGraph 架构**（不是 lead_agent 的节点扩展）
  - plan_tool 工具说明（lead_agent 通过 plan_tool 与 PlanGraph 交互）
  - PlanState 与 ThreadState 的关系
  - API 端点列表
  - 配置项说明（PlanConfig）
  - 与 GoalTracker 的联动
- **验收**: 文档覆盖所有新增功能，架构描述准确

### 步骤7: 新增 PlanConfig 配置类
- **文件**: `backend/packages/harness/deerflow/config/plan_config.py`
- **操作**: 新建
- **内容**: 新增 PlanConfig Pydantic 配置类和 `load_plan_config_from_dict` 函数，遵循现有配置模式（如 `TitleConfig` + `load_title_config_from_dict`）。
```python
from pydantic import BaseModel, Field


class PlanConfig(BaseModel):
    """Plan DAG 编排配置。"""

    enabled: bool = Field(default=False, description="是否启用 Plan DAG 编排")
    max_parallel_nodes: int = Field(default=3, description="最大并行节点数")
    default_timeout: int = Field(default=900, description="节点默认超时（秒）")
    auto_approve: bool = Field(default=False, description="是否自动确认 Plan")
    acceptance_verification: bool = Field(default=True, description="是否启用验收校验")
    reorchestrate_max_retries: int = Field(default=2, description="最大重编排次数")


_plan_config: PlanConfig = PlanConfig()


def load_plan_config_from_dict(data: dict | None) -> PlanConfig:
    """从字典加载 PlanConfig 并更新全局单例。"""
    global _plan_config
    if data is None:
        _plan_config = PlanConfig()
    else:
        _plan_config = PlanConfig.model_validate(data)
    return _plan_config


def get_plan_config() -> PlanConfig:
    """获取 PlanConfig 全局单例。"""
    return _plan_config
```

- **文件**: `backend/packages/harness/deerflow/config/app_config.py`
- **操作**: 改造
- **内容**: 在 `AppConfig` 中新增 `plan` 字段，在 `_apply_singleton_configs` 中调用 `load_plan_config_from_dict`。
```python
from deerflow.config.plan_config import PlanConfig, load_plan_config_from_dict


class AppConfig(BaseModel):
    # ... 现有字段 ...
    plan: PlanConfig = Field(default_factory=PlanConfig, description="Plan DAG 编排配置")

    @classmethod
    def _apply_singleton_configs(cls, config: Self, acp_agents: dict[str, ACPAgentConfig]) -> None:
        # ... 现有加载 ...
        load_plan_config_from_dict(config.plan.model_dump())
```
- **验收**: 配置项可被正确解析，`PlanConfig` 遵循现有配置模式

## 验收标准
- [ ] PlanEngine 集成测试全部通过（mock LLM）
- [ ] 并行执行和结果传递正确
- [ ] 失败重编排流程正常
- [ ] 所有边界条件有合理处理
- [ ] E2E 测试通过（包括 plan_tool 调用 PlanGraph）
- [ ] backend/CLAUDE.md 更新完成，反映 PlanGraph 独立架构
- [ ] PlanConfig 配置类创建完成，集成到 AppConfig

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 集成测试 | 并行 A→[B,C]→D | B、C 并行，D 等两者完成 |
| 集成测试 | 上下文传递 | D 可访问 B、C 结果 |
| 集成测试 | 级联失败 | B 失败→C 不执行→下游重置 |
| 集成测试 | 重编排恢复 | 重编排后失败节点重新执行 |
| 集成测试 | 节点超时 | 超时节点标记 FAILED |
| E2E 测试 | 完整生命周期 | 创建→确认→执行→完成 |
| E2E 测试 | plan_tool 调用 | lead_agent 通过 plan_tool 触发 PlanGraph |
| E2E 测试 | PlanGraph 独立状态 | PlanState 不影响 ThreadState |
| 边界测试 | 空图 | is_complete=True |
| 边界测试 | 环形依赖 | validate_dag 报错 |
| 配置测试 | PlanConfig 默认值 | enabled=False |
| 配置测试 | PlanConfig 自定义 | 从 config.yaml 加载 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| mock LLM 与真实 LLM 行为差异 | 中 | E2E 用真实 LLM 辅助验证 |
| 并行测试不稳定 | 低 | 使用确定性 mock，避免时序依赖 |
| 测试覆盖率不足 | 低 | 对照测试矩阵逐项检查 |
| PlanConfig 集成遗漏 | 低 | 遵循现有 TitleConfig/MemoryConfig 模式 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第1节
- `backend/packages/harness/deerflow/config/title_config.py` - TitleConfig + load_title_config_from_dict 模式参考
- `backend/packages/harness/deerflow/config/app_config.py` - AppConfig 和 _apply_singleton_configs 参考
- `backend/packages/harness/deerflow/plan/graph.py` - PlanGraph 独立架构
- `backend/packages/harness/deerflow/plan/plan_tool.py` - plan_tool 实现
