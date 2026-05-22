# T07 - 场景数据模型、注册表与基础过滤

## 元信息
- **任务ID**: T07
- **阶段**: 第2期 - 场景与观测
- **优先级**: P1
- **预估工期**: 3 天
- **依赖任务**: T04（DAG 节点就绪，场景可与 Plan 联动）
- **关联差距**: 差距2 - 多场景系统

## 目标
建立 Scene 核心数据模型与 SceneRegistry 单例注册表，实现 7 种内置场景定义，完成场景过滤基础逻辑。所有状态字段必须与 ThreadState（TypedDict）兼容，使用 JSON 可序列化的 dict 类型。

## 详细实现步骤

### 步骤1: 创建场景数据模型
- **文件**: `backend/packages/harness/deerflow/scene/__init__.py`
- **操作**: 新建
- **内容**: 模块入口
```python
from deerflow.scene.models import Scene, SceneType, PermissionLevel, ToolGroup
from deerflow.scene.registry import SceneRegistry, get_scene_registry
```

- **文件**: `backend/packages/harness/deerflow/scene/models.py`
- **操作**: 新建
- **内容**: 完整场景数据模型（Pydantic 用于配置/注册表定义，不用于 ThreadState 字段）
```python
from enum import Enum

from pydantic import BaseModel, Field


class SceneType(str, Enum):
    CONVERSATION = "conversation"
    PLANNING = "planning"
    FILE_OPERATION = "file_operation"
    WEB_SEARCH = "web_search"
    GOVERNANCE = "governance"
    AUTOMATION = "automation"
    SANDBOX_RUNTIME = "sandbox"


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL = "full"


class ToolGroup(BaseModel):
    name: str
    tool_ids: list[str]
    permission: PermissionLevel = PermissionLevel.READ_ONLY


class Scene(BaseModel):
    type: SceneType
    name: str
    description: str
    tool_groups: list[ToolGroup]
    auto_deactivate_after: int = 300
    activates_plan_mode: bool = False
    priority: int = 0
```
- **验收**: 模型可实例化，字段校验通过

### 步骤2: 创建内置场景注册表（单例模式）
- **文件**: `backend/packages/harness/deerflow/scene/registry.py`
- **操作**: 新建
- **内容**: 7 种预设场景定义，使用与 ChannelService 一致的单例模式
```python
import logging
from typing import TYPE_CHECKING

from deerflow.scene.models import PermissionLevel, Scene, SceneType, ToolGroup

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BUILTIN_SCENES: dict[SceneType, Scene] = {
    SceneType.CONVERSATION: Scene(
        type=SceneType.CONVERSATION,
        name="对话",
        description="默认聊天模式，仅核心工具",
        tool_groups=[
            ToolGroup(
                name="core",
                tool_ids=["chat", "clarify", "view_image"],
                permission=PermissionLevel.READ_ONLY,
            ),
        ],
        auto_deactivate_after=0,
        activates_plan_mode=False,
        priority=0,
    ),
    SceneType.PLANNING: Scene(
        type=SceneType.PLANNING,
        name="规划",
        description="只读摸底，不做生产变更",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="search", tool_ids=["tavily_search", "jina_reader", "web_search"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="read_only_file", tool_ids=["read_file", "ls", "glob", "grep"], permission=PermissionLevel.READ_ONLY),
        ],
        auto_deactivate_after=600,
        activates_plan_mode=True,
        priority=10,
    ),
    SceneType.FILE_OPERATION: Scene(
        type=SceneType.FILE_OPERATION,
        name="文件操作",
        description="文件读写操作模式",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="file_ops", tool_ids=["read_file", "write_file", "str_replace", "ls", "glob", "grep"], permission=PermissionLevel.READ_WRITE),
        ],
        auto_deactivate_after=300,
        activates_plan_mode=False,
        priority=5,
    ),
    SceneType.WEB_SEARCH: Scene(
        type=SceneType.WEB_SEARCH,
        name="网络搜索",
        description="搜索与信息检索模式",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="search", tool_ids=["tavily_search", "jina_reader", "web_search"], permission=PermissionLevel.READ_ONLY),
        ],
        auto_deactivate_after=300,
        activates_plan_mode=False,
        priority=5,
    ),
    SceneType.GOVERNANCE: Scene(
        type=SceneType.GOVERNANCE,
        name="治理",
        description="智能体与技能管理",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="governance", tool_ids=["setup_agent", "update_agent", "skill_manage"], permission=PermissionLevel.FULL),
        ],
        auto_deactivate_after=600,
        activates_plan_mode=False,
        priority=15,
    ),
    SceneType.AUTOMATION: Scene(
        type=SceneType.AUTOMATION,
        name="自动化",
        description="定时任务与自动化配置",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="automation", tool_ids=["bash", "task"], permission=PermissionLevel.FULL),
        ],
        auto_deactivate_after=600,
        activates_plan_mode=False,
        priority=10,
    ),
    SceneType.SANDBOX_RUNTIME: Scene(
        type=SceneType.SANDBOX_RUNTIME,
        name="沙箱运行",
        description="代码执行与沙箱环境",
        tool_groups=[
            ToolGroup(name="core", tool_ids=["chat", "clarify", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="sandbox", tool_ids=["bash", "task", "present_file"], permission=PermissionLevel.FULL),
        ],
        auto_deactivate_after=300,
        activates_plan_mode=False,
        priority=5,
    ),
}


class SceneRegistry:
    """场景注册表，管理内置场景和自定义场景。

    采用与 ChannelService 一致的单例模式。
    """

    def __init__(self) -> None:
        self._scenes: dict[SceneType, Scene] = dict(BUILTIN_SCENES)

    def get(self, scene_type: SceneType) -> Scene | None:
        return self._scenes.get(scene_type)

    def register(self, scene: Scene) -> None:
        """注册或覆盖场景定义"""
        self._scenes[scene.type] = scene
        logger.info("Registered scene: %s (%s)", scene.name, scene.type.value)

    def unregister(self, scene_type: SceneType) -> None:
        if scene_type in self._scenes:
            del self._scenes[scene_type]

    def list_scenes(self) -> list[Scene]:
        return list(self._scenes.values())

    def get_allowed_tools(self, active_scenes: list[SceneType]) -> set[str]:
        """多场景叠加：工具取并集"""
        allowed: set[str] = set()
        for scene_type in active_scenes:
            scene = self._scenes.get(scene_type)
            if not scene:
                continue
            for group in scene.tool_groups:
                allowed.update(group.tool_ids)
        return allowed

    def validate_tool_ids(self, available_tool_names: set[str]) -> list[str]:
        """校验注册表中的工具 ID 是否真实存在，返回不存在的 ID"""
        missing: list[str] = []
        for scene in self._scenes.values():
            for group in scene.tool_groups:
                for tid in group.tool_ids:
                    if tid not in available_tool_names:
                        missing.append(tid)
        return sorted(set(missing))


_scene_registry: SceneRegistry | None = None


def get_scene_registry() -> SceneRegistry:
    """获取全局 SceneRegistry 单例"""
    global _scene_registry
    if _scene_registry is None:
        _scene_registry = SceneRegistry()
    return _scene_registry


def reset_scene_registry() -> None:
    """重置单例（用于测试）"""
    global _scene_registry
    _scene_registry = None
```
- **验收**: 7 种场景均有完整定义，工具 ID 与现有工具对齐；单例模式与 ChannelService 一致

### 步骤3: 扩展 ThreadState
- **文件**: `backend/packages/harness/deerflow/agents/thread_state.py`
- **操作**: 改造
- **内容**: 新增场景状态字段，使用 `NotRequired[dict | None]` 模式确保 JSON 可序列化
```python
from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState


class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]


class ThreadDataState(TypedDict):
    workspace_path: NotRequired[str | None]
    uploads_path: NotRequired[str | None]
    outputs_path: NotRequired[str | None]


class ViewedImageData(TypedDict):
    base64: str
    mime_type: str


def merge_artifacts(existing: list[str] | None, new: list[str] | None) -> list[str]:
    if existing is None:
        return new or []
    if new is None:
        return existing
    return list(dict.fromkeys(existing + new))


def merge_viewed_images(existing: dict[str, ViewedImageData] | None, new: dict[str, ViewedImageData] | None) -> dict[str, ViewedImageData]:
    if existing is None:
        return new or {}
    if new is None:
        return existing
    if len(new) == 0:
        return {}
    return {**existing, **new}


def merge_scene_state(existing: dict | None, new: dict | None) -> dict:
    """Reducer for scene_state - new dict fully replaces existing."""
    if new is None:
        return existing or {}
    return new


class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
    scene_state: NotRequired[dict | None]
```
- **关键约束**: `scene_state` 必须是 `NotRequired[dict | None]`，不能使用 Pydantic 模型类型。ThreadState 是 TypedDict，所有字段必须是 JSON 可序列化的 dict。场景状态的结构为：
```python
{
    "active_scenes": ["conversation"],
    "scene_history": [{"action": "activate", "scene": "planning", "at": 1700000000.0}],
    "last_activity": {"conversation": 1700000000.0}
}
```
- **验收**: ThreadState 可接受 scene_state 字段，且字段为 JSON 可序列化的 dict

### 步骤4: 实现场景过滤逻辑
- **文件**: `backend/packages/harness/deerflow/scene/filter.py`
- **操作**: 新建
- **内容**: 多场景叠加过滤
```python
from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry


def get_allowed_tools(scene_state: dict | None) -> set[str]:
    """多场景叠加：工具取并集。

    Args:
        scene_state: ThreadState 中的 scene_state dict，结构为
            {"active_scenes": ["conversation", ...], ...}
            为 None 时返回空集（不过滤）。
    """
    if scene_state is None:
        return set()

    active_scenes_raw = scene_state.get("active_scenes", [])
    active_scenes = [SceneType(s) for s in active_scenes_raw]
    registry = get_scene_registry()
    return registry.get_allowed_tools(active_scenes)
```
- **验收**: 单场景/多场景叠加过滤正确

### 步骤5: 工具 ID 对齐验证
- **文件**: `backend/packages/harness/deerflow/scene/registry.py`
- **操作**: 续写（已包含在步骤2中）
- **内容**: `validate_tool_ids` 方法已在 SceneRegistry 中实现。在 Gateway lifespan 启动时调用：
```python
from deerflow.scene.registry import get_scene_registry
from deerflow.tools import get_available_tools

registry = get_scene_registry()
tool_names = {t.name for t in get_available_tools(include_mcp=False)}
missing = registry.validate_tool_ids(tool_names)
if missing:
    logger.warning("Scene registry references unknown tool IDs: %s", missing)
```
- **验收**: 启动时检查工具 ID 一致性

## 验收标准
- [ ] Scene / SceneType / PermissionLevel / ToolGroup 模型定义完成
- [ ] SceneRegistry 单例实现，7 种内置场景注册完成，工具 ID 与现有工具对齐
- [ ] ThreadState 新增 `scene_state: NotRequired[dict | None]` 字段（JSON 可序列化）
- [ ] get_allowed_tools 实现单场景/多场景叠加过滤
- [ ] 工具 ID 启动校验

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | scene_state 默认值 | active_scenes=["conversation"] |
| 单元测试 | 单场景过滤 | 只返回该场景工具 |
| 单元测试 | 多场景叠加 | 工具取并集 |
| 单元测试 | CONVERSATION + PLANNING | 包含 core + search + read_only_file |
| 单元测试 | validate_tool_ids | 不存在的工具 ID 被检出 |
| 单元测试 | 场景优先级 | 高优先级场景工具权限生效 |
| 单元测试 | SceneRegistry 单例 | get_scene_registry() 返回同一实例 |
| 单元测试 | scene_state JSON 序列化 | dict 可被 json.dumps 序列化 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 工具 ID 与实际不一致 | 高 | 启动校验 + 日志警告 |
| 场景定义与实际需求不匹配 | 中 | 支持自定义场景覆盖 |
| scene_state 类型与 ThreadState 不兼容 | 低 | 使用 NotRequired[dict \| None] 模式 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第2节
- ThreadState 定义: `backend/packages/harness/deerflow/agents/thread_state.py`
- ChannelService 单例模式: `backend/app/channels/service.py`
