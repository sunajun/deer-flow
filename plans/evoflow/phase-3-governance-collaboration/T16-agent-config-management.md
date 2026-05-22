# T16 - 智能体配置管理与版本追踪

## 元信息
- **任务ID**: T16
- **阶段**: 第3期 - 治理与协同
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: T09（场景系统，智能体与场景权限关联）
- **关联差距**: 差距9 - 统一治理面

## 目标
建立智能体配置版本管理（AgentConfigVersion），实现配置的版本追踪、发布、回滚全生命周期。与现有 `agents.py` 路由（自定义智能体 CRUD）协同工作，不覆盖已有功能。

## 重要约束

> **`backend/app/gateway/routers/agents.py` 已存在**，提供自定义智能体的 CRUD（list/get/create/update/delete/user-profile），路由前缀 `/api`，标签 `["agents"]`。本任务必须使用**不同的路由文件** `agent_configs.py`，前缀 `/api/agent-configs`，避免覆盖现有端点。

> 现有 `AgentConfig`（`deerflow/config/agents_config.py`）定义了 `name`、`description`、`model`、`tool_groups`、`skills` 字段。新的版本管理模型应**扩展**此模型，而非重新定义。

## 详细实现步骤

### 步骤1: 创建 AgentConfigVersion 模型
- **文件**: `backend/packages/harness/deerflow/config/agent_config_version.py`
- **操作**: 新建
- **内容**: 扩展现有 `AgentConfig`
```python
from datetime import datetime
from pydantic import BaseModel, Field
from deerflow.config.agents_config import AgentConfig


class AgentConfigVersion(AgentConfig):
    """扩展 AgentConfig，增加版本追踪字段。"""
    version: str = "1.0.0"
    allowed_scenes: list[str] = Field(default_factory=list)
    skill_whitelist: list[str] | None = None
    skill_blacklist: list[str] | None = None
    max_retries: int = 3
    temperature: float = 0.7
    system_prompt_suffix: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AgentConfigVersionSnapshot(BaseModel):
    """版本快照，用于历史记录。"""
    agent_name: str
    version: str
    snapshot: AgentConfigVersion
    created_at: datetime = Field(default_factory=datetime.now)
    change_summary: str = ""
```
- **验收**: 模型可实例化，继承 `AgentConfig` 的全部字段

### 步骤2: 创建 AgentConfigManager
- **文件**: `backend/packages/harness/deerflow/config/agent_config_manager.py`
- **操作**: 新建
- **内容**: 版本管理 CRUD
```python
class AgentConfigManager:
    def __init__(self):
        self._configs: dict[str, AgentConfigVersion] = {}
        self._versions: dict[str, list[AgentConfigVersionSnapshot]] = {}

    async def create(self, config: AgentConfigVersion) -> AgentConfigVersion: ...
    async def get(self, agent_name: str) -> AgentConfigVersion | None: ...
    async def update(self, agent_name: str, updates: dict) -> AgentConfigVersion:
        """更新配置，自动保存历史版本"""
    async def delete(self, agent_name: str) -> None: ...
    async def list_agents(self) -> list[AgentConfigVersion]: ...
    async def get_version_history(self, agent_name: str) -> list[AgentConfigVersionSnapshot]: ...
    async def rollback(self, agent_name: str, version: str) -> AgentConfigVersion: ...
```
- **验收**: CRUD 和版本回滚正确

### 步骤3: 实现版本追踪
- **文件**: `backend/packages/harness/deerflow/config/agent_config_manager.py`
- **操作**: 续写
- **内容**: 更新时自动保存旧版本
```python
async def update(self, agent_name: str, updates: dict) -> AgentConfigVersion:
    current = self._configs[agent_name]
    if agent_name not in self._versions:
        self._versions[agent_name] = []
    self._versions[agent_name].append(
        AgentConfigVersionSnapshot(
            agent_name=agent_name,
            version=current.version,
            snapshot=current.model_copy(),
        )
    )

    updated = current.model_copy(update={**updates, "updated_at": datetime.now()})
    parts = updated.version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    updated.version = ".".join(parts)

    self._configs[agent_name] = updated
    return updated
```
- **验收**: 更新后版本号+1，历史版本可查

### 步骤4: 创建 API 路由（使用独立路由文件）
- **文件**: `backend/app/gateway/routers/agent_configs.py`
- **操作**: 新建
- **内容**: 6 个端点，前缀 `/api/agent-configs`，避免与现有 `agents.py` 冲突
```python
router = APIRouter(prefix="/api/agent-configs", tags=["agent-configs"])

@router.get("/")                           # 智能体配置列表
@router.post("/")                          # 创建智能体配置
@router.put("/{agent_name}")               # 更新智能体配置
@router.delete("/{agent_name}")            # 删除智能体配置
@router.get("/{agent_name}/versions")      # 版本历史
@router.post("/{agent_name}/rollback")     # 回滚版本
```
- **验收**: API 端点可访问，不与 `/api/agents` 冲突

### 步骤5: 注册路由到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 中通过 `app.include_router()` 注册 agent_configs router
```python
from app.gateway.routers.agent_configs import router as agent_configs_router
app.include_router(agent_configs_router)
```
- **验收**: `/api/agent-configs` 路由可访问，`/api/agents` 原有功能不受影响

## 验收标准
- [ ] `AgentConfigVersion` 扩展现有 `AgentConfig`，不重复定义基础字段
- [ ] `AgentConfigManager` CRUD + 版本管理
- [ ] 更新自动保存历史版本
- [ ] 版本回滚正确
- [ ] 使用独立路由文件 `agent_configs.py`，前缀 `/api/agent-configs`
- [ ] 不覆盖现有 `agents.py` 路由（`/api/agents`）
- [ ] 路由通过 `app.include_router()` 注册到 `create_app()`
- [ ] 6 个 API 端点可访问

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | create + get | 创建后可读取 |
| 单元测试 | update 版本递增 | version 1.0.0→1.0.1 |
| 单元测试 | update 保存历史 | 历史版本可查 |
| 单元测试 | rollback | 配置恢复到指定版本 |
| 单元测试 | delete | 配置移除 |
| 集成测试 | API CRUD | 全流程正确 |
| 集成测试 | `/api/agents` 仍正常 | 原有路由不受影响 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 版本历史内存占用 | 低 | 限制最大历史版本数 |
| 并发更新冲突 | 低 | 简单互斥锁 |
| 与 `agents.py` 路由混淆 | 中 | 路由前缀明确区分，文档说明 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第9节
- `backend/app/gateway/routers/agents.py`（现有自定义智能体 CRUD）
- `deerflow/config/agents_config.py`（现有 `AgentConfig` 模型）
