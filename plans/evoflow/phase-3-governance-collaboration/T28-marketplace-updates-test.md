# T28 - 技能市场更新机制 + 测试

## 元信息
- **任务ID**: T28
- **阶段**: 第3期 - 治理与协同
- **优先级**: P4
- **预估工期**: 2 天
- **依赖任务**: T26, T27
- **关联差距**: 差距11 - 技能市场

## 目标
实现技能市场的自动更新检查、版本比对、安全更新和更新通知机制，并进行全面的集成测试。

## 重要约束

> **配置必须添加 `MarketplaceConfig` Pydantic 类到 `AppConfig`**。`AppConfig`（`deerflow/config/app_config.py`）已有 `model_config = ConfigDict(extra="allow")`，未知 YAML 键会保留在 `model_extra` 中。但为了类型安全和 IDE 支持，应将 `MarketplaceConfig` 作为 `AppConfig` 的显式字段添加。

> 更新检查应复用 `SkillRegistry.check_updates()`（T26 实现），而非重新实现版本比对逻辑。

## 详细实现步骤

### 步骤1: 添加 MarketplaceConfig 到 AppConfig
- **文件**: `backend/packages/harness/deerflow/config/app_config.py`
- **操作**: 改造
- **内容**: 在 `AppConfig` 中添加 `MarketplaceConfig` 字段：
  ```python
  from deerflow.marketplace.models import MarketplaceConfig

  class AppConfig(BaseModel):
      model_config = ConfigDict(extra="allow")
      # ... 现有字段 ...
      marketplace: MarketplaceConfig = Field(default_factory=MarketplaceConfig)
  ```
- **验收**: `AppConfig.marketplace` 可正确解析 config.yaml 中的 marketplace 配置段

### 步骤2: 实现自动更新检查
- **文件**: `backend/packages/harness/deerflow/marketplace/updater.py`
- **操作**: 新建
- **内容**: 实现自动更新检查器：
  ```python
  class SkillUpdater:
      def __init__(self, registry: SkillRegistry, config: MarketplaceConfig):
          self._registry = registry
          self._config = config
          self._last_check: datetime | None = None
          self._available_updates: list[dict] = []

      async def check_updates(self, force: bool = False) -> list[dict]:
          """检查可更新技能，复用 SkillRegistry.check_updates()"""
          if not force and self._available_updates and self._is_check_fresh():
              return self._available_updates
          await self._registry.fetch_index()
          self._available_updates = await self._registry.check_updates()
          self._last_check = datetime.now()
          return self._available_updates

      async def update_skill(self, skill_id: str) -> dict:
          """更新单个技能"""
          return await self._registry.update_skill(skill_id)

      async def update_all(self) -> list[dict]:
          """更新所有可更新技能"""
          updates = await self.check_updates()
          results = []
          for update in updates:
              try:
                  result = await self._registry.update_skill(update["skill_id"])
                  results.append({"skill_id": update["skill_id"], "success": True, "result": result})
              except Exception as e:
                  results.append({"skill_id": update["skill_id"], "success": False, "error": str(e)})
          self._available_updates = []
          return results

      def _is_check_fresh(self) -> bool:
          if not self._last_check:
              return False
          elapsed = (datetime.now() - self._last_check).total_seconds()
          return elapsed < self._config.cache_ttl
  ```
- **验收**: 更新检查复用 `SkillRegistry.check_updates()`

### 步骤3: 实现版本比对逻辑
- **文件**: `backend/packages/harness/deerflow/marketplace/updater.py`
- **操作**: 续写
- **内容**: 实现语义化版本比对：
  ```python
  def compare_versions(current: str, available: str) -> int:
      """比较两个语义化版本。返回 -1/0/1。"""
      def parse(v: str) -> tuple[int, ...]:
          return tuple(int(x) for x in v.split("."))
      c, a = parse(current), parse(available)
      return (c > a) - (c < a)

  def is_update_available(current_version: str, available_version: str) -> bool:
      """判断是否有可用更新"""
      return compare_versions(current_version, available_version) < 0

  def is_security_update(current_version: str, available_version: str) -> bool:
      """判断是否为安全更新（补丁版本变更）"""
      c = tuple(int(x) for x in current_version.split("."))
      a = tuple(int(x) for x in available_version.split("."))
      return c[0] == a[0] and c[1] == a[1] and a[2] > c[2]
  ```
- **验收**: 版本比对逻辑正确

### 步骤4: 实现更新通知
- **文件**: `backend/packages/harness/deerflow/marketplace/updater.py`
- **操作**: 续写
- **内容**: 实现更新通知机制：
  - 通过 `MessageBus` 发送更新通知到已连接的渠道
  - 通知格式：`"有 N 个技能可更新：skill-a (1.0.0→1.1.0), skill-b (2.0.0→2.0.1)"`
  - 仅在 `auto_update_check=True` 时自动检查并发送通知
- **验收**: 更新通知可发送到渠道

### 步骤5: 添加更新 API 端点
- **文件**: `backend/app/gateway/routers/marketplace.py`
- **操作**: 改造（T27 已创建此文件）
- **内容**: 添加更新相关端点（如 T27 未包含）：
  - `GET /api/marketplace/updates` — 检查可更新技能（T27 可能已包含）
  - `POST /api/marketplace/skills/{skill_id}/update` — 更新单个技能（T27 可能已包含）
  - `POST /api/marketplace/update-all` — 一键更新所有
  - `GET /api/marketplace/update-status` — 获取更新状态
- **验收**: 更新 API 端点可用

### 步骤6: 编写单元测试
- **文件**: `backend/tests/test_marketplace_updater.py`
- **操作**: 新建
- **内容**: 测试用例：
  - 版本比对：compare_versions("1.0.0", "1.0.1") → -1
  - 版本比对：compare_versions("1.1.0", "1.0.1") → 1
  - 版本比对：compare_versions("1.0.0", "1.0.0") → 0
  - is_update_available("1.0.0", "1.0.1") → True
  - is_update_available("1.1.0", "1.0.1") → False
  - is_security_update("1.0.0", "1.0.1") → True
  - is_security_update("1.0.0", "1.1.0") → False
  - SkillUpdater.check_updates（mock SkillRegistry）
  - SkillUpdater.update_skill（mock SkillRegistry）
  - SkillUpdater.update_all（mock SkillRegistry）
  - 缓存新鲜度检查
  - AppConfig.marketplace 字段解析
- **验收**: `cd backend && make test` 全部通过

### 步骤7: 编写集成测试
- **文件**: `backend/tests/test_marketplace_integration.py`
- **操作**: 新建
- **内容**: 集成测试（mock httpx 和 SkillInstaller）：
  - 完整流程：拉取索引 → 搜索技能 → 安装技能 → 检查更新 → 更新技能 → 卸载技能
  - 更新流程：安装 v1.0.0 → 索引更新为 v1.1.0 → 检查更新 → 更新到 v1.1.0
  - 安全更新检测：安装 v1.0.0 → 索引更新为 v1.0.1 → 检测为安全更新
  - 一键更新：3个技能可更新 → update_all → 全部更新成功
  - 更新失败处理：1个更新失败 → 部分成功结果
  - AppConfig 解析：config.yaml 中 marketplace 配置正确解析
- **验收**: 集成测试通过

### 步骤8: 编写 E2E 测试
- **文件**: `backend/tests/test_marketplace_e2e.py`
- **操作**: 新建
- **内容**: 端到端测试（mock 外部依赖）：
  - API 全链路：浏览 → 安装 → 检查更新 → 更新 → 卸载
  - 前端交互（通过 API 调用模拟）：
    - 搜索技能 → 查看详情 → 安装 → 检查更新 → 更新
  - 更新通知发送
- **验收**: E2E 测试通过

## 验收标准
- [ ] `MarketplaceConfig` 作为显式字段添加到 `AppConfig`
- [ ] SkillUpdater 实现自动更新检查，复用 `SkillRegistry.check_updates()`
- [ ] 语义化版本比对逻辑正确
- [ ] 安全更新检测（补丁版本变更）
- [ ] 更新通知机制实现
- [ ] 更新 API 端点可用
- [ ] 单元测试通过（版本比对、更新检查、缓存）
- [ ] 集成测试通过（完整更新流程）
- [ ] E2E 测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | compare_versions("1.0.0", "1.0.1") | 返回 -1 |
| 单元测试 | is_update_available("1.0.0", "1.1.0") | 返回 True |
| 单元测试 | is_security_update("1.0.0", "1.0.1") | 返回 True |
| 单元测试 | is_security_update("1.0.0", "1.1.0") | 返回 False |
| 单元测试 | SkillUpdater.check_updates | 返回可更新列表 |
| 单元测试 | SkillUpdater.update_all | 全部更新成功 |
| 单元测试 | AppConfig.marketplace 解析 | 字段正确填充 |
| 集成测试 | 安装→检查更新→更新 | 版本从 1.0.0 更新到 1.1.0 |
| 集成测试 | 一键更新3个技能 | 全部成功 |
| 集成测试 | 更新失败处理 | 部分成功，错误信息正确 |
| E2E 测试 | API 全链路 | 浏览→安装→更新→卸载 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 版本号格式不规范（非语义化） | 中 | compare_versions 容错处理，解析失败视为不可更新 |
| 更新过程中技能不可用 | 低 | 先下载新版本，再原子替换 |
| 自动更新通知频率过高 | 低 | 受 cache_ttl 控制，默认1小时 |
| AppConfig 添加字段影响现有配置 | 低 | MarketplaceConfig 有默认值，旧配置文件无需修改 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第11节（技能市场）
- `deerflow/config/app_config.py`（`AppConfig` 定义，`ConfigDict(extra="allow")`）
- `deerflow/marketplace/registry.py`（T26 实现的 `SkillRegistry.check_updates()`）
