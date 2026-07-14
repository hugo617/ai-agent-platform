"""Global cross-entity search endpoint.

A read-only aggregator that fans a single query out across agents / customers /
conversations (+ users / tenants for cross-tenant viewers) and groups the hits
by entity type. Like ``/dashboard/overview``, the controller talks to several
repositories directly — this is the accepted read-aggregator exception to the
Controller → Service → Repository chain (each search method still enforces its
own multi-tenant filter in its repository, so isolation is never bypassed).

Permission: every authenticated user may search their accessible scope. Store
users search their own tenant; super_admin / hq_staff search across every
tenant and additionally get users + tenants sections.

Short queries (< 2 chars after strip) return an empty result without touching
the DB — matching the plan's guard against trivial fan-out.
"""

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.repositories.agent import AgentRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.customer import CustomerProfileRepository, CustomerRepository
from app.repositories.tenant import TenantRepository, UserRepository
from app.schemas.search import GlobalSearchResult, SearchResultItem
from app.services.permission_service import is_cross_tenant_viewer

router = APIRouter(prefix="/search", tags=["search"])

# Minimum keyword length. Single-character queries match too much to be useful
# and would fan out to five ILIKE scans — skip them entirely.
MIN_QUERY_LEN = 2


def _item(entity_id: str, label: str | None, entity_type: str) -> SearchResultItem:
    """Build a SearchResultItem, falling back when the label is missing."""
    return SearchResultItem(
        id=entity_id, label=label or entity_id, type=entity_type
    )


@router.get(
    "",
    response_model=GlobalSearchResult,
)
async def global_search(
    q: str = Query(default="", description="Keyword (min 2 chars after strip)"),
    limit_per_type: int = Query(
        default=5, ge=1, le=20, description="Max hits per entity type"
    ),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GlobalSearchResult:
    """Search across agents / customers / conversations (+ users / tenants).

    Store users are scoped to their own tenant; super_admin / hq_staff search
    across every tenant and additionally receive the users + tenants sections.
    Returns grouped lightweight hits; queries shorter than 2 chars return an
    empty result.
    """
    keyword = (q or "").strip()
    if len(keyword) < MIN_QUERY_LEN:
        return GlobalSearchResult()

    cross_tenant = is_cross_tenant_viewer(user.platform_role)

    # Repositories carry the tenant_id filter on their search methods, so the
    # isolation rule (filter in the repository layer) holds even though this
    # endpoint coordinates several of them.
    agent_repo = AgentRepository(db)
    conv_repo = ConversationRepository(db)
    customer_repo = CustomerRepository(db)
    profile_repo = CustomerProfileRepository(db)

    # --- agents ---------------------------------------------------------
    # Cross-tenant viewers see every tenant's agents; store users see theirs.
    if cross_tenant:
        agents_task = agent_repo.search(keyword=keyword, limit=limit_per_type)
    else:
        agents_task = agent_repo.search_for_tenant(
            keyword=keyword, tenant_id=user.tenant_id, limit=limit_per_type
        )

    # --- customers ------------------------------------------------------
    # Cross-tenant viewers search the global Customer table; store users
    # search their tenant's profiles (joined to Customer for name/identity).
    if cross_tenant:
        customers_task = customer_repo.search(
            keyword=keyword, limit=limit_per_type
        )
    else:
        customers_task = profile_repo.search_for_tenant(
            keyword=keyword, tenant_id=user.tenant_id, limit=limit_per_type
        )

    # --- conversations --------------------------------------------------
    # Conversations are private per-user. A store user searches their own
    # chats (title OR message content, via list_for_user's existing search);
    # cross-tenant viewers get a platform-wide title search instead.
    if cross_tenant:
        convs_task = conv_repo.search_all(
            keyword=keyword, limit=limit_per_type
        )
    else:
        convs_task = conv_repo.list_for_user(
            user.tenant_id,
            user.user_id,
            limit=limit_per_type,
            search=keyword,
        )

    agents, customers_or_profiles, convs = await asyncio.gather(
        agents_task, customers_task, convs_task
    )

    result = GlobalSearchResult(
        agents=[_item(a.id, a.name, "agent") for a in agents],
        conversations=[_item(c.id, c.title, "conversation") for c in convs],
    )

    # Customer shape differs by scope: cross-tenant viewers get Customer rows
    # (name on the row); store users get CustomerProfile rows (name is on the
    # joined Customer, fetched per-profile). Both map to the same DTO.
    if cross_tenant:
        result.customers = [
            _item(c.id, c.name, "customer") for c in customers_or_profiles
        ]
    else:
        # Batch-load the joined customer names so store-user hits carry the
        # human-readable name (the profile itself has no name column).
        profile_customers: dict[str, str | None] = {}
        for p in customers_or_profiles:
            c = await customer_repo.get(p.customer_id)
            profile_customers[p.id] = c.name if c is not None else None
        result.customers = [
            _item(pid, name, "customer")
            for pid, name in profile_customers.items()
        ]

    # --- users + tenants (super_admin / hq_staff only) ------------------
    if cross_tenant:
        user_repo = UserRepository(db)
        tenant_repo = TenantRepository(db)
        users, tenants = await asyncio.gather(
            user_repo.search(keyword=keyword, limit=limit_per_type),
            tenant_repo.search(keyword=keyword, limit=limit_per_type),
        )
        result.users = [
            _item(u.id, u.real_name or u.username or u.email, "user")
            for u in users
        ]
        result.tenants = [_item(t.id, t.name, "tenant") for t in tenants]

    return result
