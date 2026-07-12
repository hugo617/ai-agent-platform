"""Customer endpoints — global identity + per-tenant profile.

Two access patterns, two permission guards:

- **Store view** (``/customers/profiles/...``): tenant-scoped CRUD on this
  store's profiles. Guarded by ``require_permission('customers', act)``;
  super_admin also sees all stores (the service splits on platform_role).
- **HQ view** (``/customers/`` list + ``/customers/{id}/aggregate``):
  cross-store aggregation, guarded by ``require_super_admin()``.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission, require_super_admin
from app.core.database import get_db
from app.schemas.customer import (
    CustomerProfileCreate,
    CustomerProfileRead,
    CustomerProfileUpdate,
    CustomerRead,
)
from app.services.customer_service import CustomerService
from app.services.errors import NotFoundError

router = APIRouter(prefix="/customers", tags=["customers"])


def _http_exc(e: ValueError) -> HTTPException:
    """Map a service ValueError to the right HTTP status by exception type."""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ----------------------------------------------------------- HQ view (super_admin)


@router.get(
    "/",
    response_model=list[CustomerRead],
    dependencies=[Depends(require_super_admin())],
)
async def list_customers_hq(
    db: AsyncSession = Depends(get_db),
) -> list[CustomerRead]:
    """Cross-store customer list with all profiles (super_admin only)."""
    return await CustomerService(db).list_customers_hq()


@router.get(
    "/{customer_id}/aggregate",
    response_model=CustomerRead,
    dependencies=[Depends(require_super_admin())],
)
async def get_customer_aggregate(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """One customer with every store's profile (super_admin only)."""
    try:
        return await CustomerService(db).get_customer_aggregate(customer_id)
    except ValueError as e:
        raise _http_exc(e) from e


# ---------------------------------------------------- store view (tenant-scoped)


@router.get(
    "/profiles/",
    response_model=list[CustomerProfileRead],
    dependencies=[Depends(require_permission("customers", "read"))],
)
async def list_profiles(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerProfileRead]:
    """List customer profiles. Store users see their tenant; super_admin sees all."""
    return await CustomerService(db).list_profiles(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.post(
    "/profiles/",
    response_model=CustomerProfileRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("customers", "create"))],
)
async def create_profile(
    payload: CustomerProfileCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerProfileRead:
    """Create a customer in this store (reuses global identity if it exists)."""
    try:
        return await CustomerService(db).create_profile(
            user.user_id, user.tenant_id, payload, platform_role=user.platform_role
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.put(
    "/profiles/{profile_id}",
    response_model=CustomerProfileRead,
    dependencies=[Depends(require_permission("customers", "update"))],
)
async def update_profile(
    profile_id: str,
    payload: CustomerProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerProfileRead:
    """Update a store profile (syncs global-identity fields to the Customer)."""
    try:
        return await CustomerService(db).update_profile(
            user.user_id,
            user.tenant_id,
            profile_id,
            payload,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.delete(
    "/profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("customers", "delete"))],
)
async def delete_profile(
    profile_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a store profile. The global Customer identity is preserved."""
    try:
        await CustomerService(db).delete_profile(
            user.user_id,
            user.tenant_id,
            profile_id,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e
