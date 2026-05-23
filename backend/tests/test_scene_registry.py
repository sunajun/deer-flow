import json

import pytest

from deerflow.agents.thread_state import merge_scene_state
from deerflow.scene.filter import get_allowed_tools
from deerflow.scene.models import PermissionLevel, Scene, SceneType, ToolGroup
from deerflow.scene.registry import (
    BUILTIN_SCENES,
    SceneRegistry,
    get_scene_registry,
    reset_scene_registry,
)


class TestSceneModels:
    def test_scene_type_values(self):
        assert SceneType.CONVERSATION.value == "conversation"
        assert SceneType.PLANNING.value == "planning"
        assert SceneType.FILE_OPERATION.value == "file_operation"
        assert SceneType.WEB_SEARCH.value == "web_search"
        assert SceneType.GOVERNANCE.value == "governance"
        assert SceneType.AUTOMATION.value == "automation"
        assert SceneType.SANDBOX_RUNTIME.value == "sandbox"

    def test_permission_level_values(self):
        assert PermissionLevel.READ_ONLY.value == "read_only"
        assert PermissionLevel.READ_WRITE.value == "read_write"
        assert PermissionLevel.FULL.value == "full"

    def test_tool_group_defaults(self):
        tg = ToolGroup(name="core", tool_ids=["chat"])
        assert tg.permission == PermissionLevel.READ_ONLY

    def test_scene_instantiation(self):
        scene = Scene(
            type=SceneType.CONVERSATION,
            name="Test",
            description="Test scene",
            tool_groups=[ToolGroup(name="core", tool_ids=["a", "b"])],
        )
        assert scene.auto_deactivate_after == 300
        assert scene.activates_plan_mode is False
        assert scene.priority == 0

    def test_scene_type_from_string(self):
        assert SceneType("conversation") == SceneType.CONVERSATION
        assert SceneType("planning") == SceneType.PLANNING

    def test_scene_type_invalid_string(self):
        with pytest.raises(ValueError):
            SceneType("nonexistent")


class TestBuiltinScenes:
    def test_seven_builtin_scenes(self):
        assert len(BUILTIN_SCENES) == 7

    def test_all_scene_types_covered(self):
        for st in SceneType:
            assert st in BUILTIN_SCENES

    def test_conversation_scene(self):
        s = BUILTIN_SCENES[SceneType.CONVERSATION]
        assert s.name == "对话"
        assert s.auto_deactivate_after == 0
        assert s.activates_plan_mode is False
        assert s.priority == 0

    def test_planning_scene(self):
        s = BUILTIN_SCENES[SceneType.PLANNING]
        assert s.name == "规划"
        assert s.activates_plan_mode is True
        assert s.priority == 10
        tool_ids = set()
        for g in s.tool_groups:
            tool_ids.update(g.tool_ids)
        assert "read_file" in tool_ids
        assert "web_search" in tool_ids

    def test_governance_scene(self):
        s = BUILTIN_SCENES[SceneType.GOVERNANCE]
        assert s.priority == 15
        tool_ids = set()
        for g in s.tool_groups:
            tool_ids.update(g.tool_ids)
        assert "setup_agent" in tool_ids
        assert "update_agent" in tool_ids
        assert "skill_manage" in tool_ids

    def test_sandbox_scene_present_files(self):
        s = BUILTIN_SCENES[SceneType.SANDBOX_RUNTIME]
        tool_ids = set()
        for g in s.tool_groups:
            tool_ids.update(g.tool_ids)
        assert "present_files" in tool_ids


class TestSceneRegistry:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_singleton(self):
        r1 = get_scene_registry()
        r2 = get_scene_registry()
        assert r1 is r2

    def test_reset_creates_new_instance(self):
        r1 = get_scene_registry()
        reset_scene_registry()
        r2 = get_scene_registry()
        assert r1 is not r2

    def test_get_builtin_scene(self):
        registry = get_scene_registry()
        scene = registry.get(SceneType.CONVERSATION)
        assert scene is not None
        assert scene.name == "对话"

    def test_get_unregistered_scene(self):
        registry = get_scene_registry()
        registry.unregister(SceneType.CONVERSATION)
        assert registry.get(SceneType.CONVERSATION) is None

    def test_register_override_scene(self):
        override_scene = Scene(
            type=SceneType.CONVERSATION,
            name="自定义对话",
            description="覆盖默认对话场景",
            tool_groups=[ToolGroup(name="core", tool_ids=["tool_a"])],
        )
        registry = get_scene_registry()
        original = registry.get(SceneType.CONVERSATION)
        assert original is not None
        assert original.name == "对话"
        registry.register(override_scene)
        assert registry.get(SceneType.CONVERSATION).name == "自定义对话"

    def test_unregister_scene(self):
        registry = get_scene_registry()
        assert registry.get(SceneType.CONVERSATION) is not None
        registry.unregister(SceneType.CONVERSATION)
        assert registry.get(SceneType.CONVERSATION) is None

    def test_unregister_already_removed(self):
        registry = get_scene_registry()
        registry.unregister(SceneType.CONVERSATION)
        registry.unregister(SceneType.CONVERSATION)

    def test_list_scenes(self):
        registry = get_scene_registry()
        scenes = registry.list_scenes()
        assert len(scenes) == 7

    def test_get_allowed_tools_single_scene(self):
        registry = get_scene_registry()
        tools = registry.get_allowed_tools([SceneType.CONVERSATION])
        assert "ask_clarification" in tools
        assert "view_image" in tools

    def test_get_allowed_tools_multiple_scenes_union(self):
        registry = get_scene_registry()
        tools = registry.get_allowed_tools([SceneType.CONVERSATION, SceneType.PLANNING])
        assert "ask_clarification" in tools
        assert "view_image" in tools
        assert "web_search" in tools
        assert "read_file" in tools

    def test_get_allowed_tools_conversation_plus_planning(self):
        registry = get_scene_registry()
        tools = registry.get_allowed_tools([SceneType.CONVERSATION, SceneType.PLANNING])
        conv_tools = registry.get_allowed_tools([SceneType.CONVERSATION])
        planning_tools = registry.get_allowed_tools([SceneType.PLANNING])
        assert tools == conv_tools | planning_tools

    def test_get_allowed_tools_empty_list(self):
        registry = get_scene_registry()
        tools = registry.get_allowed_tools([])
        assert tools == set()

    def test_get_allowed_tools_unregistered_scene(self):
        registry = get_scene_registry()
        registry.unregister(SceneType.CONVERSATION)
        tools = registry.get_allowed_tools([SceneType.CONVERSATION])
        assert tools == set()

    def test_validate_tool_ids_all_present(self):
        registry = get_scene_registry()
        all_tool_ids = set()
        for scene in registry.list_scenes():
            for group in scene.tool_groups:
                all_tool_ids.update(group.tool_ids)
        missing = registry.validate_tool_ids(all_tool_ids)
        assert missing == []

    def test_validate_tool_ids_missing(self):
        registry = get_scene_registry()
        missing = registry.validate_tool_ids(set())
        assert len(missing) > 0

    def test_validate_tool_ids_partial(self):
        registry = get_scene_registry()
        all_tool_ids = set()
        for scene in registry.list_scenes():
            for group in scene.tool_groups:
                all_tool_ids.update(group.tool_ids)
        partial = all_tool_ids - {"ask_clarification"}
        missing = registry.validate_tool_ids(partial)
        assert "ask_clarification" in missing


class TestSceneFilter:
    def setup_method(self):
        reset_scene_registry()

    def teardown_method(self):
        reset_scene_registry()

    def test_filter_none_state(self):
        tools = get_allowed_tools(None)
        assert tools == set()

    def test_filter_empty_active_scenes(self):
        tools = get_allowed_tools({"active_scenes": []})
        assert tools == set()

    def test_filter_single_scene(self):
        tools = get_allowed_tools({"active_scenes": ["conversation"]})
        assert "ask_clarification" in tools
        assert "view_image" in tools

    def test_filter_multiple_scenes(self):
        tools = get_allowed_tools({"active_scenes": ["conversation", "planning"]})
        assert "ask_clarification" in tools
        assert "web_search" in tools
        assert "read_file" in tools

    def test_filter_unknown_scene_type(self):
        with pytest.raises(ValueError):
            get_allowed_tools({"active_scenes": ["nonexistent"]})


class TestMergeSceneState:
    def test_new_replaces_existing(self):
        existing = {"active_scenes": ["conversation"]}
        new = {"active_scenes": ["planning"]}
        result = merge_scene_state(existing, new)
        assert result == {"active_scenes": ["planning"]}

    def test_new_none_returns_existing(self):
        existing = {"active_scenes": ["conversation"]}
        result = merge_scene_state(existing, None)
        assert result == {"active_scenes": ["conversation"]}

    def test_existing_none_returns_new(self):
        new = {"active_scenes": ["planning"]}
        result = merge_scene_state(None, new)
        assert result == {"active_scenes": ["planning"]}

    def test_both_none_returns_empty(self):
        result = merge_scene_state(None, None)
        assert result == {}


class TestSceneStateJsonSerialization:
    def test_scene_state_serializable(self):
        state = {
            "active_scenes": ["conversation"],
            "scene_history": [{"action": "activate", "scene": "planning", "at": 1700000000.0}],
            "last_activity": {"conversation": 1700000000.0},
        }
        serialized = json.dumps(state)
        deserialized = json.loads(serialized)
        assert deserialized == state

    def test_scene_type_values_serializable(self):
        types = [t.value for t in SceneType]
        serialized = json.dumps(types)
        deserialized = json.loads(serialized)
        assert deserialized == ["conversation", "planning", "file_operation", "web_search", "governance", "automation", "sandbox"]
