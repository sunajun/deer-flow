# T17 - 技能生命周期管理与市场对接

## 元信息
- **任务ID**: T17
- **阶段**: 第3期 - 治理与协同
- **优先级**: P2
- **预估工期**: 3 天
- **依赖任务**: T16（智能体配置，技能绑定到智能体）
- **关联差距**: 差距9 - 统一治理面

## 目标
实现 SkillManager 技能生命周期管理（安装、卸载、启用/禁用、更新），与现有安装函数对接。

## 重要约束

> **`SkillInstaller` 类在 `installer.py` 中不存在**。该文件提供的是独立函数：`safe_extract_skill_archive`、`is_unsafe_zip_member`、`SkillAlreadyExistsError`、`SkillSecurityScanError`、`_scan_skill_archive_contents_or_raise` 等。本任务需要**创建 `SkillInstaller` 类**，封装这些现有函数作为安装流程的核心实现。

## 详细实现步骤

### 步骤1: 创建 SkillInstaller 类
- **文件**: `backend/packages/harness/deerflow/skills/installer.py`
- **操作**: 改造（在现有函数之后追加类定义）
- **内容**: 封装现有函数为面向对象接口
```python
class SkillInstaller:
    """面向对象的技能安装器，封装现有 installer 函数。"""

    def __init__(self, skills_dir: Path | None = None):
        self._skills_dir = skills_dir or get_paths().skills_dir

    async def install(self, skill_id: str, archive_path: Path | None = None) -> dict:
        """安装技能：解压 + 安全扫描 + 移入目标目录。

        复用现有函数：
        - safe_extract_skill_archive() — 安全解压
        - _scan_skill_archive_contents_or_raise() — 安全扫描
        - _move_staged_skill_into_reserved_target() — 原子移入
        """
        target = self._skills_dir / skill_id
        if target.exists():
            raise SkillAlreadyExistsError(f"Skill '{skill_id}' already exists")

        staging = Path(tempfile.mkdtemp(prefix="deerflow_skill_"))
        try:
            with zipfile.ZipFile(archive_path) as zf:
                safe_extract_skill_archive(zf, staging)
            skill_dir = resolve_skill_dir_from_archive(staging)
            await _scan_skill_archive_contents_or_raise(skill_dir, skill_id)
            _move_staged_skill_into_reserved_target(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        return {"skill_id": skill_id, "install_path": str(target)}

    async def uninstall(self, skill_id: str) -> None:
        """卸载技能：删除目录。"""
        target = self._skills_dir / skill_id
        if target.exists():
            shutil.rmtree(target)

    def is_installed(self, skill_id: str) -> bool:
        """检查技能是否已安装。"""
        return (self._skills_dir / skill_id).exists()
```
- **验收**: `SkillInstaller` 类正确封装 `safe_extract_skill_archive`、`SkillAlreadyExistsError` 等现有函数

### 步骤2: 创建 SkillManager
- **文件**: `backend/packages/harness/deerflow/skills/manager.py`
- **操作**: 新建
- **内容**: 技能生命周期管理
```python
class SkillManager:
    def __init__(self):
        self._installed: dict[str, dict] = {}
        self._installer = SkillInstaller()

    async def install_skill(self, skill_id: str, version: str | None = None) -> dict:
        """安装技能，复用 SkillInstaller"""
        result = await self._installer.install(skill_id, archive_path=...)
        self._installed[skill_id] = {
            "version": result.get("version", "latest"),
            "enabled": True,
            "installed_at": datetime.now().isoformat(),
        }
        await self._update_config(skill_id, enable=True)
        return result

    async def uninstall_skill(self, skill_id: str) -> None: ...
    async def enable_skill(self, skill_id: str, agent_id: str | None = None) -> None: ...
    async def disable_skill(self, skill_id: str, agent_id: str | None = None) -> None: ...
    async def list_skills(self) -> list[dict]: ...
    async def get_skill_detail(self, skill_id: str) -> dict | None: ...
    async def check_updates(self, skill_id: str | None = None) -> list[dict]: ...
    async def update_skill(self, skill_id: str, version: str | None = None) -> dict: ...
```
- **验收**: 所有方法可调用，安装复用 `SkillInstaller`

### 步骤3: 实现 enable/disable
- **文件**: `backend/packages/harness/deerflow/skills/manager.py`
- **操作**: 续写
- **内容**: 启用/禁用逻辑
```python
async def enable_skill(self, skill_id: str, agent_id: str | None = None):
    if skill_id in self._installed:
        self._installed[skill_id]["enabled"] = True
    await self._update_config(skill_id, enable=True)

async def disable_skill(self, skill_id: str, agent_id: str | None = None):
    if skill_id in self._installed:
        self._installed[skill_id]["enabled"] = False
    await self._update_config(skill_id, enable=False)
```
- **验收**: 启用/禁用后配置文件更新

### 步骤4: 创建技能 API 路由
- **文件**: `backend/app/gateway/routers/skills.py`
- **操作**: 改造（现有 skills router 可能存在，需检查并扩展）
- **内容**: 7 个端点
```python
router = APIRouter(prefix="/api/skills", tags=["skills"])

@router.get("/market")                    # 技能市场列表
@router.post("/install")                  # 安装技能
@router.delete("/{skill_id}")             # 卸载技能
@router.post("/{skill_id}/enable")        # 启用技能
@router.post("/{skill_id}/disable")       # 禁用技能
@router.get("/check-updates")             # 检查更新
@router.post("/{skill_id}/update")        # 更新技能
```
- **验收**: API 端点可访问

### 步骤5: 注册路由到 Gateway
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `create_app()` 中通过 `app.include_router()` 注册 skills router（如尚未注册）
- **验收**: API 可访问

### 步骤6: 测试
- **文件**: `backend/tests/test_skill_manager.py`
- **操作**: 新建
- **内容**: 技能管理测试
```python
# 测试用例：
# test_install_skill - 安装（验证 SkillInstaller 被调用）
# test_uninstall_skill - 卸载
# test_enable_skill - 启用
# test_disable_skill - 禁用
# test_list_skills - 列表
# test_enable_for_agent - 指定智能体启用
# test_check_updates - 检查更新
# test_update_skill - 更新
# test_install_already_exists - 安装已存在技能抛出 SkillAlreadyExistsError
# test_install_security_scan_fail - 安全扫描失败抛出 SkillSecurityScanError
```
- **验收**: 测试通过

## 验收标准
- [ ] `SkillInstaller` 类创建完成，封装 `safe_extract_skill_archive`、`SkillAlreadyExistsError`、`SkillSecurityScanError` 等现有函数
- [ ] SkillManager 8 个方法实现
- [ ] 安装复用 SkillInstaller，更新 extensions_config.json
- [ ] 启用/禁用全局和指定智能体
- [ ] 7 个 API 端点可访问
- [ ] 测试通过

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | SkillInstaller.install | 调用 safe_extract_skill_archive + 安全扫描 |
| 单元测试 | install | extensions_config.json 更新 |
| 单元测试 | uninstall | 配置移除 |
| 单元测试 | enable/disable | enabled 标志切换 |
| 单元测试 | install 已存在 | 抛出 SkillAlreadyExistsError |
| 单元测试 | install 安全扫描失败 | 抛出 SkillSecurityScanError |
| 集成测试 | API install | 返回成功 |
| 集成测试 | API enable | 状态切换 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| SkillInstaller 与现有函数接口不兼容 | 低 | SkillInstaller 直接封装现有函数，不改变其行为 |
| 并发安装冲突 | 低 | 文件锁 |
| 安全扫描误报 | 中 | 可配置扫描策略 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第9节
- `deerflow/skills/installer.py`（现有安装函数：`safe_extract_skill_archive`、`SkillAlreadyExistsError`、`SkillSecurityScanError`）
- `deerflow/skills/security_scanner.py`（安全扫描器）
