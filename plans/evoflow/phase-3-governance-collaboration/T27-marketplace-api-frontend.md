# T27 - 技能市场 API + 前端页面

## 元信息
- **任务ID**: T27
- **阶段**: 第3期 - 治理与协同
- **优先级**: P3
- **预估工期**: 3 天
- **依赖任务**: T26
- **关联差距**: 差距11 - 技能市场

## 目标
实现技能市场的 REST API 和前端页面，提供技能浏览、搜索、安装、更新、卸载的完整用户界面。

## 重要约束

> **路由注册必须在 `create_app()` 中通过 `app.include_router()` 完成**，不使用 `@app.on_event`（Gateway 使用 `lifespan` 上下文管理器）。

> **前端导航集成需修改 `WorkspaceSidebar` 组件**，在侧边栏中添加"技能市场"导航入口，与 T19 的治理导航保持一致的样式和交互模式。

## 详细实现步骤

### 步骤1: 创建市场 API 路由
- **文件**: `backend/app/gateway/routers/marketplace.py`
- **操作**: 新建
- **内容**: 实现 FastAPI 路由：
  - `GET /api/marketplace/skills` — 浏览技能列表（支持分页、分类过滤、搜索）
    - 查询参数：`page`, `page_size`, `category`, `query`
  - `GET /api/marketplace/skills/{skill_id}` — 获取技能详情
  - `GET /api/marketplace/categories` — 获取技能分类列表
  - `POST /api/marketplace/skills/{skill_id}/install` — 安装技能
  - `POST /api/marketplace/skills/{skill_id}/uninstall` — 卸载技能
  - `GET /api/marketplace/updates` — 检查可更新技能
  - `POST /api/marketplace/skills/{skill_id}/update` — 更新技能
  - `POST /api/marketplace/refresh` — 刷新技能索引
- **验收**: 8个 API 端点功能正确

### 步骤2: 注册路由到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 中通过 `app.include_router()` 注册 marketplace router：
  ```python
  from app.gateway.routers.marketplace import router as marketplace_router
  app.include_router(marketplace_router)
  ```
- **验收**: `/api/marketplace/skills` 路由可访问

### 步骤3: 创建市场 API 客户端
- **文件**: `frontend/src/lib/api/marketplace.ts`
- **操作**: 新建
- **内容**: 封装市场 API 调用：
  - `listMarketSkills(params?)` — 浏览技能列表
  - `getMarketSkill(skillId)` — 获取技能详情
  - `listCategories()` — 获取分类列表
  - `installSkill(skillId)` — 安装
  - `uninstallSkill(skillId)` — 卸载
  - `checkUpdates()` — 检查更新
  - `updateSkill(skillId)` — 更新
  - `refreshIndex()` — 刷新索引
- **验收**: API 客户端类型安全

### 步骤4: 创建技能市场页面
- **文件**: `frontend/src/app/workspace/marketplace/page.tsx`
- **操作**: 新建
- **内容**: 技能市场主页面，包含：
  - 搜索栏（关键词搜索）
  - 分类筛选标签（productivity/development/data/communication/automation/other）
  - 技能卡片网格：
    - 每个卡片显示：名称、描述、作者、版本、分类标签、安装状态
    - 操作按钮：安装/卸载/更新
  - 分页控件
  - 刷新索引按钮
- **验收**: 页面可正确展示技能列表和搜索结果

### 步骤5: 创建技能详情页面
- **文件**: `frontend/src/app/workspace/marketplace/skills/[skillId]/page.tsx`
- **操作**: 新建
- **内容**: 技能详情页面，包含：
  - 基本信息：名称、描述、作者、版本、分类、标签
  - 仓库链接（可点击跳转 GitHub）
  - 依赖列表
  - 所需权限列表
  - 更新日志
  - 安装/卸载/更新按钮
  - 版本历史（如有）
- **验收**: 详情页展示完整信息

### 步骤6: 集成到 WorkspaceSidebar 导航
- **文件**: `frontend/src/components/workspace/workspace-sidebar.tsx`
- **操作**: 改造
- **内容**: 在 `WorkspaceSidebar` 中添加"技能市场"导航项，链接到 `/workspace/marketplace`。确保与 T19 的治理导航入口保持一致的样式（使用相同的 `SidebarMenuButton` 等组件）。
- **验收**: 侧边栏中"技能市场"入口可见且可点击

### 步骤7: 编写 API 测试
- **文件**: `backend/tests/test_marketplace_api.py`
- **操作**: 新建
- **内容**: API 端点测试（mock SkillRegistry）：
  - GET /api/marketplace/skills — 列表
  - GET /api/marketplace/skills?category=development — 分类过滤
  - GET /api/marketplace/skills?query=search — 搜索
  - GET /api/marketplace/skills/{id} — 详情
  - GET /api/marketplace/categories — 分类列表
  - POST /api/marketplace/skills/{id}/install — 安装
  - POST /api/marketplace/skills/{id}/uninstall — 卸载
  - GET /api/marketplace/updates — 检查更新
  - POST /api/marketplace/skills/{id}/update — 更新
  - POST /api/marketplace/refresh — 刷新索引
- **验收**: API 测试全部通过

### 步骤8: 编写前端 E2E 测试
- **文件**: `frontend/tests/e2e/marketplace.spec.ts`
- **操作**: 新建
- **内容**: 前端 E2E 测试（Playwright + mock 后端）：
  - 技能市场页面：列表展示、搜索、分类筛选
  - 技能详情页面：信息展示、安装/卸载操作
  - 导航：侧边栏入口跳转正确
- **验收**: E2E 测试通过

## 验收标准
- [ ] 8个市场 API 端点实现完成
- [ ] 路由通过 `app.include_router()` 注册到 `create_app()`
- [ ] 前端市场 API 客户端类型安全
- [ ] 技能市场页面：搜索、分类筛选、卡片网格、分页
- [ ] 技能详情页面：完整信息展示
- [ ] `WorkspaceSidebar` 中添加"技能市场"导航入口
- [ ] API 测试通过
- [ ] 前端 E2E 测试通过
- [ ] 遵循前端规范：Shadcn 组件、`cn()` class 合并、`@/*` 路径别名

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| API 测试 | GET /api/marketplace/skills | 200，返回技能列表 |
| API 测试 | GET /api/marketplace/skills?category=development | 200，返回过滤列表 |
| API 测试 | GET /api/marketplace/skills?query=search | 200，返回搜索结果 |
| API 测试 | GET /api/marketplace/skills/{id} | 200，返回详情 |
| API 测试 | POST /api/marketplace/skills/{id}/install | 200，安装成功 |
| API 测试 | POST /api/marketplace/skills/{id}/uninstall | 200，卸载成功 |
| API 测试 | GET /api/marketplace/updates | 200，返回可更新列表 |
| API 测试 | POST /api/marketplace/refresh | 200，索引刷新 |
| E2E 测试 | 市场页面搜索 | 搜索结果正确展示 |
| E2E 测试 | 市场页面分类筛选 | 筛选结果正确 |
| E2E 测试 | 技能详情页 | 信息完整展示 |
| E2E 测试 | 侧边栏导航 | 入口可见，跳转正确 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 技能索引为空时页面无内容 | 中 | 显示空状态提示和刷新按钮 |
| 安装操作耗时导致 UI 卡顿 | 中 | 安装按钮显示 loading 状态 |
| 前端组件库缺少卡片网格组件 | 低 | 使用 CSS Grid + Card 组件组合 |
| 与 T19 治理页面导航样式不一致 | 低 | 共享导航组件和样式 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第11节（技能市场）
- `backend/app/gateway/app.py`（`create_app()` 和 `app.include_router()` 模式）
- `frontend/src/components/workspace/workspace-sidebar.tsx`（侧边栏导航）
- frontend/CLAUDE.md（前端开发规范）
