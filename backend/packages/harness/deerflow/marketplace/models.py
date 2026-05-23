from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SkillCategory(StrEnum):
    productivity = "productivity"
    development = "development"
    data = "data"
    communication = "communication"
    automation = "automation"
    other = "other"


class SkillManifest(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    category: SkillCategory
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    homepage: str = ""
    repository: str = ""
    archive_url: str = ""
    checksum: str = ""
    min_platform_version: str = ""
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    changelog: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkillIndex(BaseModel):
    version: str = "1.0"
    updated_at: datetime
    skills: list[SkillManifest] = Field(default_factory=list)


class SkillRegistryEntry(BaseModel):
    manifest: SkillManifest
    installed: bool = False
    installed_version: str | None = None
    local_path: str | None = None


class MarketplaceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    index_url: str = ""
    cache_ttl: int = 3600
    auto_update_check: bool = True
    trusted_sources: list[str] = Field(default_factory=list)
