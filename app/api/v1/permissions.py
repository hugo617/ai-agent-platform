"""Permission matrix endpoints — read-only aggregated views.

Two endpoints back the permission-matrix UI:
  - ``GET /permissions/matrix``    — role × permission current state (SCD2)
  - ``GET /permissions/catalogue`` — all available ``<obj>:<act>`` items

Both are read-only. Editing a cell goes through the existing
``roles/{role_id}/permissions`` grant/revoke endpoints (see ``roles.py``), which
write the SCD2 source and resync casbin; this module only reads it back.

Access requires ``roles:read`` — anyone who can see roles can see the matrix
(owner/admin/member all hold it). Tenant scoping happens in the repositories.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.rbac import PermissionItem, PermissionMatrix
from app.services.permission_service import permission_service

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get(
    "/matrix",
    response_model=PermissionMatrix,
    dependencies=[Depends(require_permission("roles", "read"))],
)
async def get_permission_matrix(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PermissionMatrix:
    """Aggregated role × permission matrix for the caller's tenant."""
    return await permission_service.get_matrix(db, user.tenant_id)


@router.get(
    "/catalogue",
    response_model=list[PermissionItem],
    dependencies=[Depends(require_permission("roles", "read"))],
)
async def get_permission_catalogue(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PermissionItem]:
    """All permission catalogue items for the caller's tenant."""
    return await permission_service.get_catalogue(db, user.tenant_id)
