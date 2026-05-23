from fastapi import APIRouter

from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.post("/activate")
async def activate_scene(scene_type: str):
    registry = get_scene_registry()
    try:
        st = SceneType(scene_type)
    except ValueError:
        return {"error": f"Unknown scene: {scene_type}"}
    scene = registry.get(st)
    if scene is None:
        return {"error": f"Unknown scene: {scene_type}"}
    return {"scene": scene.model_dump(), "allowed_tools": sorted(registry.get_allowed_tools([st]))}


@router.post("/deactivate")
async def deactivate_scene(scene_type: str):
    if scene_type == SceneType.CONVERSATION.value:
        return {"error": "Cannot deactivate conversation scene"}
    return {"deactivated": scene_type}


@router.get("/active")
async def list_active_scenes():
    return {"active_scenes": ["conversation"]}


@router.get("/available")
async def list_available_scenes():
    registry = get_scene_registry()
    return {"scenes": [s.model_dump() for s in registry.list_scenes()]}


@router.get("/{scene_type}/tools")
async def get_scene_tools(scene_type: str):
    registry = get_scene_registry()
    try:
        st = SceneType(scene_type)
    except ValueError:
        return {"error": f"Unknown scene: {scene_type}"}
    return {"scene_type": scene_type, "tools": sorted(registry.get_allowed_tools([st]))}
