from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deerflow.governance.middleware import PermissionMiddleware
from deerflow.governance.models import GovernanceConfig, PermissionRule, RoleType
from deerflow.governance.presets import BUILTIN_ROLES

router = APIRouter(prefix="/api/governance", tags=["governance"])

_governance_config: GovernanceConfig | None = None


def _get_config() -> GovernanceConfig:
    global _governance_config
    if _governance_config is not None:
        return _governance_config
    try:
        from deerflow.config.app_config import get_app_config

        app_cfg = get_app_config()
        raw = getattr(app_cfg, "governance", None)
        if raw is not None and isinstance(raw, dict):
            _governance_config = GovernanceConfig.model_validate(raw)
        else:
            _governance_config = GovernanceConfig(
                roles=BUILTIN_ROLES,
            )
    except Exception:
        _governance_config = GovernanceConfig(roles=BUILTIN_ROLES)
    return _governance_config


def _get_middleware() -> PermissionMiddleware:
    return PermissionMiddleware(_get_config())


@router.get("/roles")
async def list_roles():
    config = _get_config()
    roles = config.roles or BUILTIN_ROLES
    return {"roles": {rt.value: r.model_dump(mode="json") for rt, r in roles.items()}}


@router.put("/roles/{role}")
async def update_role(role: str, permissions: PermissionRule):
    try:
        rt = RoleType(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown role: {role}") from None
    config = _get_config()
    existing = config.roles.get(rt) or BUILTIN_ROLES.get(rt)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Role {role} not found")
    from datetime import UTC, datetime

    existing.permissions = permissions
    existing.updated_at = datetime.now(UTC)
    config.roles[rt] = existing
    return existing.model_dump(mode="json")


@router.get("/permissions")
async def get_permissions(user_id: str | None = None):
    config = _get_config()
    rt = config.default_role
    permissions = (config.roles.get(rt) or BUILTIN_ROLES.get(rt, BUILTIN_ROLES[RoleType.GUEST])).permissions
    return {
        "user_id": user_id,
        "role": rt.value,
        "permissions": permissions.model_dump(),
    }


class CheckAccessRequest(BaseModel):
    role: str
    resource_type: str
    resource_id: str


@router.post("/check-access")
async def check_access(req: CheckAccessRequest):
    try:
        rt = RoleType(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown role: {req.role}") from None
    mw = _get_middleware()
    if req.resource_type == "scene":
        allowed = mw.check_scene_access(rt, req.resource_id)
    elif req.resource_type == "tool":
        allowed = mw.check_tool_access(rt, req.resource_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown resource_type: {req.resource_type}")
    return {"role": req.role, "resource_type": req.resource_type, "resource_id": req.resource_id, "allowed": allowed}
