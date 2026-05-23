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
                tool_ids=["ask_clarification", "view_image"],
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
            ToolGroup(name="core", tool_ids=["ask_clarification", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="search", tool_ids=["web_search", "web_fetch"], permission=PermissionLevel.READ_ONLY),
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
            ToolGroup(name="core", tool_ids=["ask_clarification", "view_image"], permission=PermissionLevel.READ_ONLY),
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
            ToolGroup(name="core", tool_ids=["ask_clarification", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="search", tool_ids=["web_search", "web_fetch"], permission=PermissionLevel.READ_ONLY),
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
            ToolGroup(name="core", tool_ids=["ask_clarification", "view_image"], permission=PermissionLevel.READ_ONLY),
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
            ToolGroup(name="core", tool_ids=["ask_clarification", "view_image"], permission=PermissionLevel.READ_ONLY),
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
            ToolGroup(name="core", tool_ids=["ask_clarification", "view_image"], permission=PermissionLevel.READ_ONLY),
            ToolGroup(name="sandbox", tool_ids=["bash", "task", "present_files"], permission=PermissionLevel.FULL),
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
        self._scenes[scene.type] = scene
        logger.info("Registered scene: %s (%s)", scene.name, scene.type.value)

    def unregister(self, scene_type: SceneType) -> None:
        if scene_type in self._scenes:
            del self._scenes[scene_type]

    def list_scenes(self) -> list[Scene]:
        return list(self._scenes.values())

    def get_allowed_tools(self, active_scenes: list[SceneType]) -> set[str]:
        allowed: set[str] = set()
        for scene_type in active_scenes:
            scene = self._scenes.get(scene_type)
            if not scene:
                continue
            for group in scene.tool_groups:
                allowed.update(group.tool_ids)
        return allowed

    def validate_tool_ids(self, available_tool_names: set[str]) -> list[str]:
        missing: list[str] = []
        for scene in self._scenes.values():
            for group in scene.tool_groups:
                for tid in group.tool_ids:
                    if tid not in available_tool_names:
                        missing.append(tid)
        return sorted(set(missing))


_scene_registry: SceneRegistry | None = None


def get_scene_registry() -> SceneRegistry:
    global _scene_registry
    if _scene_registry is None:
        _scene_registry = SceneRegistry()
    return _scene_registry


def reset_scene_registry() -> None:
    global _scene_registry
    _scene_registry = None
