# T26 - 技能市场模型 + 注册中心

## 元信息
- **任务ID**: T26
- **阶段**: 第3期 - 治理与协同
- **优先级**: P2
- **预估工期**: 3 天
- **依赖任务**: T17
- **关联差距**: 差距11 - 技能市场

## 目标
建立技能市场的数据模型和注册中心，支持技能元数据管理、分类索引、版本追踪和搜索。首版支持 GitHub Repo + JSON Index 作为技能来源。

## 重要约束

> **`SkillInstaller` 类需要创建**（见 T17）。T17 负责创建 `SkillInstaller` 类封装现有 `installer.py` 函数。本任务（T26）的注册中心应使用 `SkillInstaller` 执行实际的安装/卸载操作，而非直接调用 `safe_extract_skill_archive` 等底层函数。

> **首版技能来源为 GitHub Repo + JSON Index**。技能索引文件（如 `skills-index.json`）托管在 GitHub 仓库中，包含技能元数据列表。注册中心通过 HTTP 拉取索引并缓存。

## 详细实现步骤

### 步骤1: 创建技能市场数据模型
- **文件**: `backend/packages/harness/deerflow/marketplace/models.py`
- **操作**: 新建
- **内容**: 定义以下 Pydantic 模型：
  - `SkillCategory(str, Enum)` — "productivity" | "development" | "data" | "communication" | "automation" | "other"
  - `SkillManifest(BaseModel)`:
    - `skill_id: str` — 唯一标识
    - `name: str` — 显示名称
    - `description: str` — 描述
    - `version: str` — 语义化版本
    - `category: SkillCategory`
    - `tags: list[str] = Field(default_factory=list)`
    - `author: str = ""`
    - `homepage: str = ""`
    - `repository: str = ""` — GitHub 仓库地址
    - `archive_url: str = ""` — 下载地址
    - `checksum: str = ""` — SHA256 校验
    - `min_platform_version: str = ""` — 最低平台版本要求
    - `dependencies: list[str] = Field(default_factory=list)` — 依赖的其他技能
    - `permissions: list[str] = Field(default_factory=list)` — 所需权限
    - `changelog: str = ""`
    - `created_at: datetime | None = None`
    - `updated_at: datetime | None = None`
  - `SkillIndex(BaseModel)`:
    - `version: str = "1.0"` — 索引格式版本
    - `updated_at: datetime`
    - `skills: list[SkillManifest] = Field(default_factory=list)`
  - `SkillRegistryEntry(BaseModel)`:
    - `manifest: SkillManifest`
    - `installed: bool = False`
    - `installed_version: str | None = None`
    - `local_path: str | None = None`
  - `MarketplaceConfig(BaseModel)`:
    - `enabled: bool = True`
    - `index_url: str = ""` — GitHub 仓库中 skills-index.json 的 raw URL
    - `cache_ttl: int = 3600` — 索引缓存时间（秒）
    - `auto_update_check: bool = True`
    - `trusted_sources: list[str] = Field(default_factory=list)` — 信任的来源
    - `model_config = ConfigDict(extra="allow")`
- **验收**: 模型定义完整，Pydantic 校验通过

### 步骤2: 创建模块入口
- **文件**: `backend/packages/harness/deerflow/marketplace/__init__.py`
- **操作**: 新建
- **内容**: 导出核心模型和 Registry：
  ```python
  from deerflow.marketplace.models import SkillCategory, SkillManifest, SkillIndex, SkillRegistryEntry, MarketplaceConfig
  from deerflow.marketplace.registry import SkillRegistry
  ```
- **验收**: 模块可正确导入

### 步骤3: 实现 SkillRegistry
- **文件**: `backend/packages/harness/deerflow/marketplace/registry.py`
- **操作**: 新建
- **内容**: 实现技能注册中心：
  ```python
  class SkillRegistry:
      def __init__(self, config: MarketplaceConfig):
          self._config = config
          self._index: SkillIndex | None = None
          self._entries: dict[str, SkillRegistryEntry] = {}
          self._index_fetched_at: datetime | None = None
          self._installer: SkillInstaller | None = None

      async def fetch_index(self) -> SkillIndex:
          """从 GitHub Repo 拉取 skills-index.json"""
          if self._index and self._is_cache_valid():
              return self._index
          async with httpx.AsyncClient() as client:
              resp = await client.get(self._config.index_url)
              resp.raise_for_status()
              self._index = SkillIndex.model_validate(resp.json())
              self._index_fetched_at = datetime.now()
              self._rebuild_entries()
              return self._index

      async def search(self, query: str, category: SkillCategory | None = None) -> list[SkillRegistryEntry]: ...
      async def get_skill(self, skill_id: str) -> SkillRegistryEntry | None: ...
      async def list_skills(self, category: SkillCategory | None = None) -> list[SkillRegistryEntry]: ...
      async def get_categories(self) -> list[dict]: ...
      async def install_skill(self, skill_id: str, version: str | None = None) -> dict: ...
      async def uninstall_skill(self, skill_id: str) -> None: ...
      async def check_updates(self) -> list[dict]: ...
      async def update_skill(self, skill_id: str) -> dict: ...

      def _is_cache_valid(self) -> bool: ...
      def _rebuild_entries(self) -> None: ...
  ```
- **验收**: 注册中心核心方法实现完成

### 步骤4: 实现 GitHub Repo + JSON Index 拉取
- **文件**: `backend/packages/harness/deerflow/marketplace/registry.py`
- **操作**: 续写
- **内容**: 实现 `fetch_index` 的完整逻辑：
  - 从 `config.index_url`（GitHub raw URL）拉取 `skills-index.json`
  - 解析为 `SkillIndex` 模型
  - 缓存到内存，根据 `cache_ttl` 判断是否需要重新拉取
  - 错误处理：网络异常、JSON 解析失败、索引版本不兼容
  - 重建 `_entries` 映射
- **验收**: 可从 GitHub URL 拉取并解析技能索引

### 步骤5: 实现安装/卸载（使用 SkillInstaller）
- **文件**: `backend/packages/harness/deerflow/marketplace/registry.py`
- **操作**: 续写
- **内容**: 安装和卸载方法使用 `SkillInstaller`（T17 创建）：
  ```python
  async def install_skill(self, skill_id: str, version: str | None = None) -> dict:
      entry = self._entries.get(skill_id)
      if not entry:
          raise ValueError(f"Skill '{skill_id}' not found in registry")
      manifest = entry.manifest
      archive_path = await self._download_archive(manifest.archive_url, manifest.checksum)
      installer = self._get_installer()
      result = await installer.install(skill_id, archive_path=archive_path)
      entry.installed = True
      entry.installed_version = manifest.version
      return result

  async def uninstall_skill(self, skill_id: str) -> None:
      installer = self._get_installer()
      await installer.uninstall(skill_id)
      if skill_id in self._entries:
          self._entries[skill_id].installed = False
          self._entries[skill_id].installed_version = None

  def _get_installer(self) -> SkillInstaller:
      if self._installer is None:
          self._installer = SkillInstaller()
      return self._installer
  ```
- **验收**: 安装/卸载通过 `SkillInstaller` 执行

### 步骤6: 添加 marketplace 配置段
- **文件**: `config.example.yaml`
- **操作**: 改造
- **内容**: 新增配置段：
  ```yaml
  marketplace:
    enabled: true
    index_url: "https://raw.githubusercontent.com/example/deerflow-skills/main/skills-index.json"
    cache_ttl: 3600
    auto_update_check: true
    trusted_sources:
      - "github.com/example"
  ```
- **验收**: 配置可被 `get_app_config()` 正确解析（`AppConfig` 有 `ConfigDict(extra="allow")`）

### 步骤7: 编写单元测试
- **文件**: `backend/tests/test_marketplace_registry.py`
- **操作**: 新建
- **内容**: 测试用例：
  - SkillManifest 模型校验
  - SkillIndex 解析
  - SkillRegistry.fetch_index（mock httpx）
  - SkillRegistry.search（关键词、分类过滤）
  - SkillRegistry.get_skill
  - SkillRegistry.list_skills
  - SkillRegistry.install_skill（mock SkillInstaller）
  - SkillRegistry.uninstall_skill（mock SkillInstaller）
  - SkillRegistry.check_updates
  - 缓存过期逻辑
  - 错误处理：网络异常、无效 JSON、索引版本不兼容
- **验收**: `cd backend && make test` 全部通过

## 验收标准
- [ ] SkillManifest, SkillIndex, SkillRegistryEntry, MarketplaceConfig 模型定义完成
- [ ] SkillRegistry 核心方法实现（fetch_index, search, list, install, uninstall, check_updates）
- [ ] GitHub Repo + JSON Index 拉取和缓存实现
- [ ] 安装/卸载使用 `SkillInstaller`（T17 创建），不直接调用底层函数
- [ ] marketplace 配置段添加到 config.example.yaml
- [ ] 搜索支持关键词和分类过滤
- [ ] 单元测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | SkillManifest 校验 | 必填字段缺失时校验失败 |
| 单元测试 | SkillIndex 解析 | 正确解析 JSON |
| 单元测试 | fetch_index（首次） | httpx 请求被调用，index 被缓存 |
| 单元测试 | fetch_index（缓存有效） | 不发起新请求 |
| 单元测试 | fetch_index（缓存过期） | 发起新请求 |
| 单元测试 | search("search") | 返回匹配技能 |
| 单元测试 | search(category=development) | 返回分类过滤结果 |
| 单元测试 | install_skill | SkillInstaller.install 被调用 |
| 单元测试 | uninstall_skill | SkillInstaller.uninstall 被调用 |
| 单元测试 | check_updates | 返回可更新列表 |
| 单元测试 | 网络异常 | 抛出合适异常 |
| 单元测试 | 无效 JSON | 抛出解析异常 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| GitHub raw URL 限流 | 中 | 缓存 + 指数退避重试 |
| skills-index.json 格式变更 | 低 | 版本号字段，兼容性检查 |
| SkillInstaller 接口变更（T17 未完成） | 低 | T26 依赖 T17，确保顺序执行 |
| 大量技能索引内存占用 | 低 | 首版规模小（<100），后续可分页 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第11节（技能市场）
- `deerflow/skills/installer.py`（现有安装函数，T17 将创建 `SkillInstaller` 类封装）
