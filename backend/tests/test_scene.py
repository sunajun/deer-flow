from unittest.mock import MagicMock

import pytest

from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry, reset_scene_registry
from deerflow.tools.scene_tools import activate_scene, deactivate_scene, list_active_scenes


def _make_minimal_config(tools=None):
    config = MagicMock()
    config.tools = tools or []
    config.models = []
    config.tool_search.enabled = False
    config.skill_evolution.enabled = False
    config.sandbox = MagicMock()
    config.acp_agents = {}
    config.scenes = MagicMock()
    config.scenes.enabled = True
    return config


class TestActivateSceneTool:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_activate_valid_scene(self):
        result = activate_scene.invoke({"scene_type": "planning"})
        assert "规划" in result
        assert "已激活" in result

    def test_activate_invalid_scene(self):
        result = activate_scene.invoke({"scene_type": "nonexistent"})
        assert "无效场景类型" in result

    def test_activate_conversation_scene(self):
        result = activate_scene.invoke({"scene_type": "conversation"})
        assert "对话" in result


class TestDeactivateSceneTool:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_deactivate_non_conversation(self):
        result = deactivate_scene.invoke({"scene_type": "planning"})
        assert "已退出" in result

    def test_deactivate_conversation_forbidden(self):
        result = deactivate_scene.invoke({"scene_type": "conversation"})
        assert "不可退出" in result

    def test_deactivate_invalid_scene(self):
        result = deactivate_scene.invoke({"scene_type": "nonexistent"})
        assert "无效场景类型" in result


class TestListActiveScenesTool:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_list_scenes_returns_all(self):
        result = list_active_scenes.invoke({})
        assert "对话" in result
        assert "规划" in result
        assert "conversation" in result

    def test_list_scenes_includes_tool_ids(self):
        result = list_active_scenes.invoke({})
        assert "ask_clarification" in result


class TestToolAssemblyWithScene:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_allowed_tools_filters_output(self):
        from deerflow.tools.tools import get_available_tools

        app_config = _make_minimal_config()
        allowed = {"ask_clarification", "view_image"}
        tools = get_available_tools(include_mcp=False, allowed_tools=allowed, app_config=app_config)
        tool_names = {t.name for t in tools}
        assert "ask_clarification" in tool_names
        for name in tool_names:
            if name not in allowed and name not in {"activate_scene", "deactivate_scene", "list_active_scenes"}:
                pytest.fail(f"Tool '{name}' should have been filtered out")

    def test_allowed_tools_none_returns_all(self):
        from deerflow.tools.tools import get_available_tools

        app_config = _make_minimal_config()
        tools_none = get_available_tools(include_mcp=False, allowed_tools=None, app_config=app_config)
        tools_explicit_none = get_available_tools(include_mcp=False, app_config=app_config)
        assert len(tools_none) == len(tools_explicit_none)


class TestToolAssemblyAlwaysHasSceneTools:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_scene_tools_not_filtered(self):
        from deerflow.tools.tools import get_available_tools

        app_config = _make_minimal_config()
        allowed = {"ask_clarification"}
        tools = get_available_tools(include_mcp=False, allowed_tools=allowed, app_config=app_config)
        tool_names = {t.name for t in tools}
        assert "activate_scene" in tool_names
        assert "deactivate_scene" in tool_names
        assert "list_active_scenes" in tool_names

    def test_scene_tools_present_without_filter(self):
        from deerflow.tools.tools import get_available_tools

        app_config = _make_minimal_config()
        tools = get_available_tools(include_mcp=False, app_config=app_config)
        tool_names = {t.name for t in tools}
        assert "activate_scene" in tool_names
        assert "deactivate_scene" in tool_names
        assert "list_active_scenes" in tool_names


class TestSceneAPIActivate:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    @pytest.mark.asyncio
    async def test_activate_valid(self):
        from app.gateway.routers.scenes import activate_scene as api_activate

        result = await api_activate(scene_type="planning")
        assert "scene" in result
        assert "allowed_tools" in result
        assert result["scene"]["type"] == "planning"

    @pytest.mark.asyncio
    async def test_activate_invalid(self):
        from app.gateway.routers.scenes import activate_scene as api_activate

        result = await api_activate(scene_type="nonexistent")
        assert "error" in result


class TestSceneAPIDeactivate:
    @pytest.mark.asyncio
    async def test_deactivate_conversation(self):
        from app.gateway.routers.scenes import deactivate_scene as api_deactivate

        result = await api_deactivate(scene_type="conversation")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_deactivate_other(self):
        from app.gateway.routers.scenes import deactivate_scene as api_deactivate

        result = await api_deactivate(scene_type="planning")
        assert "deactivated" in result


class TestSceneAPIActiveList:
    @pytest.mark.asyncio
    async def test_list_active(self):
        from app.gateway.routers.scenes import list_active_scenes as api_list_active

        result = await api_list_active()
        assert "active_scenes" in result
        assert "conversation" in result["active_scenes"]


class TestSceneFilteringIntegration:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_full_filter_chain(self):
        from deerflow.scene.filter import get_allowed_tools as get_scene_allowed_tools
        from deerflow.tools.tools import get_available_tools

        app_config = _make_minimal_config()
        scene_state = {"active_scenes": ["conversation"]}
        allowed = get_scene_allowed_tools(scene_state)
        assert "ask_clarification" in allowed

        tools = get_available_tools(include_mcp=False, allowed_tools=allowed, app_config=app_config)
        tool_names = {t.name for t in tools}
        assert "ask_clarification" in tool_names
        assert "activate_scene" in tool_names

    def test_planning_scene_allows_search_tools(self):
        from deerflow.scene.filter import get_allowed_tools as get_scene_allowed_tools

        scene_state = {"active_scenes": ["planning"]}
        allowed = get_scene_allowed_tools(scene_state)
        assert "web_search" in allowed
        assert "read_file" in allowed
