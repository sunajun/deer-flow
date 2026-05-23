from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry


def get_allowed_tools(scene_state: dict | None) -> set[str]:
    if scene_state is None:
        return set()

    active_scenes_raw = scene_state.get("active_scenes", [])
    active_scenes = [SceneType(s) for s in active_scenes_raw]
    registry = get_scene_registry()
    return registry.get_allowed_tools(active_scenes)
