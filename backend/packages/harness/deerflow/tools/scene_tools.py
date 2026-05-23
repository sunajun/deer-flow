from langchain_core.tools import tool

from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry


@tool
def activate_scene(scene_type: str) -> str:
    """激活工作场景。可用场景：conversation, planning, file_operation, web_search, governance, automation, sandbox"""
    try:
        st = SceneType(scene_type)
    except ValueError:
        valid = ", ".join(t.value for t in SceneType)
        return f"无效场景类型: {scene_type}。可用场景: {valid}"
    registry = get_scene_registry()
    scene = registry.get(st)
    if scene is None:
        return f"场景 {scene_type} 未注册"
    return f"场景 '{scene.name}' 已激活。可用工具: {registry.get_allowed_tools([st])}"


@tool
def deactivate_scene(scene_type: str) -> str:
    """退出工作场景"""
    try:
        st = SceneType(scene_type)
    except ValueError:
        return f"无效场景类型: {scene_type}"
    if st == SceneType.CONVERSATION:
        return "对话场景不可退出"
    return f"场景 {scene_type} 已退出"


@tool
def list_active_scenes() -> str:
    """列出当前活跃场景及其可用工具"""
    registry = get_scene_registry()
    scenes = registry.list_scenes()
    lines = []
    for scene in scenes:
        tools = set()
        for group in scene.tool_groups:
            tools.update(group.tool_ids)
        lines.append(f"- {scene.name} ({scene.type.value}): {', '.join(sorted(tools))}")
    return "\n".join(lines)
