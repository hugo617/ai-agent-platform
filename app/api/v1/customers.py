"""Customer endpoints — global identity + per-tenant profile.

Two access patterns, two permission guards:

- **Store view** (``/customers/profiles/...``): tenant-scoped CRUD on this
  store's profiles. Guarded by ``require_permission('customers', act)``;
  cross-tenant viewers (super_admin / hq_staff) also see all stores (the
  service splits on ``is_cross_tenant_viewer``).
- **HQ view** (``/customers/`` list + ``/customers/{id}/aggregate``):
  cross-store aggregation, guarded by ``require_cross_tenant_viewer()``
  (super_admin full power + hq_staff read-only HQ panorama).
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    is_cross_tenant_viewer,
    require_cross_tenant_viewer,
    require_permission,
)
from app.core.database import get_db
from app.repositories.usage_event import UsageEventRepository
from app.schemas.customer import (
    CustomerProfileCreate,
    CustomerProfileRead,
    CustomerProfileUpdate,
    CustomerRead,
    CustomerStatistics,
    CustomerUsageRead,
)
from app.services.customer_service import CustomerService
from app.services.permission_service import permission_service

router = APIRouter(prefix="/customers", tags=["customers"])


# ----------------------------------------------- HQ view (super_admin + hq_staff)


@router.get(
    "/",
    response_model=list[CustomerRead],
    dependencies=[Depends(require_cross_tenant_viewer())],
)
async def list_customers_hq(
    db: AsyncSession = Depends(get_db),
) -> list[CustomerRead]:
    """Cross-store customer list with all profiles (super_admin + hq_staff)."""
    return await CustomerService(db).list_customers_hq()


@router.get(
    "/{customer_id}/aggregate",
    response_model=CustomerRead,
    dependencies=[Depends(require_cross_tenant_viewer())],
)
async def get_customer_aggregate(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """One customer with every store's profile (super_admin + hq_staff)."""
    return await CustomerService(db).get_customer_aggregate(customer_id)


# ----------------------------------------------- AI usage attribution (3/4)
# GET /customers/{id}/usage — aggregate AI consumption for a customer.
# Dual view: store users (customers:read) see only this store's service of the
# customer (tenant_id filter); cross-tenant viewers (super_admin / hq_staff)
# see the global aggregate (no tenant filter). Mirrors the list_profiles split.
#
# The guard is inlined (not a router ``dependencies=``) because the two view
# modes need different guards: store mode requires ``customers:read`` while HQ
# mode requires a cross-tenant viewer role — a single dependency can't express
# both. ``permission_service.require`` is called manually for store users;
# super_admin bypasses inside ``check`` (its first-line return True), and
# hq_staff takes the cross_tenant branch.


@router.get(
    "/{customer_id}/usage",
    response_model=CustomerUsageRead,
)
async def get_customer_usage(
    customer_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerUsageRead:
    """Aggregate token usage attributed to a customer (customer 360 "AI 服务").

    Store users get their tenant's slice; cross-tenant viewers get the global
    aggregate. Returns zeros when the customer has no attributed conversations.
    """
    cross_tenant = is_cross_tenant_viewer(user.platform_role)
    if not cross_tenant:
        # Store user: enforce customers:read (super_admin bypasses in check).
        await permission_service.require(
            user.user_id,
            user.tenant_id,
            "customers",
            "read",
            platform_role=user.platform_role,
        )
        scope: str | None = user.tenant_id
    else:
        # Cross-tenant viewer (super_admin / hq_staff): global aggregate.
        scope = None
    repo = UsageEventRepository(db)
    prompt, completion, total, cost_sum, conv_count, last_active = (
        await repo.sum_tokens_for_customer(customer_id, tenant_id=scope)
    )
    return CustomerUsageRead(
        customer_id=customer_id,
        conversation_count=conv_count,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        total_cost=float(cost_sum) if cost_sum else None,
        last_active_at=last_active,
    )


# ---------------------------------------------------- store view (tenant-scoped)


@router.get(
    "/profiles/",
    response_model=list[CustomerProfileRead],
    dependencies=[Depends(require_permission("customers", "read"))],
)
async def list_profiles(
    search: str | None = Query(
        default=None,
        description="Substring match on customer name or identity_key (ILIKE)",
    ),
    status: str | None = Query(
        default=None,
        description="Filter by profile status: active | inactive | vip | blacklist",
    ),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerProfileRead]:
    """List customer profiles, optionally filtered by a name/identity search.

    Store users see their tenant; super_admin sees all. ``search`` matches the
    customer's name or identity_key (case-insensitive substring). ``status``
    optionally narrows to one of the 4 profile states (default: show all).
    """
    return await CustomerService(db).list_profiles(
        user.user_id,
        user.tenant_id,
        platform_role=user.platform_role,
        search=search,
        status_filter=status,
    )


# GET /customers/statistics — aggregate counts for the dashboard card. Dual view:
# store users (customers:read) get this store's profile counts; cross-tenant
# viewers (super_admin / hq_staff) get the global identity counts. The guard is
# inlined (not a router ``dependencies=``) for the same reason as
# ``get_customer_usage``: the two view modes need different guards.
@router.get(
    "/statistics",
    response_model=CustomerStatistics,
)
async def customer_statistics(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerStatistics:
    """Aggregate customer counts (total / active / last_7d_new).

    Store users count their tenant's profiles; cross-tenant viewers count global
    identities. The service splits on ``is_cross_tenant_viewer``.
    """
    cross_tenant = is_cross_tenant_viewer(user.platform_role)
    if not cross_tenant:
        await permission_service.require(
            user.user_id,
            user.tenant_id,
            "customers",
            "read",
            platform_role=user.platform_role,
        )
    return await CustomerService(db).statistics(
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
    return await CustomerService(db).create_profile(
        user.user_id, user.tenant_id, payload, platform_role=user.platform_role
    )


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
    return await CustomerService(db).update_profile(
        user.user_id,
        user.tenant_id,
        profile_id,
        payload,
        platform_role=user.platform_role,
    )


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
    await CustomerService(db).delete_profile(
        user.user_id,
        user.tenant_id,
        profile_id,
        platform_role=user.platform_role,
    )
