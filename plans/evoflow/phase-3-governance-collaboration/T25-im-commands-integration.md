# T25 - IM 命令集成测试 + E2E 验证

## 元信息
- **任务ID**: T25
- **阶段**: 第3期 - 治理与协同
- **优先级**: P4
- **预估工期**: 2 天
- **依赖任务**: T23, T24
- **关联差距**: 差距10 - IM 渠道命令对齐

## 目标
对 IM 命令系统进行全面的集成测试和端到端验证，确保命令从渠道消息输入到格式化响应输出的完整链路正确，验证命令通过 `ChannelManager` 调度的端到端流程。

## 重要约束

> **集成测试应验证命令通过 `ChannelManager` 调度的完整流程**。`ChannelManager._handle_command()` 是命令分发的核心入口，测试应覆盖从消息接收到响应发送的完整链路，而非仅测试单个命令的 execute 方法。

> 使用 `get_channel_service()` 获取渠道服务实例进行测试。

## 详细实现步骤

### 步骤1: 搭建测试基础设施
- **文件**: `backend/tests/conftest.py`
- **操作**: 改造（添加 IM 命令测试 fixtures）
- **内容**: 添加以下 pytest fixtures：
  - `mock_channel_service` — mock `ChannelService`，包含 mock `ChannelManager` 和 `MessageBus`
  - `mock_message_bus` — mock `MessageBus`，记录 `publish_outbound` 调用
  - `sample_inbound_message` — 构造测试用 `InboundMessage`
  - `all_commands` — 加载所有注册命令
  - `all_formatters` — 加载所有格式化器
- **验收**: fixtures 可正确创建和使用

### 步骤2: 编写命令路由集成测试
- **文件**: `backend/tests/test_im_command_integration.py`
- **操作**: 新建
- **内容**: 测试命令通过 `ChannelManager` 调度的完整流程：
  - 测试所有23个命令的路由正确性：
    - 对话管理：/new, /status, /lead, /resume, /clear
    - Claude Code：/claude, /claude-list, /claude-resume, /claude-terminate
    - 任务管理：/task-list, /task-retry, /task-cancel
    - 定时任务：/schedule-list, /schedule-create, /schedule-pause, /schedule-resume, /schedule-delete
    - 技能管理：/skill-list, /skill-enable, /skill-disable, /skill-install, /skill-update
    - 帮助：/help
  - 测试命令别名路由：/n → NewCommand, /s → StatusCommand, /cl → ClaudeListCommand
  - 测试复合命令路由：/claude list → ClaudeListCommand
  - 测试未知命令路由：返回错误提示
  - 测试命令执行异常处理：命令抛出异常时返回 CommandResult(success=False)
  - 验证 `OutboundMessage` 正确发布到 `MessageBus`
- **验收**: 所有命令路由测试通过，`ChannelManager` 调度链路正确

### 步骤3: 编写跨渠道格式化集成测试
- **文件**: `backend/tests/test_im_cross_channel_integration.py`
- **操作**: 新建
- **内容**: 测试同一命令在不同渠道的响应格式：
  - `/status` 命令在飞书/企业微信/钉钉/Slack/Telegram/Discord/微信的输出格式
  - `/help` 命令在各渠道的帮助信息格式
  - `/task-list` 表格数据在各渠道的格式化
  - `/claude` 结果在各渠道的代码块格式化
  - 验证 `OutboundMessage.text` 字段内容符合各渠道格式要求
- **验收**: 各渠道格式化输出正确

### 步骤4: 编写端到端测试
- **文件**: `backend/tests/test_im_e2e.py`
- **操作**: 新建
- **内容**: 端到端测试，模拟完整消息流：
  - 消息接收 → 命令解析 → 命令执行 → 格式化 → 响应发送
  - 测试场景：
    1. 飞书渠道发送 `/new 测试对话` → 创建新对话 → 飞书格式响应
    2. Slack 渠道发送 `/claude 写一个函数` → 创建 Claude 会话 → Slack 格式响应
    3. 企业微信发送 `/task-list` → 获取任务列表 → 企业微信格式响应
    4. 钉钉发送 `/schedule-create "0 9 * * 1-5" "每日站会"` → 创建定时任务 → 钉钉格式响应
    5. Telegram 发送 `/skill-install search-skill` → 安装技能 → Telegram 格式响应
    6. Discord 发送 `/help` → 帮助信息 → Discord 格式响应
  - 验证 `MessageBus.publish_outbound` 被正确调用
  - 验证 `OutboundMessage` 的 channel_name、chat_id、text 字段正确
- **验收**: E2E 测试全部通过

### 步骤5: 编写边界和异常测试
- **文件**: `backend/tests/test_im_edge_cases.py`
- **操作**: 新建
- **内容**: 边界和异常场景测试：
  - 空消息处理
  - 只有 `/` 的消息
  - 命令参数缺失
  - 命令参数格式错误
  - 命令执行超时
  - 命令依赖的 API 不可用
  - 格式化器对特殊字符的处理（Markdown 转义、emoji 等）
  - 并发命令执行
  - 长消息截断
- **验收**: 边界和异常场景正确处理

### 步骤6: 编写性能测试
- **文件**: `backend/tests/test_im_performance.py`
- **操作**: 新建
- **内容**: 性能基准测试：
  - 命令路由延迟：< 10ms（不含 API 调用）
  - 格式化延迟：< 5ms
  - 完整链路延迟（mock API）：< 50ms
  - 并发100条命令处理
- **验收**: 性能指标达标

## 验收标准
- [ ] 测试基础设施（fixtures）搭建完成
- [ ] 23个命令的路由集成测试通过
- [ ] 命令别名和复合命令路由测试通过
- [ ] 7个渠道的格式化集成测试通过
- [ ] E2E 测试：6个场景全部通过
- [ ] 边界和异常测试通过
- [ ] 性能基准测试达标
- [ ] 集成测试验证命令通过 `ChannelManager` 调度的完整链路

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 集成测试 | ChannelManager 路由 /new | OutboundMessage 正确发布 |
| 集成测试 | ChannelManager 路由 /claude | OutboundMessage 正确发布 |
| 集成测试 | 别名 /n → NewCommand | 路由正确 |
| 集成测试 | 复合命令 /claude list | 路由到 ClaudeListCommand |
| 集成测试 | 未知命令 /unknown | 返回错误提示 |
| 集成测试 | 命令执行异常 | 返回 CommandResult(success=False) |
| 集成测试 | 飞书渠道 /status 格式化 | 输出飞书 Markdown |
| 集成测试 | Slack 渠道 /help 格式化 | 输出 Block Kit |
| E2E 测试 | 飞书→/new→响应 | 完整链路正确 |
| E2E 测试 | Slack→/claude→响应 | 完整链路正确 |
| E2E 测试 | 企业微信→/task-list→响应 | 完整链路正确 |
| 边界测试 | 空消息 | 不崩溃，返回提示 |
| 边界测试 | 命令参数缺失 | 返回用法提示 |
| 性能测试 | 命令路由延迟 | < 10ms |
| 性能测试 | 并发100条命令 | 全部正确处理 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| mock ChannelService 设置复杂 | 中 | 使用 conftest.py 共享 fixtures |
| E2E 测试依赖 mock API 响应 | 高 | 使用 respx 或 httpx mock |
| 格式化器输出难以断言 | 中 | 使用快照测试或正则匹配关键结构 |
| 性能测试不稳定 | 低 | 多次运行取中位数 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第10节（IM 渠道命令对齐）
- `app/channels/manager.py`（`ChannelManager._handle_command` 命令分发）
- `app/channels/service.py`（`get_channel_service()` 和 `ChannelService`）
