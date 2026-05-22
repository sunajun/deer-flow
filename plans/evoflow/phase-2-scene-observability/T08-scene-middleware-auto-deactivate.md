# T08 - SceneMiddleware、自动淡化与意图检测

## 元信息
- **任务ID**: T08
- **阶段**: 第2期 - 场景与观测
- **优先级**: P2
- **预估工期**: 3 天
- **依赖任务**: T07
- **关联差距**: 差距2 - 多场景系统

## 目标
实现 SceneMiddleware 中间件，继承 `AgentMiddleware[ThreadState]`，使用标准钩子（`after_model`、`after_agent`、`wrap_model_call`）实现工具调用拦截、自动淡化过期场景、意图检测自动切换场景。

## 详细实现步骤

### 步骤1: 创建 SceneMiddleware
- **文件**: `backend/packages/harness/deerflow/agents/middlewares/scene_middleware.py`
- **操作**: 新建
- **内容**: 场景中间件主类，继承 `AgentMiddleware[ThreadState]`
```python
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage
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
    - wrap_model_call: 注入意图检测提示（如需要）

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
        """默认意图关键词映射，可通过构造函数覆盖。"""
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
            scene = get_scene_registry().get(SceneType(scene_name))
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
```
- **验收**: 非允许工具被拦截，允许工具放行；使用标准 AgentMiddleware 钩子

### 步骤2: 注册中间件
- **文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
- **操作**: 改造
- **内容**: 在 `_build_middlewares()` 函数中注册 SceneMiddleware，通过 `custom_middlewares` 参数注入
```python
from deerflow.agents.middlewares.scene_middleware import SceneMiddleware

def _build_middlewares(
    config: RunnableConfig,
    model_name: str | None,
    agent_name: str | None = None,
    custom_middlewares: list[AgentMiddleware] | None = None,
    *,
    app_config: AppConfig | None = None,
):
    # ... 现有逻辑 ...

    scene_config = getattr(resolved_app_config, "scenes", None)
    if scene_config and getattr(scene_config, "enabled", False):
        intent_keywords = getattr(scene_config, "intent_keywords", None)
        custom_middlewares = custom_middlewares or []
        custom_middlewares.append(SceneMiddleware(intent_keywords=intent_keywords))

    # ... 现有逻辑：custom_middlewares 在 ClarificationMiddleware 之前注入 ...
```
- **验收**: 中间件在 agent 初始化时被加载

### 步骤3: 创建场景中间件测试
- **文件**: `backend/tests/test_scene_middleware.py`
- **操作**: 新建
- **内容**: 测试中间件所有功能
```python
import time

from deerflow.agents.middlewares.scene_middleware import SceneMiddleware
from deerflow.scene.models import SceneType


def test_tool_call_allowed():
    """允许的工具放行 — after_model 返回 None"""


def test_tool_call_rejected():
    """非允许工具被拦截 — after_model 返回 messages 更新"""


def test_auto_deactivate_timeout():
    """超时场景移除 — after_agent 返回 scene_state 更新"""


def test_auto_deactivate_conversation_stays():
    """CONVERSATION 不被移除"""


def test_auto_deactivate_no_timeout():
    """auto_deactivate_after=0 不移除"""


def test_intent_keyword_detection():
    """关键词触发场景 — before_agent 返回 scene_state 更新"""


def test_intent_activate_plan_mode():
    """planning 场景开启 plan_mode"""


def test_multi_scene_overlay():
    """多场景工具取并集"""


def test_custom_intent_keywords():
    """自定义关键词覆盖默认映射"""


def test_scene_state_json_serializable():
    """scene_state dict 可被 json.dumps 序列化"""
```
- **验收**: 所有测试通过

## 验收标准
- [ ] SceneMiddleware 继承 `AgentMiddleware[ThreadState]`，使用标准钩子
- [ ] 工具拦截在 `after_model` 中实现（检查 AIMessage.tool_calls）
- [ ] 自动淡化在 `after_agent` 中实现
- [ ] 意图检测在 `before_agent` 中实现，关键词可配置
- [ ] planning 场景自动开启 plan_mode
- [ ] 场景切换历史记录完整
- [ ] 中间件通过 `_build_middlewares` 的 `custom_middlewares` 参数注册

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | 允许工具放行 | after_model 返回 None |
| 单元测试 | 非允许工具拦截 | after_model 返回 messages 更新 |
| 单元测试 | 超时场景移除 | after_agent 返回 scene_state 更新 |
| 单元测试 | CONVERSATION 不移除 | 始终在 active_scenes |
| 单元测试 | "搜索"触发 WEB_SEARCH | before_agent 返回 scene_state 更新 |
| 单元测试 | "规划"触发 PLANNING | is_plan_mode=True |
| 单元测试 | 多场景叠加 | 工具取并集 |
| 单元测试 | 自定义关键词 | 覆盖默认映射 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 关键词误触发场景 | 中 | 关键词可配置，支持关闭意图检测 |
| 自动淡化时间不合理 | 低 | 可配置，默认 5 分钟 |
| after_model 修改 AIMessage 影响下游 | 低 | 仅修改 tool_calls，保持消息结构完整 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第2节
- AgentMiddleware 接口: `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py`
- _build_middlewares 注册模式: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
