# T20 - Claude Code 多会话数据模型 + SessionManager 骨架

## 元信息
- **任务ID**: T20
- **阶段**: 第3期 - 治理与协同
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: 无
- **关联差距**: 差距3 - Claude Code 多会话

## 目标
创建 Claude Code 多会话的核心数据模型和 SessionManager 骨架，实现会话的创建、消息发送、续接、暂停、恢复、终止等基本生命周期管理。

## 重要约束

> **与现有 ACP 代理的关系**：项目已有 `invoke_acp_agent_tool`（`deerflow/tools/builtins/invoke_acp_agent_tool.py`）和 `ACPAgentConfig`（`deerflow/config/acp_config.py`）。ACP 代理通过 `spawn_agent_process` 启动子进程，使用 `Client` 收集流式输出。Claude Code 会话是 ACP 代理的一种特化场景——Claude Code 本身就是通过 ACP 协议接入的外部代理。SessionManager 应**复用 ACP 通信层**（`spawn_agent_process`、`Client`、`new_session`、`prompt` 等），而非重新实现进程管理和通信协议。

> **状态类型为 `ThreadState`**（TypedDict），会话相关状态字段必须为 JSON 可序列化的 dict。

## 详细实现步骤

### 步骤1: 创建数据模型
- **文件**: `backend/packages/harness/deerflow/claude_session/models.py`
- **操作**: 新建
- **内容**: 定义以下 Pydantic 模型：
  - `SessionStatus(str, Enum)` — "idle" | "running" | "paused" | "completed" | "failed"
  - `ClaudeSession(BaseModel)`:
    - `session_id: str` — 会话唯一标识（UUID）
    - `thread_id: str` — 所属 DeerFlow 线程
    - `parent_node_id: str | None = None` — 所属 DAG 节点
    - `status: SessionStatus = SessionStatus.IDLE`
    - `working_directory: str | None = None`
    - `created_at: datetime`
    - `last_active_at: datetime`
    - `message_count: int = 0`
    - `system_prompt_suffix: str = ""`
    - `tool_permissions: list[str] = Field(default_factory=list)`
    - `error: str | None = None`
    - `timeout_seconds: int = 3600`
  - `SessionMessage(BaseModel)`:
    - `session_id: str`
    - `role: str` — "user" | "assistant" | "system"
    - `content: str`
    - `timestamp: datetime`
    - `metadata: dict = Field(default_factory=dict)`
  - `ClaudeSessionPool(BaseModel)`:
    - `thread_id: str`
    - `sessions: dict[str, ClaudeSession] = Field(default_factory=dict)`
    - `max_parallel: int = 3`
  - `SessionConfig(BaseModel)`:
    - `enabled: bool = True`
    - `max_parallel: int = 3`
    - `default_timeout: int = 3600`
    - `auto_terminate_idle: int = 1800`
    - `working_directory: str | None = None`
    - `model_config = ConfigDict(extra="allow")`
- **验收**: 所有模型 Pydantic 校验通过，序列化/反序列化正确

### 步骤2: 创建模块入口
- **文件**: `backend/packages/harness/deerflow/claude_session/__init__.py`
- **操作**: 新建
- **内容**: 导出核心模型和 Manager：
  ```python
  from deerflow.claude_session.models import SessionStatus, ClaudeSession, SessionMessage, ClaudeSessionPool, SessionConfig
  from deerflow.claude_session.manager import ClaudeSessionManager
  ```
- **验收**: 模块可正确导入

### 步骤3: 实现 ClaudeSessionManager 核心方法
- **文件**: `backend/packages/harness/deerflow/claude_session/manager.py`
- **操作**: 新建
- **内容**: 实现 `ClaudeSessionManager` 类：
  - `__init__(self, config: SessionConfig | None = None)`:
    - 初始化 `self.pools: dict[str, ClaudeSessionPool]`
    - 初始化 `self._output_streams: dict[str, asyncio.Queue]`
    - 初始化 `self._session_messages: dict[str, list[SessionMessage]]`
    - 初始化 `self._idle_timer: dict[str, asyncio.Task]`
    - `self.max_parallel = config.max_parallel if config else 3`
  - `async def create_session(...)` — 创建会话
  - `async def send_message(self, session_id: str, message: str)` — 发送消息
  - `async def continue_session(self, session_id: str, message: str)` — 续接
  - `async def terminate_session(self, session_id: str)` — 终止
  - `async def pause_session(self, session_id: str)` — 暂停
  - `async def resume_session(self, session_id: str)` — 恢复
  - `async def get_output_stream(self, session_id: str)` — 获取输出流
  - `async def get_session(self, session_id: str)` — 获取会话
  - `async def list_sessions(self, thread_id: str)` — 列出会话
  - `async def get_messages(self, session_id: str)` — 获取消息历史
  - `async def _dispatch_to_claude(self, session, message)` — 骨架：抛出 NotImplementedError，T21 实际实现
  - `async def _start_idle_monitor(self, session_id)` — 空闲超时监控
  - `async def _reset_idle_timer(self, session_id)` — 重置空闲计时器
- **验收**: 所有生命周期方法可正确修改 session 状态，并行上限检查正确

### 步骤4: 添加 claude_sessions 配置段
- **文件**: `config.example.yaml`
- **操作**: 改造
- **内容**: 新增配置段：
  ```yaml
  claude_sessions:
    enabled: true
    max_parallel: 3
    default_timeout: 3600
    auto_terminate_idle: 1800
    working_directory: null
  ```
- **验收**: 配置可被 `get_app_config()` 正确解析（`AppConfig` 有 `ConfigDict(extra="allow")`，未知键保留在 `model_extra` 中）

### 步骤5: 编写单元测试
- **文件**: `backend/tests/test_claude_session_models.py`
- **操作**: 新建
- **内容**: 测试用例：
  - ClaudeSession 模型校验（默认值、字段类型）
  - SessionMessage 序列化
  - ClaudeSessionPool 并行计数
  - SessionConfig 默认值

- **文件**: `backend/tests/test_claude_session_manager.py`
- **操作**: 新建
- **内容**: 测试用例：
  - create_session：正确创建，pool 中包含新 session
  - 并行上限：创建超过 max_parallel 个 session 时抛出 RuntimeError
  - send_message：状态变为 RUNNING，消息计数增加
  - pause_session / resume_session：状态切换正确
  - terminate_session：状态变为 COMPLETED
  - continue_session：等同于 send_message
  - list_sessions：返回正确列表
  - get_messages：返回消息历史
  - _dispatch_to_claude：骨架调用抛出 NotImplementedError
  - 边界：操作不存在的 session、暂停非 RUNNING 的 session
- **验收**: `cd backend && make test` 全部通过

## 验收标准
- [ ] SessionStatus, ClaudeSession, SessionMessage, ClaudeSessionPool, SessionConfig 模型定义完成
- [ ] ClaudeSessionManager 核心生命周期方法实现
- [ ] 并行会话数上限检查正确
- [ ] 空闲超时监控骨架实现
- [ ] `_dispatch_to_claude` 为骨架（NotImplementedError），T21 实际实现
- [ ] claude_sessions 配置段添加到 config.example.yaml
- [ ] 明确 Claude Code 会话与 ACP 代理的关系，SessionManager 将复用 ACP 通信层
- [ ] 单元测试通过，覆盖率 > 85%
- [ ] 不依赖 app.* 包（harness 边界）

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | 创建 session | session_id 非空，status=IDLE |
| 单元测试 | 创建超过 max_parallel 个 session | 抛出 RuntimeError |
| 单元测试 | send_message | status=RUNNING，message_count=1 |
| 单元测试 | pause_session | status=PAUSED |
| 单元测试 | resume_session | status=RUNNING |
| 单元测试 | terminate_session | status=COMPLETED |
| 单元测试 | continue_session | 与 send_message 行为一致 |
| 单元测试 | _dispatch_to_claude 骨架 | 抛出 NotImplementedError |
| 单元测试 | 操作不存在的 session | 抛出 KeyError |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| asyncio.Queue 在测试中需事件循环 | 中 | 使用 pytest-asyncio 和 async fixture |
| 空闲超时监控在测试中触发不可控 | 中 | 测试中 mock _start_idle_monitor |
| _dispatch_to_claude 骨架无法端到端测试 | 低 | T21 实现后补全集成测试 |
| 与 ACP 代理概念混淆 | 中 | 明确文档：Claude Code 会话是 ACP 代理的特化场景 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第3节（Claude Code 多会话）
- `deerflow/tools/builtins/invoke_acp_agent_tool.py`（现有 ACP 代理调用实现）
- `deerflow/config/acp_config.py`（`ACPAgentConfig` 定义）
