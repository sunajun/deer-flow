# T12 - 任务中心前端页面与集成测试

## 元信息
- **任务ID**: T12
- **阶段**: 第2期 - 场景与观测
- **优先级**: P3
- **预估工期**: 2 天
- **依赖任务**: T11
- **关联差距**: 差距8 - 任务中心与观测面

## 目标
创建任务中心前端页面，包括任务列表、任务详情和日志查看组件，完成集成测试。页面需集成到现有 workspace 布局中。

## 详细实现步骤

### 步骤1: 创建任务列表页
- **文件**: `frontend/src/app/workspace/tasks/page.tsx`
- **操作**: 新建
- **内容**: 任务列表页面
  - 任务表格：task_id、名称、类型、状态、创建时间、耗时
  - 状态过滤器：全部/运行中/成功/失败/已取消
  - 类型过滤器：手动/定时/子代理/DAG节点
  - 分页控件
  - 操作按钮：重试、重跑、取消
  - 点击行跳转详情页
- **验收**: 列表页可展示任务数据，过滤和分页正常

### 步骤2: 创建任务详情页
- **文件**: `frontend/src/app/workspace/tasks/[task_id]/page.tsx`
- **操作**: 新建
- **内容**: 任务详情页面
  - 基本信息：名称、描述、状态、时间线
  - 执行结果展示（JSON 格式化）
  - 错误信息展示
  - 子任务列表（如有 parent_task_id 关联）
  - 操作按钮：重试、重跑、取消、导出审计
- **验收**: 详情页正确展示任务信息

### 步骤3: 创建日志查看组件
- **文件**: `frontend/src/app/workspace/tasks/LogViewer.tsx`
- **操作**: 新建
- **内容**: 执行日志查看组件
  - 日志列表：时间戳 + 内容
  - 自动滚动到底部（运行中任务）
  - 实时更新（运行中任务使用 SSE）
  - 搜索/过滤
- **验收**: 日志可查看，实时更新正常

### 步骤4: 添加导航入口
- **文件**: `frontend/src/components/workspace/workspace-sidebar.tsx`
- **操作**: 改造
- **内容**: 在 WorkspaceSidebar 组件中添加"任务中心"导航项，与现有导航结构保持一致
- **验收**: 可从侧边栏导航进入任务中心

- **文件**: `frontend/src/app/workspace/workspace-content.tsx`
- **操作**: 确认无需修改
- **说明**: `workspace-content.tsx` 仅提供 SidebarProvider + WorkspaceSidebar + SidebarInset 布局壳，子页面通过 `{children}` 渲染。新增的 `/workspace/tasks` 路由会自动被 Next.js App Router 匹配，无需修改此文件。
- **验收**: 任务中心页面在 workspace 布局中正确渲染

### 步骤5: 集成测试
- **文件**: `frontend/tests/e2e/task-center.spec.ts`
- **操作**: 新建
- **内容**: E2E 测试
```typescript
// 测试用例：
// test_task_list_page - 任务列表展示
// test_task_list_filter - 状态过滤
// test_task_list_pagination - 分页
// test_task_detail_page - 任务详情
// test_task_retry - 重试操作
// test_task_cancel - 取消操作
// test_log_viewer - 日志查看
// test_audit_export - 审计导出
```
- **验收**: E2E 测试通过

## 验收标准
- [ ] 任务列表页展示、过滤、分页正常
- [ ] 任务详情页信息完整
- [ ] 日志查看组件实时更新
- [ ] 操作按钮（重试/重跑/取消/导出）可用
- [ ] WorkspaceSidebar 导航入口添加
- [ ] 页面在 workspace-content.tsx 布局中正确渲染
- [ ] E2E 测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| E2E 测试 | 任务列表 | 表格正确渲染 |
| E2E 测试 | 状态过滤 | 仅显示对应状态 |
| E2E 测试 | 任务详情 | 信息完整展示 |
| E2E 测试 | 日志查看 | 日志按时间显示 |
| E2E 测试 | 重试操作 | 弹出确认→状态变化 |
| E2E 测试 | 侧边栏导航 | 点击进入任务中心 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 前端组件与 Shadcn 规范冲突 | 低 | 使用 Shadcn Table/Dialog |
| 实时日志性能 | 中 | 虚拟滚动 + 限制日志量 |
| workspace 布局集成问题 | 低 | 遵循 Next.js App Router 约定，无需修改 workspace-content.tsx |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第8节
- Workspace 布局: `frontend/src/app/workspace/workspace-content.tsx`
- WorkspaceSidebar: `frontend/src/components/workspace/workspace-sidebar.tsx`
