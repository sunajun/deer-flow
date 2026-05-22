# T19 - 前端治理页面 + 集成测试

## 元信息
- **任务ID**: T19
- **阶段**: 第3期 - 治理与协同
- **优先级**: P4
- **预估工期**: 2 天
- **依赖任务**: T16, T17, T18
- **关联差距**: 差距9 - 统一治理面

## 目标
实现统一治理面的三个前端页面（智能体管理、技能管理、权限配置），并与后端 API 进行端到端集成测试。

## 重要约束

> 前端导航集成需修改 `workspace-content.tsx` 和 `WorkspaceSidebar` 组件。现有布局使用 `SidebarProvider` + `WorkspaceSidebar` + `SidebarInset` 结构。治理页面导航入口应添加到 `WorkspaceSidebar` 中。

> 智能体管理页面 API 调用应使用 `/api/agent-configs` 前缀（T16 新路由），而非 `/api/agents`（现有自定义智能体 CRUD）。

## 详细实现步骤

### 步骤1: 创建智能体管理页面
- **文件**: `frontend/src/app/workspace/governance/agents/page.tsx`
- **操作**: 新建
- **内容**: 智能体管理页面，包含：
  - 智能体列表表格（ID、名称、模型、版本、状态、操作）
  - 创建智能体对话框（表单：名称、描述、模型选择、工具分组多选、场景多选）
  - 编辑智能体对话框（预填当前配置）
  - 版本历史抽屉（展示版本列表，每条显示：版本号、变更字段、时间、操作者）
  - 回滚确认弹窗（选择目标版本，确认后调用 rollback API）
  - 删除确认弹窗
  - API 调用：`GET /api/agent-configs`、`POST /api/agent-configs`、`PUT /api/agent-configs/{name}`、`DELETE /api/agent-configs/{name}`、`GET /api/agent-configs/{name}/versions`、`POST /api/agent-configs/{name}/rollback`
- **验收**: 页面可正常展示智能体列表，CRUD 操作正常

### 步骤2: 创建智能体管理 API 客户端
- **文件**: `frontend/src/lib/api/agent-configs.ts`
- **操作**: 新建
- **内容**: 封装智能体配置管理 API 调用（使用 `/api/agent-configs` 前缀）：
  - `listAgentConfigs(params?)` — 获取智能体配置列表
  - `createAgentConfig(data)` — 创建智能体配置
  - `getAgentConfig(agentName)` — 获取详情
  - `updateAgentConfig(agentName, data)` — 更新
  - `deleteAgentConfig(agentName)` — 删除
  - `getAgentConfigVersions(agentName)` — 获取版本历史
  - `rollbackAgentConfig(agentName, targetVersion)` — 回滚
- **验收**: API 客户端类型安全，错误处理完善

### 步骤3: 创建技能管理页面
- **文件**: `frontend/src/app/workspace/governance/skills/page.tsx`
- **操作**: 新建
- **内容**: 技能管理页面，包含：
  - 已安装技能列表（名称、版本、状态 enabled/disabled、操作）
  - 启用/禁用切换开关
  - 绑定智能体选择器（多选已创建的智能体）
  - 安装技能对话框（输入技能 ID，可选版本）
  - 卸载确认弹窗
  - 更新检查按钮（调用 check-updates，显示可更新列表）
  - 一键更新按钮
  - API 调用：`GET /api/skills/market`、`POST /api/skills/install`、`POST /api/skills/{id}/enable`、`POST /api/skills/{id}/disable`、`DELETE /api/skills/{id}`、`GET /api/skills/check-updates`、`POST /api/skills/{id}/update`
- **验收**: 技能启用/禁用/安装/卸载流程正常

### 步骤4: 创建技能管理 API 客户端
- **文件**: `frontend/src/lib/api/skills.ts`
- **操作**: 新建
- **内容**: 封装技能管理 API 调用：
  - `listMarketSkills()` — 获取市场技能列表
  - `installSkill(data)` — 安装
  - `enableSkill(skillId, agentId?)` — 启用
  - `disableSkill(skillId, agentId?)` — 禁用
  - `uninstallSkill(skillId)` — 卸载
  - `checkUpdates()` — 检查更新
  - `updateSkill(skillId)` — 更新
- **验收**: API 客户端类型安全

### 步骤5: 创建权限配置页面
- **文件**: `frontend/src/app/workspace/governance/permissions/page.tsx`
- **操作**: 新建
- **内容**: 权限配置页面，包含：
  - 角色列表卡片（admin/user/guest）
  - 每个角色展开编辑面板：
    - 允许场景多选
    - 允许工具输入（支持通配符和排除规则语法）
    - 最大并行会话数滑块
    - 功能开关：可创建智能体、可管理技能、可创建定时任务
  - 保存按钮（调用 PUT /api/governance/roles/{role}）
  - 权限预览区域
  - API 调用：`GET /api/governance/roles`、`PUT /api/governance/roles/{role}`、`POST /api/governance/check-access`
- **验收**: 角色权限编辑和预览功能正常

### 步骤6: 创建权限 API 客户端
- **文件**: `frontend/src/lib/api/governance.ts`
- **操作**: 新建
- **内容**: 封装权限 API 调用：
  - `listRoles()` — 获取角色列表
  - `updateRole(role, permissions)` — 更新角色权限
  - `checkAccess(params)` — 检查权限
- **验收**: API 客户端类型安全

### 步骤7: 创建治理面导航 + 集成到 WorkspaceSidebar
- **文件**: `frontend/src/app/workspace/governance/page.tsx`
- **操作**: 新建
- **内容**: 治理面入口页，包含导航卡片：
  - 智能体管理（链接到 /workspace/governance/agents）
  - 技能管理（链接到 /workspace/governance/skills）
  - 权限配置（链接到 /workspace/governance/permissions）

- **文件**: `frontend/src/components/workspace/workspace-sidebar.tsx`
- **操作**: 改造
- **内容**: 在 `WorkspaceSidebar` 中添加"治理"导航项，链接到 `/workspace/governance`。确保与现有导航结构一致（使用相同的 `SidebarMenuButton` 等组件）。

- **文件**: `frontend/src/app/workspace/workspace-content.tsx`
- **操作**: 无需改造（治理页面作为 `children` 在 `SidebarInset` 中渲染，现有布局结构已支持）
- **验收**: 导航链接可正确跳转，治理入口在侧边栏可见

### 步骤8: 编写集成测试
- **文件**: `backend/tests/test_governance_integration.py`
- **操作**: 新建
- **内容**: 后端集成测试：
  - 完整流程：创建智能体配置 → 安装技能 → 启用技能绑定到智能体 → 配置权限 → 验证工具过滤
  - 版本追踪流程：创建 → 更新3次 → 查看版本历史 → 回滚到 v1.0.0 → 验证配置恢复
  - 权限联动：设置 guest 角色 → 验证 guest 只能使用 chat/clarify
  - 技能+权限联动：禁用技能后验证工具不再可用

- **文件**: `frontend/tests/e2e/governance.spec.ts`
- **操作**: 新建
- **内容**: 前端 E2E 测试（Playwright + mock 后端）：
  - 智能体管理页面：列表展示、创建、编辑、删除
  - 技能管理页面：启用/禁用切换、安装/卸载
  - 权限配置页面：角色编辑、权限预览
  - 侧边栏导航：治理入口可见且可点击
- **验收**: 集成测试和 E2E 测试通过

## 验收标准
- [ ] 智能体管理页面：CRUD + 版本历史 + 回滚功能完整
- [ ] 技能管理页面：安装/卸载/启用/禁用/更新检查功能完整
- [ ] 权限配置页面：角色编辑 + 权限预览功能完整
- [ ] 治理面导航页面链接正确
- [ ] `WorkspaceSidebar` 中添加治理导航入口
- [ ] API 客户端类型安全，错误处理完善
- [ ] 后端集成测试通过（智能体+技能+权限联动）
- [ ] 前端 E2E 测试通过
- [ ] 遵循前端规范：使用 Shadcn 组件、`cn()` class 合并、`@/*` 路径别名

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 集成测试 | 创建智能体配置→安装技能→绑定→验证工具可用 | 工具在智能体上下文中可用 |
| 集成测试 | 创建→更新3次→回滚到 v1.0.0 | 配置与 v1.0.0 一致 |
| 集成测试 | 设置 guest 权限→调用 bash 工具 | 中间件拦截，返回拒绝 |
| E2E 测试 | 智能体管理：创建→编辑→删除 | 页面操作流程正确 |
| E2E 测试 | 技能管理：安装→启用→禁用→卸载 | 状态切换正确展示 |
| E2E 测试 | 权限配置：编辑 user 角色→保存 | 保存成功，权限更新 |
| E2E 测试 | 侧边栏治理导航 | 入口可见，点击跳转正确 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 前端组件库（Shadcn）缺少复杂组件 | 中 | 使用基础组件组合，版本历史可用 Table + Drawer |
| E2E 测试 mock 后端复杂 | 中 | 使用 MSW 拦截 API 请求，返回预定义响应 |
| 智能体/技能/权限联动测试数据依赖 | 高 | 集成测试使用 pytest fixture 按顺序创建依赖数据 |
| 页面加载性能（大量智能体/技能） | 低 | 首期不做虚拟滚动，列表限制 100 条 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第9节（统一治理面）
- `frontend/src/app/workspace/workspace-content.tsx`（现有布局结构）
- `frontend/src/components/workspace/workspace-sidebar.tsx`（侧边栏导航）
- frontend/CLAUDE.md（前端开发规范）
