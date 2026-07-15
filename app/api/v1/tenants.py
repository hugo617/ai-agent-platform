"""Tenant endpoints.

Two read scopes:

* ``GET /tenants/``  — the caller's own tenants (any logged-in user).
* ``GET /tenants/all`` — every tenant, platform-wide (super_admin only).

Writes (``POST /``, ``PUT /{id}``) and the detail view (``GET /{id}``) are
super_admin-only: creating / editing stores and inspecting a single store's
membership count are platform-level operations, not tenant-scoped ones.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_super_admin
from app.core.database import get_db
from app.schemas.tenant import TenantCreate, TenantRead, TenantUpdate
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


# --- user-scoped (any logged-in user) -----------------------------------------


@router.get("/", response_model=list[TenantRead])
async def list_my_tenants(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TenantRead]:
    service = TenantService(db)
    tenants = await service.list_user_tenants(user.user_id)
    if not tenants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="you have no tenants; create one first",
        )
    return tenants


# --- platform-level (super_admin only) ----------------------------------------
# NOTE: ``/all`` MUST be declared before ``/{tenant_id}`` — otherwise FastAPI
# would match the literal string "all" as a tenant_id path param.


@router.get(
    "/all",
    response_model=list[TenantRead],
    dependencies=[Depends(require_super_admin())],
)
async def list_all_tenants(
    db: AsyncSession = Depends(get_db),
) -> list[TenantRead]:
    """Platform-wide tenant list with member counts (super_admin only)."""
    service = TenantService(db)
    return await service.list_all()


@router.post(
    "/",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin())],
)
async def create_tenant(
    payload: TenantCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    """Create a tenant (super_admin only).

    The creator becomes the tenant's owner; ``created_by`` records the
    super_admin who performed the creation.
    """
    service = TenantService(db)
    return await service.create_tenant(
        user.user_id, payload, owner_email=user.email, created_by=user.user_id
    )


@router.get(
    "/{tenant_id}",
    response_model=TenantRead,
    dependencies=[Depends(require_super_admin())],
)
async def get_tenant_detail(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    """Tenant detail with member_count (super_admin only)."""
    service = TenantService(db)
    return await service.get_detail(tenant_id)


@router.put(
    "/{tenant_id}",
    response_model=TenantRead,
    dependencies=[Depends(require_super_admin())],
)
async def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    """Edit a tenant's name/status/description/address (super_admin only)."""
    service = TenantService(db)
    return await service.update(tenant_id, payload)
