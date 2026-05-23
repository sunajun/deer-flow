from __future__ import annotations

import logging
import time
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import ThreadState
from deerflow.scene.filter import get_allowed_tools
from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry

logger = logging.getLogger(__name__)


class SceneMiddleware(AgentMiddleware[ThreadState]):
    """场景中间件：拦截工具调用，按场景过滤可用工具，自动淡化过期场景。

    使用标准 AgentMiddleware 钩子：
    - after_model: 检查 AI 响应中的 tool_calls，拒绝不在允许列表中的工具调用
    - after_agent: 执行自动淡化逻辑，移除超时场景
    - before_agent: 检测用户意图，自动切换场景

    不使用自定义钩子如 on_tool_call，而是映射到标准接口。
    """

    def __init__(
        self,
        intent_keywords: dict[str, list[str]] | None = None,
        max_scene_history: int = 100,
    ) -> None:
        super().__init__()
        self._intent_keywords = intent_keywords or self._default_intent_keywords()
        self._max_scene_history = max_scene_history

    @staticmethod
    def _default_intent_keywords() -> dict[str, list[str]]:
        return {
            "web_search": ["搜索", "查找", "search", "检索", "查询"],
            "file_operation": ["修改文件", "写文件", "编辑", "create file", "write"],
            "planning": ["规划", "分析", "plan", "设计"],
            "governance": ["管理智能体", "技能管理", "agent manage"],
            "automation": ["定时", "自动化", "schedule", "cron"],
        }

    def _get_scene_state(self, state: ThreadState) -> dict:
        return state.get("scene_state") or {
            "active_scenes": ["conversation"],
            "scene_history": [],
            "last_activity": {},
        }

    def _set_scene_state(self, state: ThreadState, scene_state: dict) -> dict:
        return {"scene_state": scene_state}

    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        """检查 AI 响应中的 tool_calls，拒绝不在当前场景允许列表中的工具。

        这是 on_tool_call 的标准替代方案：在 after_model 中检查
        AIMessage.tool_calls，将不允许的工具调用从响应中移除。
        """
        scene_state = self._get_scene_state(state)
        allowed_tools = get_allowed_tools(scene_state)

        if not allowed_tools:
            return None

        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        filtered_calls = []
        rejected_names = []
        for tc in tool_calls:
            if tc["name"] in allowed_tools:
                filtered_calls.append(tc)
            else:
                rejected_names.append(tc["name"])

        if not rejected_names:
            return None

        logger.info(
            "Scene filter rejected tool calls: %s (allowed: %s)",
            rejected_names,
            allowed_tools,
        )

        if not filtered_calls:
            stripped_msg = last_msg.model_copy(update={
                "tool_calls": [],
                "content": (last_msg.content or "") + f"\n\n[场景限制] 工具 {rejected_names} 在当前场景中不可用，请使用可用工具或切换场景。",
            })
            return {"messages": [stripped_msg]}

        filtered_msg = last_msg.model_copy(update={"tool_calls": filtered_calls})
        return {"messages": [filtered_msg]}

    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self.after_model(state, runtime)

    @override
    def after_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        """自动淡化超时场景。"""
        return self._auto_deactivate(state, runtime)

    @override
    async def aafter_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self._auto_deactivate(state, runtime)

    def _auto_deactivate(self, state: ThreadState, runtime: Runtime) -> dict | None:
        """超时场景自动移除，CONVERSATION 永远保留。"""
        scene_state = self._get_scene_state(state)
        now = time.time()
        active = list(scene_state.get("active_scenes", ["conversation"]))
        last_activity = dict(scene_state.get("last_activity", {}))
        history = list(scene_state.get("scene_history", []))

        to_remove = []
        for scene_name in active:
            if scene_name == SceneType.CONVERSATION.value:
                continue
            try:
                scene_type = SceneType(scene_name)
            except ValueError:
                continue
            scene = get_scene_registry().get(scene_type)
            if scene is None or scene.auto_deactivate_after == 0:
                continue
            last = last_activity.get(scene_name, 0)
            if now - last > scene.auto_deactivate_after:
                to_remove.append(scene_name)

        if not to_remove:
            return None

        for s in to_remove:
            active.remove(s)
            history.append({"action": "auto_deactivate", "scene": s, "at": now})

        if len(history) > self._max_scene_history:
            history = history[-self._max_scene_history:]

        new_scene_state = {
            "active_scenes": active,
            "scene_history": history,
            "last_activity": last_activity,
        }
        logger.info("Auto-deactivated scenes: %s", to_remove)
        return {"scene_state": new_scene_state}

    def _detect_intent(self, content: str) -> str | None:
        """基于关键词的意图检测（快速路径）。关键词可配置。"""
        content_lower = content.lower()
        for scene_name, keywords in self._intent_keywords.items():
            if any(kw in content_lower for kw in keywords):
                return scene_name
        return None

    def activate_scene(self, state: ThreadState, scene_type: SceneType) -> dict:
        """激活场景，更新 scene_state dict。"""
        scene_state = self._get_scene_state(state)
        now = time.time()
        active = list(scene_state.get("active_scenes", ["conversation"]))
        last_activity = dict(scene_state.get("last_activity", {}))
        history = list(scene_state.get("scene_history", []))

        scene_name = scene_type.value
        if scene_name not in active:
            active.append(scene_name)
        last_activity[scene_name] = now
        history.append({"action": "activate", "scene": scene_name, "at": now})

        if len(history) > self._max_scene_history:
            history = history[-self._max_scene_history:]

        new_scene_state = {
            "active_scenes": active,
            "scene_history": history,
            "last_activity": last_activity,
        }

        scene = get_scene_registry().get(scene_type)
        extra: dict = {"scene_state": new_scene_state}
        if scene and scene.activates_plan_mode:
            extra["is_plan_mode"] = True
        return extra

    @override
    def before_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        """在 agent 执行前检测用户意图，自动切换场景。"""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "human":
            return None

        content = getattr(last_msg, "content", "")
        if not isinstance(content, str) or not content:
            return None

        detected = self._detect_intent(content)
        if detected is None:
            return None

        try:
            scene_type = SceneType(detected)
        except ValueError:
            return None

        scene_state = self._get_scene_state(state)
        if detected in scene_state.get("active_scenes", []):
            return None

        logger.info("Intent detected: %s -> activating scene %s", content[:50], detected)
        return self.activate_scene(state, scene_type)

    @override
    async def abefore_agent(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self.before_agent(state, runtime)
