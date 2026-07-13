"""Dashboard repository — platform-wide totals for the HQ overview.

Kept separate from the entity repos because the HQ overview aggregates across
ALL entity kinds (tenants / users / conversations / agents / customers), which
doesn't belong to any single entity repository. Single-direction dependency
still holds: the service calls this repo; this repo only imports models.

super_admin-only: every method here is cross-tenant. Store-level aggregates
live on their respective entity repos (``ConversationRepository.count_for_tenant``
etc.) — this is the platform-wide counterpart.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, User


class DashboardRepository:
    """Cross-tenant aggregate counts for the super_admin overview."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def tenant_count(self) -> int:
        return int(
            (await self.db.execute(select(func.count()).select_from(Tenant))).scalar_one()
        )

    async def user_count(self) -> int:
        """Count live platform users (across all tenants)."""
        stmt = select(func.count()).select_from(User).where(User.is_deleted.is_(False))
        return int((await self.db.execute(stmt)).scalar_one())
