import json
import time
from unittest.mock import MagicMock

import pytest

from deerflow.agents.middlewares.scene_middleware import SceneMiddleware
from deerflow.scene.models import Scene, SceneType, ToolGroup
from deerflow.scene.registry import get_scene_registry, reset_scene_registry


def _make_runtime():
    runtime = MagicMock()
    runtime.context = {}
    return runtime


def _make_state(messages=None, scene_state=None):
    state = {"messages": messages or [], "scene_state": scene_state}
    return state


def _make_ai_message(tool_calls=None, content=""):
    msg = MagicMock()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.model_copy = MagicMock(return_value=msg)
    return msg


def _make_human_message(content=""):
    msg = MagicMock()
    msg.type = "human"
    msg.content = content
    return msg


class TestToolCallAllowed:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_allowed_tool_passes_through(self):
        mw = SceneMiddleware()
        ai_msg = _make_ai_message(tool_calls=[{"name": "ask_clarification", "args": {}}])
        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.after_model(state, _make_runtime())
        assert result is None

    def test_no_tool_calls_returns_none(self):
        mw = SceneMiddleware()
        ai_msg = _make_ai_message(tool_calls=[], content="Hello")
        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.after_model(state, _make_runtime())
        assert result is None

    def test_no_messages_returns_none(self):
        mw = SceneMiddleware()
        state = _make_state(
            messages=[],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.after_model(state, _make_runtime())
        assert result is None

    def test_empty_allowed_tools_returns_none(self):
        mw = SceneMiddleware()
        ai_msg = _make_ai_message(tool_calls=[{"name": "ask_clarification", "args": {}}])
        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": [], "scene_history": [], "last_activity": {}},
        )
        result = mw.after_model(state, _make_runtime())
        assert result is None


class TestToolCallRejected:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_rejected_tool_stripped(self):
        mw = SceneMiddleware()
        filtered_msg = MagicMock()
        filtered_msg.tool_calls = [{"name": "ask_clarification", "args": {}}]

        ai_msg = _make_ai_message(
            tool_calls=[
                {"name": "ask_clarification", "args": {}},
                {"name": "web_search", "args": {"query": "test"}},
            ],
        )
        ai_msg.model_copy = MagicMock(return_value=filtered_msg)

        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.after_model(state, _make_runtime())
        assert result is not None
        assert "messages" in result
        ai_msg.model_copy.assert_called_once()
        update_arg = ai_msg.model_copy.call_args[1]["update"]
        assert len(update_arg["tool_calls"]) == 1
        assert update_arg["tool_calls"][0]["name"] == "ask_clarification"

    def test_all_tools_rejected_strips_and_adds_message(self):
        mw = SceneMiddleware()
        stripped_msg = MagicMock()
        stripped_msg.tool_calls = []
        stripped_msg.content = "[场景限制]"

        ai_msg = _make_ai_message(
            tool_calls=[{"name": "web_search", "args": {"query": "test"}}],
            content="",
        )
        ai_msg.model_copy = MagicMock(return_value=stripped_msg)

        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.after_model(state, _make_runtime())
        assert result is not None
        update_arg = ai_msg.model_copy.call_args[1]["update"]
        assert update_arg["tool_calls"] == []
        assert "[场景限制]" in update_arg["content"]


class TestAutoDeactivateTimeout:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_timeout_scene_removed(self):
        mw = SceneMiddleware()
        now = time.time()
        old_time = now - 600
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation", "web_search"],
                "scene_history": [],
                "last_activity": {"conversation": old_time, "web_search": old_time},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is not None
        assert "scene_state" in result
        assert "web_search" not in result["scene_state"]["active_scenes"]
        assert "conversation" in result["scene_state"]["active_scenes"]

    def test_conversation_never_removed(self):
        mw = SceneMiddleware()
        now = time.time()
        very_old = now - 999999
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation"],
                "scene_history": [],
                "last_activity": {"conversation": very_old},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is None

    def test_auto_deactivate_after_zero_not_removed(self):
        mw = SceneMiddleware()
        now = time.time()
        very_old = now - 999999
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation"],
                "scene_history": [],
                "last_activity": {"conversation": very_old},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is None

    def test_no_timeout_returns_none(self):
        mw = SceneMiddleware()
        now = time.time()
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation", "web_search"],
                "scene_history": [],
                "last_activity": {"conversation": now, "web_search": now},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is None

    def test_history_recorded_on_deactivate(self):
        mw = SceneMiddleware()
        now = time.time()
        old_time = now - 600
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation", "web_search"],
                "scene_history": [],
                "last_activity": {"conversation": old_time, "web_search": old_time},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is not None
        history = result["scene_state"]["scene_history"]
        assert any(h["action"] == "auto_deactivate" and h["scene"] == "web_search" for h in history)

    def test_unregistered_scene_skipped(self):
        mw = SceneMiddleware()
        now = time.time()
        old_time = now - 600
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation", "nonexistent"],
                "scene_history": [],
                "last_activity": {"conversation": old_time, "nonexistent": old_time},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is None


class TestIntentKeywordDetection:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_search_keyword_activates_web_search(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("帮我搜索一下天气")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is not None
        assert "scene_state" in result
        assert "web_search" in result["scene_state"]["active_scenes"]

    def test_plan_keyword_activates_planning(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("帮我规划一个项目")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is not None
        assert "scene_state" in result
        assert "planning" in result["scene_state"]["active_scenes"]

    def test_already_active_scene_returns_none(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("搜索天气")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation", "web_search"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is None

    def test_no_intent_returns_none(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("你好，今天天气不错")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is None

    def test_non_human_message_returns_none(self):
        mw = SceneMiddleware()
        ai_msg = _make_ai_message(content="搜索天气")
        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is None

    def test_empty_messages_returns_none(self):
        mw = SceneMiddleware()
        state = _make_state(
            messages=[],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is None


class TestIntentActivatePlanMode:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_planning_scene_activates_plan_mode(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("帮我规划一下")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is not None
        assert result.get("is_plan_mode") is True

    def test_web_search_does_not_activate_plan_mode(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("搜索天气")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is not None
        assert "is_plan_mode" not in result


class TestMultiSceneOverlay:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_multi_scene_tools_union(self):
        mw = SceneMiddleware()
        conv_tools = get_scene_registry().get_allowed_tools([SceneType.CONVERSATION])
        planning_tools = get_scene_registry().get_allowed_tools([SceneType.PLANNING])
        union_tools = conv_tools | planning_tools

        allowed_msg = MagicMock()
        allowed_msg.tool_calls = [{"name": "web_search", "args": {}}]
        allowed_msg.type = "ai"
        allowed_msg.content = ""

        disallowed_tool_name = "write_file"
        assert disallowed_tool_name not in union_tools

        ai_msg = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "args": {}},
                {"name": disallowed_tool_name, "args": {}},
            ],
        )
        filtered_msg = MagicMock()
        ai_msg.model_copy = MagicMock(return_value=filtered_msg)

        state = _make_state(
            messages=[ai_msg],
            scene_state={
                "active_scenes": ["conversation", "planning"],
                "scene_history": [],
                "last_activity": {},
            },
        )
        result = mw.after_model(state, _make_runtime())
        assert result is not None
        update_arg = ai_msg.model_copy.call_args[1]["update"]
        filtered_names = [tc["name"] for tc in update_arg["tool_calls"]]
        assert "web_search" in filtered_names
        assert disallowed_tool_name not in filtered_names


class TestCustomIntentKeywords:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_custom_keywords_override_defaults(self):
        custom = {"web_search": ["find", "lookup"]}
        mw = SceneMiddleware(intent_keywords=custom)
        human_msg = _make_human_message("find the answer")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is not None
        assert "web_search" in result["scene_state"]["active_scenes"]

    def test_default_keyword_not_matched_with_custom(self):
        custom = {"web_search": ["find", "lookup"]}
        mw = SceneMiddleware(intent_keywords=custom)
        human_msg = _make_human_message("搜索天气")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is None


class TestSceneStateJsonSerializable:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_scene_state_serializable(self):
        mw = SceneMiddleware()
        now = time.time()
        human_msg = _make_human_message("搜索天气")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.before_agent(state, _make_runtime())
        assert result is not None
        serialized = json.dumps(result["scene_state"])
        deserialized = json.loads(serialized)
        assert deserialized == result["scene_state"]

    def test_deactivate_state_serializable(self):
        mw = SceneMiddleware()
        now = time.time()
        old_time = now - 600
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation", "web_search"],
                "scene_history": [],
                "last_activity": {"conversation": old_time, "web_search": old_time},
            },
        )
        result = mw._auto_deactivate(state, _make_runtime())
        assert result is not None
        serialized = json.dumps(result["scene_state"])
        deserialized = json.loads(serialized)
        assert deserialized == result["scene_state"]


class TestAsyncMethods:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    @pytest.mark.asyncio
    async def test_aafter_model_delegates(self):
        mw = SceneMiddleware()
        ai_msg = _make_ai_message(tool_calls=[{"name": "ask_clarification", "args": {}}])
        state = _make_state(
            messages=[ai_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = await mw.aafter_model(state, _make_runtime())
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_delegates(self):
        mw = SceneMiddleware()
        now = time.time()
        state = _make_state(
            scene_state={
                "active_scenes": ["conversation", "web_search"],
                "scene_history": [],
                "last_activity": {"conversation": now, "web_search": now},
            },
        )
        result = await mw.aafter_agent(state, _make_runtime())
        assert result is None

    @pytest.mark.asyncio
    async def test_abefore_agent_delegates(self):
        mw = SceneMiddleware()
        human_msg = _make_human_message("搜索天气")
        state = _make_state(
            messages=[human_msg],
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = await mw.abefore_agent(state, _make_runtime())
        assert result is not None
        assert "web_search" in result["scene_state"]["active_scenes"]


class TestActivateScene:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_activate_adds_to_active_scenes(self):
        mw = SceneMiddleware()
        state = _make_state(
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.activate_scene(state, SceneType.WEB_SEARCH)
        assert "web_search" in result["scene_state"]["active_scenes"]
        assert "conversation" in result["scene_state"]["active_scenes"]

    def test_activate_updates_last_activity(self):
        mw = SceneMiddleware()
        state = _make_state(
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.activate_scene(state, SceneType.WEB_SEARCH)
        assert "web_search" in result["scene_state"]["last_activity"]

    def test_activate_records_history(self):
        mw = SceneMiddleware()
        state = _make_state(
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.activate_scene(state, SceneType.WEB_SEARCH)
        history = result["scene_state"]["scene_history"]
        assert any(h["action"] == "activate" and h["scene"] == "web_search" for h in history)

    def test_activate_already_active_no_duplicate(self):
        mw = SceneMiddleware()
        state = _make_state(
            scene_state={"active_scenes": ["conversation", "web_search"], "scene_history": [], "last_activity": {}},
        )
        result = mw.activate_scene(state, SceneType.WEB_SEARCH)
        active = result["scene_state"]["active_scenes"]
        assert active.count("web_search") == 1

    def test_activate_planning_sets_plan_mode(self):
        mw = SceneMiddleware()
        state = _make_state(
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.activate_scene(state, SceneType.PLANNING)
        assert result.get("is_plan_mode") is True

    def test_activate_web_search_no_plan_mode(self):
        mw = SceneMiddleware()
        state = _make_state(
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        result = mw.activate_scene(state, SceneType.WEB_SEARCH)
        assert "is_plan_mode" not in result

    def test_max_scene_history_truncation(self):
        mw = SceneMiddleware(max_scene_history=2)
        state = _make_state(
            scene_state={"active_scenes": ["conversation"], "scene_history": [], "last_activity": {}},
        )
        mw.activate_scene(state, SceneType.WEB_SEARCH)
        result = mw.activate_scene(state, SceneType.PLANNING)
        history = result["scene_state"]["scene_history"]
        assert len(history) <= 2


class TestDefaultSceneState:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_none_scene_state_defaults_to_conversation(self):
        mw = SceneMiddleware()
        state = _make_state(messages=[], scene_state=None)
        scene_state = mw._get_scene_state(state)
        assert scene_state["active_scenes"] == ["conversation"]

    def test_empty_scene_state_defaults_to_conversation(self):
        mw = SceneMiddleware()
        state = _make_state(messages=[], scene_state={})
        scene_state = mw._get_scene_state(state)
        assert scene_state["active_scenes"] == ["conversation"]
