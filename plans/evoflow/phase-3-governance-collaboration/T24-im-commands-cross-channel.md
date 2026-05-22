# T24 - IM 命令跨渠道响应适配

## 元信息
- **任务ID**: T24
- **阶段**: 第3期 - 治理与协同
- **优先级**: P2
- **预估工期**: 2 天
- **依赖任务**: T23
- **关联差距**: 差距10 - IM 渠道命令对齐

## 目标
实现 IM 渠道命令路由和跨渠道响应格式适配，使同一命令在不同渠道（飞书/企业微信/钉钉/Slack/Telegram/Discord/微信）上输出适配的富文本格式。

## 重要约束

> **使用 `get_channel_service()` 获取渠道服务**（`app/channels/service.py`），而非直接使用 `get_channel_manager`。`ChannelService` 管理所有渠道的生命周期，`ChannelManager` 是其内部组件。

> **响应格式化器应与现有渠道实现兼容**。现有渠道（`FeishuChannel`、`SlackChannel` 等）通过 `MessageBus` 的 `OutboundMessage` 发送响应。格式化器应将 `CommandResult` 转换为 `OutboundMessage.text` 字段，由现有渠道发送机制处理。

## 详细实现步骤

### 步骤1: 创建命令注册表
- **文件**: `backend/app/channels/commands/__init__.py`
- **操作**: 新建
- **内容**: 实现命令注册和发现机制：
  ```python
  COMMANDS: list[BaseCommand] = [
      NewCommand(), StatusCommand(), LeadCommand(), ResumeCommand(), ClearCommand(),
      ClaudeCommand(), ClaudeListCommand(), ClaudeResumeCommand(), ClaudeTerminateCommand(),
      TaskListCommand(), TaskRetryCommand(), TaskCancelCommand(),
      ScheduleListCommand(), ScheduleCreateCommand(), SchedulePauseCommand(), ScheduleResumeCommand(), ScheduleDeleteCommand(),
      SkillListCommand(), SkillEnableCommand(), SkillDisableCommand(), SkillInstallCommand(), SkillUpdateCommand(),
      HelpCommand(),
  ]

  def get_command(name: str) -> BaseCommand | None: ...
  def get_all_commands() -> list[BaseCommand]: ...
  ```
- **验收**: `get_command("new")` 返回 NewCommand 实例

### 步骤2: 创建响应格式化器
- **文件**: `backend/app/channels/commands/formatters.py`
- **操作**: 新建
- **内容**: 实现各渠道的响应格式化器：
  - `BaseFormatter(ABC)`:
    - `format_result(result: CommandResult) -> str`
    - `format_table(headers, rows) -> str`
    - `format_code_block(code, language) -> str`
    - `format_link(text, url) -> str`
    - `format_bold(text) -> str`
    - `format_italic(text) -> str`

  - `FeishuFormatter(BaseFormatter)` — 飞书 Markdown + 卡片
  - `WeComFormatter(BaseFormatter)` — 企业微信 Markdown
  - `DingTalkFormatter(BaseFormatter)` — 钉钉 Markdown
  - `SlackFormatter(BaseFormatter)` — Slack Block Kit
  - `TelegramFormatter(BaseFormatter)` — Telegram MarkdownV2/HTML
  - `DiscordFormatter(BaseFormatter)` — Discord embed
  - `WeChatFormatter(BaseFormatter)` — 微信（纯文本）

  - `get_formatter(channel: str) -> BaseFormatter` — 工厂方法
- **验收**: 各格式化器输出对应渠道的正确格式

### 步骤3: 实现命令路由
- **文件**: `backend/app/channels/manager.py`
- **操作**: 改造
- **内容**: 在 `ChannelManager` 中添加命令路由逻辑，**使用 `get_channel_service()` 获取渠道信息**：
  ```python
  from app.channels.commands import get_command, get_all_commands
  from app.channels.commands.formatters import get_formatter
  from app.channels.commands.base import CommandResult
  from app.channels.service import get_channel_service

  class ChannelManager:
      async def _handle_command(self, msg: InboundMessage) -> None:
          text = msg.text.strip()
          parts = text.split(maxsplit=1)
          cmd_name = parts[0].lower().lstrip("/")
          args = parts[1] if len(parts) > 1 else ""

          cmd_name = self._normalize_command(cmd_name, args)
          cmd = get_command(cmd_name)

          if cmd:
              try:
                  result = await cmd.execute(msg, args)
              except Exception as e:
                  result = CommandResult(success=False, message=f"命令执行失败: {e}")
          else:
              result = CommandResult(success=False, message=f"未知命令 `/{cmd_name}`，输入 /help 查看帮助")

          formatter = get_formatter(msg.channel_name)
          formatted_text = formatter.format_result(result)

          outbound = OutboundMessage(
              channel_name=msg.channel_name,
              chat_id=msg.chat_id,
              thread_id=self.store.get_thread_id(msg.channel_name, msg.chat_id) or "",
              text=formatted_text,
              thread_ts=msg.thread_ts,
              metadata=_slim_metadata(msg.metadata),
          )
          await self.bus.publish_outbound(outbound)

      def _normalize_command(self, cmd_name: str, args: str) -> str:
          """处理复合命令名"""
          ...
  ```
- **验收**: 命令路由正确，使用 `get_channel_service()` 获取渠道信息

### 步骤4: 编写测试
- **文件**: `backend/tests/test_im_command_routing.py`
- **操作**: 新建
- **内容**: 测试用例：
  - 命令路由：`/new 测试` → NewCommand，`/help` → HelpCommand
  - 复合命令解析：`/claude list` → ClaudeListCommand
  - 未知命令：`/unknown` → 返回错误提示
  - 格式化器测试：同一 CommandResult 在不同渠道输出不同格式
  - 边界：空消息、只有 `/`
- **验收**: `cd backend && make test` 全部通过

## 验收标准
- [ ] 命令注册表实现，`get_command()` 和 `get_all_commands()` 可用
- [ ] 7个渠道的响应格式化器实现完成
- [ ] ChannelManager._handle_command 支持命令路由
- [ ] 使用 `get_channel_service()` 获取渠道信息
- [ ] 复合命令名解析正确
- [ ] 同一命令结果在不同渠道输出适配格式
- [ ] 单元测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | get_command("new") | 返回 NewCommand |
| 单元测试 | get_command("unknown") | 返回 None |
| 单元测试 | 复合命令 /claude list | 解析为 claude-list |
| 单元测试 | FeishuFormatter.format_result | 输出飞书 Markdown |
| 单元测试 | SlackFormatter.format_result | 输出 Block Kit JSON |
| 单元测试 | DiscordFormatter.format_result | 输出 embed 格式 |
| 单元测试 | WeChatFormatter.format_result | 输出纯文本 |
| 单元测试 | 未知命令路由 | 返回 CommandResult(success=False) |
| 集成测试 | ChannelManager 路由 /status | 正确路由到 StatusCommand 并格式化 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 各渠道 Markdown 语法差异导致显示异常 | 中 | 每个格式化器独立处理 |
| 飞书/钉钉卡片消息 JSON 结构复杂 | 中 | 首期使用简单 Markdown |
| 复合命令解析边界情况 | 中 | 明确文档说明命令格式 |
| 微信渠道纯文本限制体验差 | 低 | 微信端提供简化版输出 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第10节（IM 渠道命令对齐）
- `app/channels/service.py`（`get_channel_service()` 和 `ChannelService`）
- `app/channels/manager.py`（`ChannelManager` 现有命令分发）
