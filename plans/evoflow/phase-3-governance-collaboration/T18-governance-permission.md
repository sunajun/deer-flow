# T18 - 权限治理 + API

## 元信息
- **任务ID**: T18
- **阶段**: 第3期 - 治理与协同
- **优先级**: P3
- **预估工期**: 2 天
- **依赖任务**: T16
- **关联差距**: 差距9 - 统一治理面

## 目标
实现基于角色的权限治理系统，控制智能体可用的场景和工具，提供权限中间件和 API 端点。

## 重要约束

> **权限中间件必须继承 `AgentMiddleware[StateType]`**，使用标准 hooks（`wrap_tool_call`/`awrap_tool_call`）。参考现有 `ClarificationMiddleware(AgentMiddleware[ClarificationMiddlewareState])` 的实现模式。

> **状态类型为 `ThreadState`**（`deerflow/agents/thread_state.py`），是 `AgentState` 的 TypedDict 子类。中间件状态字段必须为 JSON 可序列化的 dict。

## 详细实现步骤

### 步骤1: 定义权限数据模型
- **文件**: `backend/packages/harness/deerflow/governance/models.py`
- **操作**: 新建
- **内容**: 定义以下 Pydantic 模型：
  - `RoleType(str, Enum)` — "admin" | "user" | "guest"
  - `PermissionRule(BaseModel)`:
    - `allowed_scenes: list[str]` — 允许的场景（通配符 "*" 表示全部）
    - `allowed_tools: list[str]` — 允许的工具（支持通配符 "*" 和排除前缀 "!"，如 `["*", "!agent_manage"]`）
    - `max_parallel_sessions: int = 1` — 最大并行会话数
    - `can_create_agents: bool = False` — 是否可创建智能体
    - `can_manage_skills: bool = False` — 是否可管理技能
    - `can_schedule_tasks: bool = False` — 是否可创建定时任务
  - `Role(BaseModel)`:
    - `role_type: RoleType`
    - `name: str` — 显示名称
    - `description: str`
    - `permissions: PermissionRule`
    - `created_at: datetime`
    - `updated_at: datetime`
  - `GovernanceConfig(BaseModel)`:
    - `enabled: bool = True`
    - `default_role: RoleType = RoleType.USER`
    - `roles: dict[RoleType, Role] = Field(default_factory=dict)` — 角色配置映射
    - `model_config = ConfigDict(extra="allow")`
- **验收**: 模型定义完整，Pydantic 校验通过

### 步骤2: 实现内置角色预设
- **文件**: `backend/packages/harness/deerflow/governance/presets.py`
- **操作**: 新建
- **内容**: 定义内置角色预设：
  ```python
  BUILTIN_ROLES = {
      RoleType.ADMIN: Role(
          role_type=RoleType.ADMIN,
          name="管理员",
          description="完全控制权限",
          permissions=PermissionRule(
              allowed_scenes=["*"],
              allowed_tools=["*"],
              max_parallel_sessions=10,
              can_create_agents=True,
              can_manage_skills=True,
              can_schedule_tasks=True,
          ),
      ),
      RoleType.USER: Role(
          role_type=RoleType.USER,
          name="普通用户",
          description="日常使用权限",
          permissions=PermissionRule(
              allowed_scenes=["conversation", "planning", "file_operation"],
              allowed_tools=["*", "!agent_manage", "!skill_manage"],
              max_parallel_sessions=3,
              can_create_agents=False,
              can_manage_skills=False,
              can_schedule_tasks=True,
          ),
      ),
      RoleType.GUEST: Role(
          role_type=RoleType.GUEST,
          name="访客",
          description="只读对话权限",
          permissions=PermissionRule(
              allowed_scenes=["conversation"],
              allowed_tools=["chat", "clarify"],
              max_parallel_sessions=1,
              can_create_agents=False,
              can_manage_skills=False,
              can_schedule_tasks=False,
          ),
      ),
  }
  ```
- **验收**: 预设角色定义完整，权限级别递减

### 步骤3: 实现权限中间件
- **文件**: `backend/packages/harness/deerflow/governance/middleware.py`
- **操作**: 新建
- **内容**: 实现 `PermissionMiddleware` 类，**继承 `AgentMiddleware[ThreadState]`**：
  ```python
  from langchain.agents.middleware import AgentMiddleware
  from langchain.prebuilt.tool_node import ToolCallRequest
  from langchain_core.messages import ToolMessage
  from langgraph.types import Command
  from deerflow.agents.thread_state import ThreadState

  class PermissionMiddlewareState(ThreadState):
      """兼容 ThreadState 的权限中间件状态。"""
      pass

  class PermissionMiddleware(AgentMiddleware[PermissionMiddlewareState]):
      """权限治理中间件，拦截工具调用并检查权限。"""
      state_schema = PermissionMiddlewareState

      def __init__(self, config: GovernanceConfig):
          self._config = config

      def resolve_permissions(self, user_role: RoleType) -> PermissionRule: ...
      def check_scene_access(self, user_role: RoleType, scene: str) -> bool: ...
      def check_tool_access(self, user_role: RoleType, tool: str) -> bool: ...

      def wrap_tool_call(self, request, handler):
          """同步拦截工具调用，检查权限。"""
          tool_name = request.tool_call.get("name", "")
          user_role = self._get_role_from_state(request)
          if not self.check_tool_access(user_role, tool_name):
              return ToolMessage(
                  content=f"权限不足：角色 '{user_role.value}' 无权使用工具 '{tool_name}'",
                  tool_call_id=request.tool_call.get("id", ""),
                  name=tool_name,
              )
          return handler(request)

      async def awrap_tool_call(self, request, handler):
          """异步拦截工具调用，检查权限。"""
          tool_name = request.tool_call.get("name", "")
          user_role = self._get_role_from_state(request)
          if not self.check_tool_access(user_role, tool_name):
              return ToolMessage(
                  content=f"权限不足：角色 '{user_role.value}' 无权使用工具 '{tool_name}'",
                  tool_call_id=request.tool_call.get("id", ""),
                  name=tool_name,
              )
          return await handler(request)

      def get_allowed_tools(self, user_role: RoleType) -> set[str]: ...
  ```
- **验收**: 中间件正确继承 `AgentMiddleware[ThreadState]`，使用标准 hooks 拦截工具调用

### 步骤4: 添加 governance 配置段到 config.yaml
- **文件**: `config.example.yaml`
- **操作**: 改造
- **内容**: 新增 governance 配置段：
  ```yaml
  governance:
    enabled: true
    default_role: user
    user_roles:
      admin:
        allowed_scenes: ["*"]
        allowed_tools: ["*"]
        max_parallel_sessions: 10
        can_create_agents: true
        can_manage_skills: true
        can_schedule_tasks: true
      user:
        allowed_scenes: ["conversation", "planning", "file_operation"]
        allowed_tools: ["*", "!agent_manage", "!skill_manage"]
        max_parallel_sessions: 3
        can_create_agents: false
        can_manage_skills: false
        can_schedule_tasks: true
      guest:
        allowed_scenes: ["conversation"]
        allowed_tools: ["chat", "clarify"]
        max_parallel_sessions: 1
        can_create_agents: false
        can_manage_skills: false
        can_schedule_tasks: false
  ```
- **验收**: 配置段格式正确，可被 `get_app_config()` 正确解析（`AppConfig` 已有 `ConfigDict(extra="allow")`，未知键会保留在 `model_extra` 中）

### 步骤5: 创建权限管理 API
- **文件**: `backend/app/gateway/routers/governance.py`
- **操作**: 新建
- **内容**: 实现以下端点：
  - `GET /api/governance/roles` — 获取所有角色及其权限配置
  - `PUT /api/governance/roles/{role}` — 更新角色权限，请求体为 `PermissionRule`
  - `GET /api/governance/permissions?user_id=xxx` — 查询指定用户的权限
  - `POST /api/governance/check-access` — 检查权限，请求体 `{role, resource_type, resource_id}`
- **验收**: API 端点可用

### 步骤6: 注册路由到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 中通过 `app.include_router()` 注册 governance router
- **验收**: `/api/governance/roles` 可访问

### 步骤7: 编写测试
- **文件**: `backend/tests/test_governance.py`
- **操作**: 新建
- **内容**: 测试用例：
  - 角色权限解析：admin 全部放行、guest 仅 chat/clarify
  - 通配符处理：`["*"]` 放行所有、`["*", "!agent_manage"]` 排除特定工具
  - 场景访问检查：user 可访问 conversation 但不可访问 governance
  - 工具访问检查：guest 调用 bash 被拒绝
  - 中间件拦截：`wrap_tool_call`/`awrap_tool_call` 正确拒绝/放行
  - API 端点测试
- **验收**: `cd backend && make test` 全部通过

## 验收标准
- [ ] 权限数据模型定义完成，支持 3 种内置角色
- [ ] `PermissionMiddleware` 继承 `AgentMiddleware[ThreadState]`，使用标准 hooks
- [ ] 通配符 "*" 和排除前缀 "!" 规则正确处理
- [ ] governance 配置段添加到 config.example.yaml
- [ ] API 端点可用，权限查询和检查正确
- [ ] 单元测试通过
- [ ] 不依赖 app.* 包（harness 边界内）

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | admin 角色检查任意工具 | 全部放行 |
| 单元测试 | guest 角色检查 "bash" 工具 | 拒绝 |
| 单元测试 | user 角色检查 "agent_manage" | 拒绝（排除规则） |
| 单元测试 | user 角色检查 "chat" | 放行 |
| 单元测试 | 通配符 `["*"]` + 任意工具 | 放行 |
| 单元测试 | `["*", "!agent_manage"]` + agent_manage | 拒绝 |
| 单元测试 | PermissionMiddleware.wrap_tool_call | 正确拦截/放行 |
| 单元测试 | PermissionMiddleware.awrap_tool_call | 正确拦截/放行 |
| API 测试 | GET /api/governance/roles | 200，返回3种角色 |
| API 测试 | PUT /api/governance/roles/user | 200，权限更新生效 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 权限规则与场景系统重叠 | 中 | 明确分工：场景过滤工具集，权限过滤工具+场景访问 |
| 用户-角色映射缺失（无认证模式） | 高 | 无认证模式默认使用 default_role（user），admin 通过 config 配置 |
| 权限变更需要重启 | 低 | governance 配置在热重载边界内，修改后下条消息生效 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第9节（统一治理面）
- `deerflow/agents/middlewares/clarification_middleware.py`（`AgentMiddleware[StateType]` 参考实现）
- `deerflow/agents/thread_state.py`（`ThreadState` 定义）
