# T23 - IM 命令基类 + 核心命令实现

## 元信息
- **任务ID**: T23
- **阶段**: 第3期 - 治理与协同
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: 无
- **关联差距**: 差距10 - IM 渠道命令对齐

## 目标
实现 IM 渠道命令系统的基类和全部核心命令，覆盖对话管理、Claude Code 集成、任务管理、定时任务管理、技能管理和帮助命令，为跨渠道命令路由提供基础。

## 重要约束

> **新命令必须扩展 `KNOWN_CHANNEL_COMMANDS`**（`app/channels/commands.py` 中的 `frozenset`）。当前已有命令：`/bootstrap`、`/new`、`/status`、`/models`、`/memory`、`/help`。新增命令需要将命令名添加到此集合中，确保渠道解析器和 `ChannelManager` 调度器保持同步。

> **命令应注册到现有 `ChannelManager` 调度逻辑**中。`ChannelManager._handle_command()`（`app/channels/manager.py`）当前通过 if-elif 链处理命令。新命令应重构为可扩展的命令注册/分发机制。

## 详细实现步骤

### 步骤1: 创建命令基类
- **文件**: `backend/app/channels/commands/base.py`
- **操作**: 新建
- **内容**: 定义 `BaseCommand` 抽象基类：
  ```python
  from abc import ABC, abstractmethod
  from pydantic import BaseModel

  class CommandResult(BaseModel):
      success: bool
      message: str
      data: dict | None = None
      format_hint: str = "markdown"

  class BaseCommand(ABC):
      name: str
      aliases: list[str]
      description: str
      usage: str

      @abstractmethod
      async def execute(self, message: dict, args: str) -> CommandResult: ...

      def match(self, cmd_name: str) -> bool:
          return cmd_name == self.name or cmd_name in self.aliases

      def get_help(self) -> str:
          return f"`/{self.name}` — {self.description}\n用法: {self.usage}"
  ```
- **验收**: 基类定义完整，子类可正确继承

### 步骤2: 实现对话管理命令
- **文件**: `backend/app/channels/commands/conversation.py`
- **操作**: 新建
- **内容**: 实现以下命令类：
  - `NewCommand(BaseCommand)`: name="new", aliases=["n"]
  - `StatusCommand(BaseCommand)`: name="status", aliases=["s"]
  - `LeadCommand(BaseCommand)`: name="lead", aliases=[]
  - `ResumeCommand(BaseCommand)`: name="resume", aliases=["r"]
  - `ClearCommand(BaseCommand)`: name="clear", aliases=[]
- **验收**: 5个对话管理命令实现完成

### 步骤3: 实现 Claude Code 集成命令
- **文件**: `backend/app/channels/commands/claude.py`
- **操作**: 新建
- **内容**: 实现以下命令类：
  - `ClaudeCommand(BaseCommand)`: name="claude", aliases=[]
  - `ClaudeListCommand(BaseCommand)`: name="claude-list", aliases=["cl"]
  - `ClaudeResumeCommand(BaseCommand)`: name="claude-resume", aliases=["cr"]
  - `ClaudeTerminateCommand(BaseCommand)`: name="claude-terminate", aliases=["ct"]
- **验收**: 4个 Claude Code 命令实现完成

### 步骤4: 实现任务管理命令
- **文件**: `backend/app/channels/commands/task.py`
- **操作**: 新建
- **内容**: 实现以下命令类：
  - `TaskListCommand(BaseCommand)`: name="task-list", aliases=["tl"]
  - `TaskRetryCommand(BaseCommand)`: name="task-retry", aliases=["tr"]
  - `TaskCancelCommand(BaseCommand)`: name="task-cancel", aliases=["tc"]
- **验收**: 3个任务管理命令实现完成

### 步骤5: 实现定时任务管理命令
- **文件**: `backend/app/channels/commands/schedule.py`
- **操作**: 新建
- **内容**: 实现以下命令类：
  - `ScheduleListCommand(BaseCommand)`: name="schedule-list", aliases=["sl"]
  - `ScheduleCreateCommand(BaseCommand)`: name="schedule-create", aliases=["sc"]
  - `SchedulePauseCommand(BaseCommand)`: name="schedule-pause", aliases=["sp"]
  - `ScheduleResumeCommand(BaseCommand)`: name="schedule-resume", aliases=["sr"]
  - `ScheduleDeleteCommand(BaseCommand)`: name="schedule-delete", aliases=["sd"]
- **验收**: 5个定时任务命令实现完成

### 步骤6: 实现技能管理命令
- **文件**: `backend/app/channels/commands/skill.py`
- **操作**: 新建
- **内容**: 实现以下命令类：
  - `SkillListCommand(BaseCommand)`: name="skill-list", aliases=["skl"]
  - `SkillEnableCommand(BaseCommand)`: name="skill-enable", aliases=["ske"]
  - `SkillDisableCommand(BaseCommand)`: name="skill-disable", aliases=["skd"]
  - `SkillInstallCommand(BaseCommand)`: name="skill-install", aliases=["ski"]
  - `SkillUpdateCommand(BaseCommand)`: name="skill-update", aliases=["sku"]
- **验收**: 5个技能管理命令实现完成

### 步骤7: 实现帮助命令
- **文件**: `backend/app/channels/commands/help.py`
- **操作**: 新建
- **内容**: 实现 `HelpCommand(BaseCommand)`：name="help", aliases=["h", "?"]
- **验收**: 帮助信息分类清晰

### 步骤8: 扩展 KNOWN_CHANNEL_COMMANDS
- **文件**: `backend/app/channels/commands.py`
- **操作**: 改造
- **内容**: 将所有新命令添加到 `KNOWN_CHANNEL_COMMANDS` frozenset：
  ```python
  KNOWN_CHANNEL_COMMANDS: frozenset[str] = frozenset(
      {
          "/bootstrap",
          "/new",
          "/status",
          "/models",
          "/memory",
          "/help",
          "/lead",
          "/resume",
          "/clear",
          "/claude",
          "/claude-list",
          "/claude-resume",
          "/claude-terminate",
          "/task-list",
          "/task-retry",
          "/task-cancel",
          "/schedule-list",
          "/schedule-create",
          "/schedule-pause",
          "/schedule-resume",
          "/schedule-delete",
          "/skill-list",
          "/skill-enable",
          "/skill-disable",
          "/skill-install",
          "/skill-update",
      }
  )
  ```
- **验收**: `KNOWN_CHANNEL_COMMANDS` 包含所有新命令

### 步骤9: 编写单元测试
- **文件**: `backend/tests/test_im_commands.py`
- **操作**: 新建
- **内容**: 测试用例：
  - BaseCommand.match 测试
  - 各命令 execute 方法测试（mock API 调用）
  - 参数解析测试
  - HelpCommand 输出格式测试
  - 命令别名匹配测试
  - 错误处理测试
- **验收**: `cd backend && make test` 全部通过

## 验收标准
- [ ] BaseCommand 基类定义完整，含 CommandResult 模型
- [ ] 对话管理命令：new/status/lead/resume/clear (5个)
- [ ] Claude Code 命令：claude/claude-list/claude-resume/claude-terminate (4个)
- [ ] 任务管理命令：task-list/task-retry/task-cancel (3个)
- [ ] 定时任务命令：schedule-list/create/pause/resume/delete (5个)
- [ ] 技能管理命令：skill-list/enable/disable/install/update (5个)
- [ ] 帮助命令：help (1个)
- [ ] `KNOWN_CHANNEL_COMMANDS` 扩展包含所有新命令
- [ ] 共23个命令全部实现，单元测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | NewCommand.execute | 返回 CommandResult(success=True) |
| 单元测试 | ClaudeCommand.execute（新建会话） | 创建新 Claude 会话 |
| 单元测试 | ClaudeCommand.execute（续接） | 使用指定 session_id 续接 |
| 单元测试 | TaskListCommand.execute | 返回格式化的任务列表 |
| 单元测试 | ScheduleCreateCommand.execute | 解析 cron+prompt，创建定时任务 |
| 单元测试 | SkillInstallCommand.execute | 解析 ID+版本，安装技能 |
| 单元测试 | HelpCommand.execute | 返回分类帮助信息 |
| 单元测试 | 别名匹配："/n" → NewCommand | match 返回 True |
| 单元测试 | 无效参数处理 | 返回 CommandResult(success=False) |
| 单元测试 | KNOWN_CHANNEL_COMMANDS 包含新命令 | frozenset 包含所有命令 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 命令参数解析复杂 | 中 | 使用正则或分步解析，覆盖边界情况 |
| 依赖的 API 尚未实现 | 高 | 命令中 API 调用使用接口抽象，测试中 mock |
| 命令数量多维护成本高 | 中 | BaseCommand 提供通用模式，子类保持精简 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第10节（IM 渠道命令对齐）
- `app/channels/commands.py`（`KNOWN_CHANNEL_COMMANDS` 定义）
- `app/channels/manager.py`（`ChannelManager._handle_command` 现有命令分发）
