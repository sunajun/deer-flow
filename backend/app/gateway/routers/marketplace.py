from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deerflow.marketplace import MarketplaceConfig, SkillCategory, SkillRegistry
from deerflow.skills.installer import SkillAlreadyExistsError, SkillSecurityScanError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

_registry: SkillRegistry | None = None


def _get_registry() -> SkillRegistry:
    global _registry
    if _registry is not None:
        return _registry
    _registry = SkillRegistry(MarketplaceConfig())
    return _registry


class MarketplaceSkillSummary(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    category: str
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    installed: bool = False
    installed_version: str | None = None


class MarketplaceSkillListResponse(BaseModel):
    skills: list[MarketplaceSkillSummary]
    total: int
    page: int
    page_size: int


class MarketplaceSkillDetail(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    category: str
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    homepage: str = ""
    repository: str = ""
    min_platform_version: str = ""
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    changelog: str = ""
    installed: bool = False
    installed_version: str | None = None


class CategoryItem(BaseModel):
    category: str
    count: int


class CategoryListResponse(BaseModel):
    categories: list[CategoryItem]


class UpdateCheckResponse(BaseModel):
    updates: list[dict]


class RefreshResponse(BaseModel):
    success: bool = True
    message: str = "Index refreshed"


class InstallResponse(BaseModel):
    success: bool = True
    skill_id: str
    message: str = "Skill installed"


class UninstallResponse(BaseModel):
    success: bool = True
    skill_id: str
    message: str = "Skill uninstalled"


class UpdateSkillResponse(BaseModel):
    success: bool = True
    skill_id: str
    message: str = "Skill updated"


def _entry_to_summary(entry) -> MarketplaceSkillSummary:
    m = entry.manifest
    return MarketplaceSkillSummary(
        skill_id=m.skill_id,
        name=m.name,
        description=m.description,
        version=m.version,
        category=m.category.value,
        tags=m.tags,
        author=m.author,
        installed=entry.installed,
        installed_version=entry.installed_version,
    )


def _entry_to_detail(entry) -> MarketplaceSkillDetail:
    m = entry.manifest
    return MarketplaceSkillDetail(
        skill_id=m.skill_id,
        name=m.name,
        description=m.description,
        version=m.version,
        category=m.category.value,
        tags=m.tags,
        author=m.author,
        homepage=m.homepage,
        repository=m.repository,
        min_platform_version=m.min_platform_version,
        dependencies=m.dependencies,
        permissions=m.permissions,
        changelog=m.changelog,
        installed=entry.installed,
        installed_version=entry.installed_version,
    )


@router.get("/skills", response_model=MarketplaceSkillListResponse)
async def list_marketplace_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    query: str | None = Query(None),
):
    registry = _get_registry()
    try:
        cat = SkillCategory(category) if category else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}") from None

    try:
        if query:
            entries = await registry.search(query, category=cat)
        else:
            entries = await registry.list_skills(category=cat)
    except Exception as e:
        logger.error("Failed to list marketplace skills: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list skills: {str(e)}") from None

    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]

    return MarketplaceSkillListResponse(
        skills=[_entry_to_summary(e) for e in page_entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/skills/{skill_id}", response_model=MarketplaceSkillDetail)
async def get_marketplace_skill(skill_id: str):
    registry = _get_registry()
    try:
        entry = await registry.get_skill(skill_id)
    except Exception as e:
        logger.error("Failed to get marketplace skill %s: %s", skill_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}") from None

    if entry is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found in marketplace")
    return _entry_to_detail(entry)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories():
    registry = _get_registry()
    try:
        cats = await registry.get_categories()
    except Exception as e:
        logger.error("Failed to list categories: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list categories: {str(e)}") from None
    return CategoryListResponse(categories=[CategoryItem(**c) for c in cats])


@router.post("/skills/{skill_id}/install", response_model=InstallResponse)
async def install_marketplace_skill(skill_id: str):
    registry = _get_registry()
    try:
        await registry.install_skill(skill_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except SkillSecurityScanError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error("Failed to install skill %s: %s", skill_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {str(e)}") from None
    return InstallResponse(skill_id=skill_id)


@router.post("/skills/{skill_id}/uninstall", response_model=UninstallResponse)
async def uninstall_marketplace_skill(skill_id: str):
    registry = _get_registry()
    try:
        await registry.uninstall_skill(skill_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error("Failed to uninstall skill %s: %s", skill_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to uninstall skill: {str(e)}") from None
    return UninstallResponse(skill_id=skill_id)


@router.get("/updates", response_model=UpdateCheckResponse)
async def check_marketplace_updates():
    registry = _get_registry()
    try:
        updates = await registry.check_updates()
    except Exception as e:
        logger.error("Failed to check updates: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check updates: {str(e)}") from None
    return UpdateCheckResponse(updates=updates)


@router.post("/skills/{skill_id}/update", response_model=UpdateSkillResponse)
async def update_marketplace_skill(skill_id: str):
    registry = _get_registry()
    try:
        await registry.update_skill(skill_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except SkillSecurityScanError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error("Failed to update skill %s: %s", skill_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}") from None
    return UpdateSkillResponse(skill_id=skill_id)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_marketplace_index():
    registry = _get_registry()
    registry._index = None
    registry._index_fetched_at = None
    try:
        await registry.fetch_index()
    except Exception as e:
        logger.error("Failed to refresh marketplace index: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to refresh index: {str(e)}") from None
    return RefreshResponse()
