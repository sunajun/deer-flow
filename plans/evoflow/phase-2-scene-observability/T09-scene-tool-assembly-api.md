# T09 - 场景工具装配改造、场景切换工具与 API

## 元信息
- **任务ID**: T09
- **阶段**: 第2期 - 场景与观测
- **优先级**: P3
- **预估工期**: 3 天
- **依赖任务**: T08
- **关联差距**: 差距2 - 多场景系统

## 目标
改造现有工具装配逻辑加入场景过滤，创建场景切换 LangGraph 工具和 API，完成场景系统端到端闭环。

## 详细实现步骤

### 步骤1: 创建场景切换 LangGraph 工具
- **文件**: `backend/packages/harness/deerflow/tools/scene_tools.py`
- **操作**: 新建
- **内容**: 3 个场景切换工具
```python
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
```
- **验收**: 工具可被 LangGraph agent 调用

### 步骤2: 改造工具装配逻辑
- **文件**: `backend/packages/harness/deerflow/tools/tools.py`
- **操作**: 改造
- **内容**: 在 `get_available_tools` 中新增 `allowed_tools` 参数，在去重步骤中进行场景过滤
```python
def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    model_name: str | None = None,
    subagent_enabled: bool = False,
    *,
    app_config: AppConfig | None = None,
    allowed_tools: set[str] | None = None,
) -> list[BaseTool]:
    """Get all available tools from config.

    Args:
        groups: Optional list of tool groups to filter by.
        include_mcp: Whether to include tools from MCP servers (default: True).
        model_name: Optional model name to determine if vision tools should be included.
        subagent_enabled: Whether to include subagent tools (task, task_status).
        app_config: Optional application config override.
        allowed_tools: Optional set of tool names allowed by the current scene.
            When provided, only tools whose names are in this set will be returned.
            Scene tools (activate_scene, deactivate_scene, list_active_scenes) are
            always included regardless of this filter.

    Returns:
        List of available tools.
    """
    config = app_config or get_app_config()
    tool_configs = [tool for tool in config.tools if groups is None or tool.group in groups]

    if not is_host_bash_allowed(config):
        tool_configs = [tool for tool in tool_configs if not _is_host_bash_tool(tool)]

    loaded_tools_raw = [(cfg, resolve_variable(cfg.use, BaseTool)) for cfg in tool_configs]

    for cfg, loaded in loaded_tools_raw:
        if cfg.name != loaded.name:
            logger.warning(
                "Tool name mismatch: config name %r does not match tool .name %r (use: %s).",
                cfg.name,
                loaded.name,
                cfg.use,
            )

    loaded_tools = [_ensure_sync_invocable_tool(t) for _, t in loaded_tools_raw]

    builtin_tools = BUILTIN_TOOLS.copy()
    skill_evolution_config = getattr(config, "skill_evolution", None)
    if getattr(skill_evolution_config, "enabled", False):
        from deerflow.tools.skill_manage_tool import skill_manage_tool
        builtin_tools.append(skill_manage_tool)

    if subagent_enabled:
        builtin_tools.extend(SUBAGENT_TOOLS)
        logger.info("Including subagent tools (task)")

    if model_name is None and config.models:
        model_name = config.models[0].name

    model_config = config.get_model_config(model_name) if model_name else None
    if model_config is not None and model_config.supports_vision:
        builtin_tools.append(view_image_tool)
        logger.info(f"Including view_image_tool for model '{model_name}' (supports_vision=True)")

    mcp_tools = []
    if include_mcp:
        try:
            from deerflow.config.extensions_config import ExtensionsConfig
            from deerflow.mcp.cache import get_cached_mcp_tools

            extensions_config = ExtensionsConfig.from_file()
            if extensions_config.get_enabled_mcp_servers():
                mcp_tools = get_cached_mcp_tools()
                if mcp_tools:
                    logger.info(f"Using {len(mcp_tools)} cached MCP tool(s)")
                    if config.tool_search.enabled:
                        from deerflow.tools.builtins.tool_search import DeferredToolRegistry, get_deferred_registry, set_deferred_registry
                        from deerflow.tools.builtins.tool_search import tool_search as tool_search_tool

                        existing_registry = get_deferred_registry()
                        if existing_registry is None:
                            registry = DeferredToolRegistry()
                            for t in mcp_tools:
                                registry.register(t)
                            set_deferred_registry(registry)
                            logger.info(f"Tool search active: {len(mcp_tools)} tools deferred")
                        else:
                            mcp_tool_names = {t.name for t in mcp_tools}
                            still_deferred = len(existing_registry)
                            promoted_count = max(0, len(mcp_tool_names) - still_deferred)
                            logger.info(f"Tool search active (preserved promotions): {still_deferred} tools deferred, {promoted_count} already promoted")
                        builtin_tools.append(tool_search_tool)
        except ImportError:
            logger.warning("MCP module not available.")
        except Exception as e:
            logger.error(f"Failed to get cached MCP tools: {e}")

    acp_tools: list[BaseTool] = []
    try:
        from deerflow.tools.builtins.invoke_acp_agent_tool import build_invoke_acp_agent_tool

        if app_config is None:
            from deerflow.config.acp_config import get_acp_agents
            acp_agents = get_acp_agents()
        else:
            acp_agents = getattr(config, "acp_agents", {}) or {}
        if acp_agents:
            acp_tools.append(build_invoke_acp_agent_tool(acp_agents))
            logger.info(f"Including invoke_acp_agent tool ({len(acp_agents)} agent(s))")
    except Exception as e:
        logger.warning(f"Failed to load ACP tool: {e}")

    # Add scene tools
    scene_tool_names = {"activate_scene", "deactivate_scene", "list_active_scenes"}
    scene_config = getattr(config, "scenes", None)
    if scene_config and getattr(scene_config, "enabled", False):
        from deerflow.tools.scene_tools import activate_scene, deactivate_scene, list_active_scenes
        builtin_tools.extend([activate_scene, deactivate_scene, list_active_scenes])

    logger.info(f"Total tools loaded: {len(loaded_tools)}, built-in tools: {len(builtin_tools)}, MCP tools: {len(mcp_tools)}, ACP tools: {len(acp_tools)}")

    # Deduplicate by tool name — config-loaded tools take priority
    all_tools = [_ensure_sync_invocable_tool(t) for t in loaded_tools + builtin_tools + mcp_tools + acp_tools]
    seen_names: set[str] = set()
    unique_tools: list[BaseTool] = []
    for t in all_tools:
        if t.name not in seen_names:
            unique_tools.append(t)
            seen_names.add(t.name)
        else:
            logger.warning(
                "Duplicate tool name %r detected and skipped — check your config.yaml and MCP server registrations (issue #1803).",
                t.name,
            )

    # Scene filtering: apply allowed_tools filter after deduplication
    if allowed_tools is not None:
        filtered = [t for t in unique_tools if t.name in allowed_tools or t.name in scene_tool_names]
        logger.info(
            "Scene filter applied: %d/%d tools allowed (scene tools always included)",
            len(filtered),
            len(unique_tools),
        )
        return filtered

    return unique_tools
```
- **关键约束**: `get_available_tools` 不接受 `state: dict` 参数。场景过滤通过新增的 `allowed_tools: set[str] | None = None` 关键字参数实现，在去重步骤之后应用。场景切换工具始终包含在结果中。
- **验收**: 工具装配受场景过滤，场景切换工具始终可用

### 步骤3: 在 agent 工厂中传递 allowed_tools
- **文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
- **操作**: 改造
- **内容**: 在 `_make_lead_agent` 中从 runtime config 获取 scene_state，计算 allowed_tools 并传给 get_available_tools
```python
def _make_lead_agent(config: RunnableConfig, *, app_config: AppConfig):
    cfg = _get_runtime_config(config)
    # ... 现有逻辑 ...

    # Resolve scene-based tool filtering
    allowed_tools: set[str] | None = None
    scene_state = cfg.get("scene_state")
    if scene_state and isinstance(scene_state, dict):
        from deerflow.scene.filter import get_allowed_tools as get_scene_allowed_tools
        allowed_tools = get_scene_allowed_tools(scene_state)

    tools = get_available_tools(
        model_name=model_name,
        groups=agent_config.tool_groups if agent_config else None,
        subagent_enabled=subagent_enabled,
        app_config=resolved_app_config,
        allowed_tools=allowed_tools,
    )
    # ... 后续逻辑不变 ...
```
- **验收**: agent 创建时工具列表受场景过滤

### 步骤4: 创建场景 API
- **文件**: `backend/app/gateway/routers/scenes.py`
- **操作**: 新建
- **内容**: 场景管理 API
```python
from fastapi import APIRouter

from deerflow.scene.models import SceneType
from deerflow.scene.registry import get_scene_registry

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.post("/activate")
async def activate_scene(scene_type: str):
    registry = get_scene_registry()
    scene = registry.get(SceneType(scene_type))
    if scene is None:
        return {"error": f"Unknown scene: {scene_type}"}
    return {"scene": scene.model_dump(), "allowed_tools": sorted(registry.get_allowed_tools([SceneType(scene_type)]))}


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
```
- **验收**: API 端点可访问

### 步骤5: 集成到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 函数中注册 scenes router
```python
from app.gateway.routers import (
    agents,
    artifacts,
    assistants_compat,
    auth,
    channels,
    feedback,
    mcp,
    memory,
    models,
    runs,
    scenes,
    skills,
    suggestions,
    thread_runs,
    threads,
    uploads,
)

def create_app() -> FastAPI:
    # ... 现有逻辑 ...

    # Scenes API is mounted at /api/scenes
    app.include_router(scenes.router)

    # ... 后续路由注册 ...
```
- **验收**: API 在 Gateway 启动后可访问

### 步骤6: 更新配置
- **文件**: `config.example.yaml`
- **操作**: 改造
- **内容**: 新增 scenes 配置段
```yaml
scenes:
  enabled: true
  auto_deactivate: true
  default_scene: conversation
  intent_keywords: {}  # 覆盖默认意图关键词
  custom_scenes: []
```
- **验收**: 配置项可被正确解析

### 步骤7: 创建场景系统完整测试
- **文件**: `backend/tests/test_scene.py`
- **操作**: 新建
- **内容**: 场景系统端到端测试
```python
def test_activate_scene_tool():
    """工具激活场景"""


def test_deactivate_scene_tool():
    """工具退出场景"""


def test_list_active_scenes_tool():
    """列出活跃场景"""


def test_tool_assembly_with_scene():
    """工具装配过滤 — allowed_tools 参数生效"""


def test_tool_assembly_always_has_scene_tools():
    """场景工具始终可用，不被 allowed_tools 过滤"""


def test_scene_api_activate():
    """API 激活"""


def test_scene_api_deactivate():
    """API 退出"""


def test_scene_api_active_list():
    """API 列表"""


def test_scene_filtering_integration():
    """完整过滤链路"""
```
- **验收**: 所有测试通过

## 验收标准
- [ ] 3 个场景切换 LangGraph 工具实现
- [ ] `get_available_tools` 新增 `allowed_tools: set[str] | None = None` 参数，在去重步骤后过滤
- [ ] 场景工具始终可用，不被 allowed_tools 过滤
- [ ] 5 个场景 API 端点可访问
- [ ] scenes router 在 `create_app()` 中注册
- [ ] 场景过滤端到端链路正确
- [ ] 配置示例更新

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | activate_scene | 返回激活确认 |
| 单元测试 | deactivate_scene | 返回退出确认 |
| 单元测试 | 工具装配过滤 | 仅允许工具 + 场景工具 |
| 单元测试 | 场景工具始终可用 | 不被 allowed_tools 过滤 |
| 单元测试 | allowed_tools=None | 不过滤，返回全部工具 |
| 集成测试 | API 激活/退出 | 状态正确变化 |
| 集成测试 | 过滤链路 | 工具调用→场景检查→放行/拒绝 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 工具装配改造影响现有功能 | 中 | allowed_tools=None 时行为不变 |
| 场景工具被自身过滤 | 低 | 场景工具名称加入白名单 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第2节
- get_available_tools 签名: `backend/packages/harness/deerflow/tools/tools.py`
- create_app 路由注册: `backend/app/gateway/app.py`
