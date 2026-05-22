# T22 - Claude Code 会话 LangGraph 工具 + API + 测试

## 元信息
- **任务ID**: T22
- **阶段**: 第3期 - 治理与协同
- **优先级**: P3
- **预估工期**: 3 天
- **依赖任务**: T20, T21
- **关联差距**: 差距3 - Claude Code 多会话

## 目标
将 Claude Code 多会话能力暴露为 LangGraph 工具和 REST API 端点，使 lead_agent 和外部客户端均可调度 Claude Code 会话，并提供 SSE 流式输出端点。

## 重要约束

> **SSE 流必须处理客户端断开清理**：当客户端断开 SSE 连接时，服务端必须检测并清理相关资源（取消输出流消费任务、释放 asyncio.Queue 引用等），避免资源泄漏。

> **路由注册必须在 `create_app()` 中通过 `app.include_router()` 完成**，不使用 `@app.on_event`（Gateway 使用 `lifespan` 上下文管理器）。

## 详细实现步骤

### 步骤1: 创建 LangGraph 工具
- **文件**: `backend/packages/harness/deerflow/tools/claude_session_tools.py`
- **操作**: 新建
- **内容**: 实现三个 LangGraph 工具：
  - `claude_code_task`:
    ```python
    @tool
    async def claude_code_task(
        task_description: str,
        session_id: str | None = None,
        working_directory: str | None = None,
    ) -> str:
        """委派任务给 Claude Code。"""
        manager = get_claude_session_manager()
        if session_id is None:
            session = await manager.create_session(
                thread_id=_current_thread_id(),
                working_directory=working_directory,
            )
            session_id = session.session_id
        else:
            session = await manager.get_session(session_id)
        await manager.send_message(session_id, task_description)
        result_parts = []
        async for chunk in manager.stream_output(session_id):
            if chunk["type"] == "text":
                result_parts.append(chunk["content"])
            elif chunk["type"] == "end":
                break
        return f"Session {session_id}: {''.join(result_parts)[:2000]}"
    ```
  - `list_claude_sessions`
  - `terminate_claude_session`
  - 辅助函数 `_current_thread_id()` — 从 LangGraph state 获取当前 thread_id
  - 辅助函数 `get_claude_session_manager()` — 获取单例 SessionManager
- **验收**: 工具可在 LangGraph 图中被 lead_agent 调用

### 步骤2: 注册工具到工具装配
- **文件**: `backend/packages/harness/deerflow/tools/__init__.py`
- **操作**: 改造
- **内容**: 在工具装配逻辑中注册 claude_session_tools：
  - 当 `claude_sessions.enabled=True` 时，将工具加入可用工具列表
- **验收**: 配置启用后工具在可用列表中

### 步骤3: 创建 API 路由
- **文件**: `backend/app/gateway/routers/claude_sessions.py`
- **操作**: 新建
- **内容**: 实现 FastAPI 路由：
  - `POST /api/claude-sessions` — 创建会话
  - `GET /api/claude-sessions` — 列出会话
  - `GET /api/claude-sessions/{session_id}` — 获取详情
  - `POST /api/claude-sessions/{session_id}/send` — 发送消息
  - `POST /api/claude-sessions/{session_id}/pause` — 暂停
  - `POST /api/claude-sessions/{session_id}/resume` — 恢复
  - `DELETE /api/claude-sessions/{session_id}` — 终止
  - `GET /api/claude-sessions/{session_id}/stream` — SSE 流式输出端点：
    ```python
    @router.get("/{session_id}/stream")
    async def stream_session_output(session_id: str, request: Request):
        manager = get_claude_session_manager()
        async def event_generator():
            try:
                async for chunk in manager.stream_output(session_id):
                    if await request.is_disconnected():
                        break
                    if chunk["type"] == "end":
                        yield {"event": "claude_end", "data": json.dumps({"session_id": session_id})}
                        break
                    yield {"event": f"claude_{chunk['type']}", "data": json.dumps(chunk)}
            finally:
                pass  # 清理资源
        return EventSourceResponse(event_generator())
    ```
  - `GET /api/claude-sessions/{session_id}/messages` — 获取消息历史
- **验收**: 所有端点功能正确，SSE 流可被 EventSource 消费，客户端断开时正确清理

### 步骤4: 注册路由到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 中通过 `app.include_router()` 注册 claude_sessions router：
  ```python
  from app.gateway.routers.claude_sessions import router as claude_sessions_router
  app.include_router(claude_sessions_router)
  ```
- **验收**: Gateway 启动后 `/api/claude-sessions` 路由可访问

### 步骤5: 集成 ClaudeSessionMiddleware
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/claude_session_middleware.py`
- **操作**: 新建
- **内容**: 实现 `ClaudeSessionMiddleware(AgentMiddleware[ClaudeSessionMiddlewareState])`：
  - 拦截 `claude_code_task` 工具调用，注入当前 thread_id
  - 检查并行会话数限制
  - 检查权限（是否允许使用 Claude Code 会话）
- **验收**: 中间件正确注入上下文和权限检查

### 步骤6: 编写 E2E 测试
- **文件**: `backend/tests/test_claude_session_e2e.py`
- **操作**: 新建
- **内容**: 端到端测试（使用 mock ACP adapter）：
  - 多会话并行派发
  - 结果汇总
  - 会话续接
  - SSE 流消费（含客户端断开测试）
  - 会话终止
  - 并行上限
  - API 全链路
- **验收**: E2E 测试全部通过

## 验收标准
- [ ] claude_code_task, list_claude_sessions, terminate_claude_session 工具实现完成
- [ ] 工具注册到工具装配，配置控制启用/禁用
- [ ] API 端点全部可用（8个端点）
- [ ] SSE 流式输出端点可正确推送 Claude Code 输出
- [ ] SSE 端点处理客户端断开清理（`request.is_disconnected()`）
- [ ] 路由通过 `app.include_router()` 注册到 `create_app()`
- [ ] ClaudeSessionMiddleware 正确注入上下文和权限检查
- [ ] E2E 测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | claude_code_task 工具调用 | 返回 session_id 和结果摘要 |
| 单元测试 | list_claude_sessions 工具 | 返回格式化的会话列表 |
| 单元测试 | terminate_claude_session 工具 | 返回终止确认 |
| API 测试 | POST /api/claude-sessions | 201，返回 session_id |
| API 测试 | GET /api/claude-sessions/{id}/stream SSE | 返回 EventSourceResponse |
| API 测试 | SSE 客户端断开 | 服务端检测并清理资源 |
| E2E 测试 | 3会话并行派发+结果汇总 | 各会话独立返回 |
| E2E 测试 | 会话续接 | 上下文延续 |
| E2E 测试 | 并行上限 | 超过 max_parallel 时拒绝 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| SSE 连接长时间保持占用资源 | 中 | 设置心跳间隔，客户端断开时检测并清理 |
| 工具中获取 thread_id 依赖 state 注入 | 中 | 通过 LangGraph state 传递 |
| SSE 客户端断开未清理 | 中 | 使用 `request.is_disconnected()` 检测，在 finally 中清理 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第3节（Claude Code 多会话）
- `backend/app/gateway/app.py`（`create_app()` 和 `app.include_router()` 模式）
