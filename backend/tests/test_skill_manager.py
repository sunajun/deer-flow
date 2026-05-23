"""Tests for SkillInstaller and SkillManager lifecycle management."""

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.skills.installer import (
    SkillAlreadyExistsError,
    SkillInstaller,
    SkillSecurityScanError,
)
from deerflow.skills.manager import SkillManager
from deerflow.skills.security_scanner import ScanResult
from deerflow.skills.storage import get_or_new_skill_storage


def _skill_content(name: str, description: str = "Demo skill") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"


def _make_skill_archive(tmp_path: Path, name: str, content: str | None = None) -> Path:
    archive = tmp_path / f"{name}.skill"
    skill_md = content or _skill_content(name)
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{name}/SKILL.md", skill_md)
    return archive


async def _async_scan_allow(*args, **kwargs):
    return ScanResult(decision="allow", reason="ok")


async def _async_scan_block(*args, **kwargs):
    return ScanResult(decision="block", reason="prompt injection")


# ---------------------------------------------------------------------------
# SkillInstaller tests
# ---------------------------------------------------------------------------


class TestSkillInstaller:
    @pytest.fixture(autouse=True)
    def _allow_security_scan(self, monkeypatch):
        monkeypatch.setattr("deerflow.skills.installer.scan_skill_content", _async_scan_allow)

    def test_install_skill(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        archive = _make_skill_archive(tmp_path, "test-skill")

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        result = anyio.run(installer.install, "test-skill", archive)
        assert result["skill_id"] == "test-skill"
        assert (skills_root / "custom" / "test-skill" / "SKILL.md").exists()

    def test_install_already_exists(self, tmp_path):
        skills_root = tmp_path / "skills"
        (skills_root / "custom" / "test-skill").mkdir(parents=True)
        archive = _make_skill_archive(tmp_path, "test-skill")

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        with pytest.raises(SkillAlreadyExistsError, match="already exists"):
            anyio.run(installer.install, "test-skill", archive)

    def test_install_security_scan_fail(self, tmp_path, monkeypatch):
        monkeypatch.setattr("deerflow.skills.installer.scan_skill_content", _async_scan_block)
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        archive = _make_skill_archive(tmp_path, "blocked-skill")

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        with pytest.raises(SkillSecurityScanError, match="Security scan blocked"):
            anyio.run(installer.install, "blocked-skill", archive)

    def test_uninstall_skill(self, tmp_path):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "custom" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("test-skill"), encoding="utf-8")

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        anyio.run(installer.uninstall, "test-skill")
        assert not skill_dir.exists()

    def test_uninstall_nonexistent_skill(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        anyio.run(installer.uninstall, "nonexistent")

    def test_is_installed(self, tmp_path):
        skills_root = tmp_path / "skills"
        (skills_root / "custom" / "test-skill").mkdir(parents=True)

        installer = SkillInstaller(skills_dir=skills_root)
        assert installer.is_installed("test-skill") is True
        assert installer.is_installed("nonexistent") is False

    def test_install_requires_archive_path(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        with pytest.raises(ValueError, match="archive_path is required"):
            anyio.run(installer.install, "test-skill", None)

    def test_install_invalid_extension(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        bad_file = tmp_path / "bad.zip"
        bad_file.write_text("not a skill")

        installer = SkillInstaller(skills_dir=skills_root)
        import anyio

        with pytest.raises(ValueError, match=".skill"):
            anyio.run(installer.install, "test-skill", bad_file)


# ---------------------------------------------------------------------------
# SkillManager tests
# ---------------------------------------------------------------------------


class TestSkillManager:
    @pytest.fixture(autouse=True)
    def _allow_security_scan(self, monkeypatch):
        monkeypatch.setattr("deerflow.skills.installer.scan_skill_content", _async_scan_allow)

    @pytest.fixture()
    def _skills_env(self, tmp_path, monkeypatch):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        (skills_root / "custom").mkdir()
        config_path = tmp_path / "extensions_config.json"
        config_path.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")
        monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(config_path))
        from deerflow.config.extensions_config import reload_extensions_config

        reload_extensions_config()
        return skills_root, config_path

    def test_install_skill(self, tmp_path, _skills_env, monkeypatch):
        skills_root, config_path = _skills_env
        archive = _make_skill_archive(tmp_path, "demo-skill")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        result = anyio.run(manager.install_skill, "demo-skill", archive)
        assert result["skill_id"] == "demo-skill"
        assert (skills_root / "custom" / "demo-skill" / "SKILL.md").exists()

        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        assert config_data["skills"]["demo-skill"]["enabled"] is True

    def test_uninstall_skill(self, tmp_path, _skills_env, monkeypatch):
        skills_root, config_path = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        config_data["skills"]["demo-skill"] = {"enabled": True}
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        anyio.run(manager.uninstall_skill, "demo-skill")
        assert not skill_dir.exists()

    def test_enable_skill(self, tmp_path, _skills_env, monkeypatch):
        skills_root, config_path = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        config_data["skills"]["demo-skill"] = {"enabled": False}
        config_path.write_text(json.dumps(config_data), encoding="utf-8")
        from deerflow.config.extensions_config import reload_extensions_config

        reload_extensions_config()

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        anyio.run(manager.enable_skill, "demo-skill")

        updated = json.loads(config_path.read_text(encoding="utf-8"))
        assert updated["skills"]["demo-skill"]["enabled"] is True

    def test_disable_skill(self, tmp_path, _skills_env, monkeypatch):
        skills_root, config_path = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        config_data["skills"]["demo-skill"] = {"enabled": True}
        config_path.write_text(json.dumps(config_data), encoding="utf-8")
        from deerflow.config.extensions_config import reload_extensions_config

        reload_extensions_config()

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        anyio.run(manager.disable_skill, "demo-skill")

        updated = json.loads(config_path.read_text(encoding="utf-8"))
        assert updated["skills"]["demo-skill"]["enabled"] is False

    def test_list_skills(self, tmp_path, _skills_env, monkeypatch):
        skills_root, _ = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        result = anyio.run(manager.list_skills)
        names = [s["name"] for s in result]
        assert "demo-skill" in names

    def test_enable_for_agent(self, tmp_path, _skills_env, monkeypatch):
        skills_root, config_path = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        anyio.run(lambda: manager.enable_skill("demo-skill", agent_id="agent-1"))

        updated = json.loads(config_path.read_text(encoding="utf-8"))
        assert updated["skills"]["demo-skill"]["enabled"] is True

    def test_check_updates(self, tmp_path, _skills_env, monkeypatch):
        skills_root, _ = _skills_env
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        result = anyio.run(manager.check_updates)
        assert result == []

    def test_update_skill(self, tmp_path, _skills_env, monkeypatch):
        skills_root, config_path = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill", "Old version"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        archive = _make_skill_archive(tmp_path, "demo-skill", _skill_content("demo-skill", "New version"))

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        result = anyio.run(manager.update_skill, "demo-skill", archive)
        assert result["skill_id"] == "demo-skill"

        updated_md = (skills_root / "custom" / "demo-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert "New version" in updated_md

    def test_install_already_exists_raises(self, tmp_path, _skills_env, monkeypatch):
        skills_root, _ = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        archive = _make_skill_archive(tmp_path, "demo-skill")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        with pytest.raises(SkillAlreadyExistsError, match="already exists"):
            anyio.run(manager.install_skill, "demo-skill", archive)

    def test_install_security_scan_fail_raises(self, tmp_path, _skills_env, monkeypatch):
        monkeypatch.setattr("deerflow.skills.installer.scan_skill_content", _async_scan_block)
        skills_root, _ = _skills_env
        archive = _make_skill_archive(tmp_path, "blocked-skill")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        with pytest.raises(SkillSecurityScanError, match="Security scan blocked"):
            anyio.run(manager.install_skill, "blocked-skill", archive)

    def test_get_skill_detail(self, tmp_path, _skills_env, monkeypatch):
        skills_root, _ = _skills_env
        skill_dir = skills_root / "custom" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_skill_content("demo-skill"), encoding="utf-8")
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        detail = anyio.run(manager.get_skill_detail, "demo-skill")
        assert detail is not None
        assert detail["name"] == "demo-skill"

    def test_get_skill_detail_not_found(self, tmp_path, _skills_env, monkeypatch):
        skills_root, _ = _skills_env
        config = SimpleNamespace(
            skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills", use="deerflow.skills.storage.local_skill_storage:LocalSkillStorage"),
        )
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
        monkeypatch.setattr("deerflow.skills.storage.get_or_new_skill_storage", lambda **kw: get_or_new_skill_storage(skills_path=skills_root))

        manager = SkillManager(skills_dir=skills_root)
        import anyio

        detail = anyio.run(manager.get_skill_detail, "nonexistent")
        assert detail is None
