"""Repository for Booking.

``Booking`` is tenant-scoped (carries ``tenant_id``), so
``BookingRepository`` extends ``TenantScopedRepository``. Unlike
``DeviceRepository`` / ``CustomerProfileRepository``, bookings are **not**
soft-deleted (D8): there is no ``is_deleted`` column, so the overrides of
``get_for_tenant`` / ``list_for_tenant`` do NOT add an ``is_deleted`` filter —
they keep the base class's tenant scoping only, and let cancelled bookings
show up in the list (the status field is how a client distinguishes them).

The core read for this feature is overlap detection
(``find_overlap``): left-closed / right-open intervals (D4),
``new_start < existing_end AND existing_start < new_end``, so back-to-back
bookings (one ending 11:00, the next starting 11:00) do NOT conflict. Only
*active* states (pending / confirmed / in_service) reserve a slot —
cancelled / done / no_show have released theirs and are excluded.
``exclude_id`` lets ``update`` skip the booking being rescheduled.

``list_for_device_schedule`` is the per-device windowed read backing the
schedule-grid endpoint (slice 03) — defined here in slice 01 so the repo
surface is complete, but only exercised by slice 03's tests.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.booking import Booking
from app.repositories.base import TenantScopedRepository

# States that still hold their time slot. cancelled / done / no_show have
# released theirs and must NOT participate in overlap detection (a cancelled
# booking's window can be reused immediately).
_ACTIVE_STATES: tuple[str, ...] = ("pending", "confirmed", "in_service")


class BookingRepository(TenantScopedRepository[Booking]):
    """Tenant-scoped CRUD over bookings (no soft delete — D8)."""

    model = Booking

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_for_tenant(
        self, obj_id: str, tenant_id: str
    ) -> Booking | None:
        """A store's booking by id (tenant-scoped; no soft-delete filter).

        Bookings are never soft-deleted, so unlike Device there is no
        ``is_deleted`` clause — cancelled bookings still resolve here (the
        status field carries their state).
        """
        stmt = select(Booking).where(
            Booking.id == obj_id,
            Booking.tenant_id == tenant_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: str) -> list[Booking]:
        """All bookings in a store, newest first (by scheduled start, then
        created_at). Includes cancelled ones — no soft-delete filter."""
        stmt = (
            select(Booking)
            .where(Booking.tenant_id == tenant_id)
            .order_by(Booking.scheduled_start_at.desc(), Booking.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_overlap(
        self,
        tenant_id: str,
        device_id: str,
        new_start: datetime,
        new_end: datetime,
        *,
        exclude_id: str | None = None,
    ) -> Booking | None:
        """Return the first active booking that overlaps ``[new_start,
        new_end)`` on ``device_id`` in ``tenant_id``, or None.

        Left-closed / right-open (D4): ``new_start < existing_end AND
        existing_start < new_end``. Back-to-back bookings (one ends 11:00,
        next starts 11:00) therefore do NOT conflict — 11:00 is the boundary,
        not an overlap. Only active states (pending / confirmed / in_service)
        hold a slot; cancelled / done / no_show are excluded so their windows
        can be reused.

        ``exclude_id`` lets ``update`` (reschedule) skip the booking being
        moved — otherwise a booking would always overlap itself.
        """
        clauses = [
            Booking.tenant_id == tenant_id,
            Booking.device_id == device_id,
            Booking.status.in_(_ACTIVE_STATES),
            Booking.scheduled_start_at < new_end,
            new_start < Booking.scheduled_end_at,
        ]
        if exclude_id is not None:
            clauses.append(Booking.id != exclude_id)
        stmt = select(Booking).where(*clauses).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_device_schedule(
        self,
        tenant_id: str,
        device_id: str,
        range_start: datetime,
        range_end: datetime,
    ) -> list[Booking]:
        """Windowed bookings for one device in ``[range_start, range_end)``
        — backs the schedule-grid endpoint (slice 03). Tenant-scoped: a foreign
        tenant's device returns nothing here (the service turns that into a
        404 via ``_assert_device_in_tenant``). Ordered by scheduled start so
        the day-grouping aggregation is trivial."""
        stmt = (
            select(Booking)
            .where(
                Booking.tenant_id == tenant_id,
                Booking.device_id == device_id,
                Booking.scheduled_start_at >= range_start,
                Booking.scheduled_start_at < range_end,
            )
            .order_by(Booking.scheduled_start_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


# Re-export Base for type hints in callers that need it.
__all__ = ["Base", "BookingRepository"]
