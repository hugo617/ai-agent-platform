"""Repository for the system audit log (SystemLog).

SystemLog is append-only — there is no soft-delete column on the model, so
unlike Customer/User this repository applies NO ``is_deleted`` predicate.
Multi-tenant isolation is enforced here (the Repository layer, per project
铁律): a non-None ``tenant_id`` filters to that tenant; ``tenant_id=None``
means cross-tenant (super_admin / hq_staff), which the API layer authorises.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import SystemLog
from app.repositories.base import BaseRepository


class SystemLogRepository(BaseRepository[SystemLog]):
    """Read-side query surface over SystemLog rows.

    Writes go through ``LoggingService.record``; this repository only exposes
    filtered, paginated reads.
    """

    model = SystemLog

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    def _apply_filters(
        self,
        stmt,
        *,
        tenant_id: str | None,
        user_id: str | None,
        action: str | None,
        resource_type: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ):
        """Append WHERE predicates for each supplied filter.

        ``tenant_id is None`` is the cross-tenant (super_admin) signal — no
        tenant filter is added in that case. Otherwise the rows are scoped to
        the given tenant (this is THE multi-tenant boundary for audit logs).
        """
        if tenant_id is not None:
            stmt = stmt.where(SystemLog.tenant_id == tenant_id)
        if user_id is not None:
            stmt = stmt.where(SystemLog.user_id == user_id)
        if action is not None:
            stmt = stmt.where(SystemLog.action == action)
        if resource_type is not None:
            stmt = stmt.where(SystemLog.resource_type == resource_type)
        if date_from is not None:
            stmt = stmt.where(SystemLog.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(SystemLog.created_at <= date_to)
        return stmt

    async def list_logs(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SystemLog], int]:
        """Return ``(rows, total)`` for the given filters.

        Newest-first ordering by ``created_at`` (with ``id`` as a deterministic
        tiebreaker so pagination is stable when two rows share a timestamp).
        ``limit``/``offset`` apply only to the row query, not the count.
        """
        base = select(SystemLog)
        filtered = self._apply_filters(
            base,
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            date_from=date_from,
            date_to=date_to,
        )

        rows_stmt = (
            filtered.order_by(SystemLog.created_at.desc(), SystemLog.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.db.execute(rows_stmt)).scalars().all())

        count_stmt = select(func.count()).select_from(filtered.subquery())
        total = int((await self.db.execute(count_stmt)).scalar_one())
        return rows, total
