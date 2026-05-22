# T21 - Claude Code 会话 ACP 通信适配 + 输出流

## 元信息
- **任务ID**: T21
- **阶段**: 第3期 - 治理与协同
- **优先级**: P2
- **预估工期**: 4 天
- **依赖任务**: T20
- **关联差距**: 差距3 - Claude Code 多会话

## 目标
实现 ClaudeSessionManager 的 ACP 通信适配层和输出流机制，使 Claude Code 会话可通过 ACP 协议与 DeerFlow 编排侧进行双向通信，输出流可被 SSE 端点消费。

## 重要约束

> **必须基于现有 ACP 基础设施构建**。项目已有完整的 ACP 通信实现：
> - `invoke_acp_agent_tool`（`deerflow/tools/builtins/invoke_acp_agent_tool.py`）中使用 `spawn_agent_process`、`Client`、`new_session`、`prompt` 等
> - `ACPAgentConfig`（`deerflow/config/acp_config.py`）定义代理配置
> - `_CollectingClient` 模式：自定义 `Client` 子类收集流式输出
> - `_build_acp_mcp_servers()` 构建 MCP 服务器配置
> - `_build_permission_response()` 处理权限请求
>
> `ClaudeACPAdapter` 应复用这些模式，而非重新实现 ACP 通信协议。

## 详细实现步骤

### 步骤1: 调研现有 ACP 通信机制
- **文件**: `backend/packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py` (阅读)
- **操作**: 阅读现有代码
- **内容**: 了解现有 ACP agent 通信机制：
  - `spawn_agent_process` 启动子进程
  - `Client` 子类（如 `_CollectingClient`）收集流式输出
  - `conn.initialize()` → `conn.new_session()` → `conn.prompt()` 调用流程
  - `_build_acp_mcp_servers()` 构建 MCP 配置
  - `_build_permission_response()` 处理权限
  - `_get_work_dir()` 获取工作目录
- **验收**: 输出调研笔记，明确 ACP 通信接口

### 步骤2: 实现 ACP 通信适配器
- **文件**: `backend/packages/harness/deerflow/claude_session/acp_adapter.py`
- **操作**: 新建
- **内容**: 实现 `ClaudeACPAdapter` 类，**复用现有 ACP 通信模式**：
  ```python
  from acp import Client, PROTOCOL_VERSION, spawn_agent_process, text_block
  from acp.schema import ClientCapabilities, Implementation, TextContentBlock
  from deerflow.config.acp_config import ACPAgentConfig

  class _StreamingClient(Client):
      """流式输出收集 Client，复用 _CollectingClient 模式。"""
      def __init__(self, output_queue: asyncio.Queue):
          self._queue = output_queue
          self._chunks: list[str] = []

      async def session_update(self, session_id, update, **kwargs):
          try:
              if hasattr(update, "content") and isinstance(update.content, TextContentBlock):
                  await self._queue.put({"type": "text", "content": update.content.text, "timestamp": ...})
                  self._chunks.append(update.content.text)
          except Exception:
              pass

      async def request_permission(self, options, session_id, tool_call, **kwargs):
          return _build_permission_response(options, auto_approve=True)

  class ClaudeACPAdapter:
      """ACP 通信适配器，复用现有 ACP 基础设施。"""

      def __init__(self, agent_config: ACPAgentConfig):
          self._agent_config = agent_config
          self._connections: dict[str, tuple] = {}  # session_id → (conn, proc)

      async def create_connection(self, session: ClaudeSession) -> str: ...
      async def send_message(self, connection_id: str, message: str) -> None: ...
      async def receive_output(self, connection_id: str) -> AsyncIterator[str]: ...
      async def close_connection(self, connection_id: str) -> None: ...
      async def check_connection_health(self, connection_id: str) -> bool: ...
  ```
- **验收**: 适配器复用 `spawn_agent_process`、`Client`、`_build_acp_mcp_servers` 等现有模式

### 步骤3: 实现 _dispatch_to_claude 核心逻辑
- **文件**: `backend/packages/harness/deerflow/claude_session/manager.py`
- **操作**: 改造
- **内容**: 替换 T20 中的 NotImplementedError 骨架，实现完整的 `_dispatch_to_claude`：
  ```python
  async def _dispatch_to_claude(self, session: ClaudeSession, message: str):
      connection_id = await self._ensure_connection(session)
      await self._acp_adapter.send_message(connection_id, message)
      queue = self._output_streams[session.session_id]
      try:
          async for chunk in self._acp_adapter.receive_output(connection_id):
              await queue.put(chunk)
              session.last_active_at = datetime.now()
      except Exception as e:
          session.status = SessionStatus.FAILED
          session.error = str(e)
          await queue.put(None)
      finally:
          if session.status == SessionStatus.RUNNING:
              session.status = SessionStatus.IDLE
  ```
  同时添加：
  - `_ensure_connection(session)` — 确保会话有活跃的 ACP 连接
  - `_connection_map: dict[str, str]` — session_id → connection_id 映射
- **验收**: _dispatch_to_claude 可通过 ACP 发送消息并接收输出流

### 步骤4: 实现输出流机制
- **文件**: `backend/packages/harness/deerflow/claude_session/manager.py`
- **操作**: 改造
- **内容**: 增强输出流相关功能：
  - `async def stream_output(self, session_id: str) -> AsyncIterator[dict]` — 结构化输出流迭代器：
    - 从 asyncio.Queue 读取
    - 封装为结构化 dict：`{"type": "text"|"error"|"tool_use"|"end", "content": ..., "timestamp": ...}`
    - 检测 None 终止信号
  - 输出流缓冲：最近 N 条输出保留在缓冲区中
- **验收**: stream_output 可作为 SSE 事件生成器的数据源

### 步骤5: 实现会话生命周期管理
- **文件**: `backend/packages/harness/deerflow/claude_session/manager.py`
- **操作**: 改造
- **内容**: 实现自动化的会话生命周期管理：
  - 空闲自动终止：`_start_idle_monitor`
  - 超时处理
  - ACP 连接健康检查
  - 资源清理：terminate 时关闭 ACP 连接、取消后台任务、清理输出流
- **验收**: 空闲超时、连接断开等场景下会话状态正确转换

### 步骤6: 编写集成测试
- **文件**: `backend/tests/test_claude_session.py`
- **操作**: 新建
- **内容**: 使用 mock ACP adapter 的集成测试：
  - 创建会话 → 发送消息 → 接收输出流 → 验证输出内容
  - 多会话并行
  - 会话续接
  - 空闲超时
  - 连接断开
  - 终止会话
  - stream_output 结构化输出格式
- **验收**: `cd backend && make test` 全部通过

## 验收标准
- [ ] `ClaudeACPAdapter` 复用现有 ACP 基础设施（`spawn_agent_process`、`Client`、`_build_acp_mcp_servers`）
- [ ] `_dispatch_to_claude` 通过 ACP 发送消息并接收输出流
- [ ] 输出流机制：asyncio.Queue + stream_output 异步迭代器
- [ ] 结构化输出：`{type, content, timestamp}` 格式
- [ ] 会话生命周期：空闲自动终止、超时处理、连接健康检查
- [ ] 资源清理：terminate 时正确关闭连接和清理任务
- [ ] 集成测试通过（mock ACP adapter）
- [ ] 不依赖 app.* 包（harness 边界）

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 集成测试 | 创建会话→发送消息→接收输出 | 输出流包含正确内容 |
| 集成测试 | 多会话并行（3个） | 各会话输出互不混淆 |
| 集成测试 | 会话续接 | 第二条消息的响应包含上下文 |
| 集成测试 | 空闲超时 | session 自动终止 |
| 集成测试 | ACP 连接异常 | session status=FAILED |
| 集成测试 | terminate_session | 输出流收到终止信号 |
| 集成测试 | stream_output 迭代 | 返回结构化 {type, content, timestamp} |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| ACP 协议与现有子代理通信不一致 | 低 | 复用现有 `_CollectingClient` 模式和 `spawn_agent_process` |
| ACP 连接建立慢 | 低 | 异步建立连接，先返回 session_id |
| 输出流消费者（SSE）断开后数据丢失 | 中 | 实现缓冲区保留最近 N 条输出 |
| 多会话并行资源消耗 | 中 | 限制 max_parallel，空闲会话及时清理 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第3节（Claude Code 多会话）
- `deerflow/tools/builtins/invoke_acp_agent_tool.py`（现有 ACP 通信实现：`spawn_agent_process`、`_CollectingClient`、`_build_acp_mcp_servers`）
- `deerflow/config/acp_config.py`（`ACPAgentConfig` 定义）
