"""Booking service — tenant-scoped CRUD over device-usage reservations (slice 01).

This slice delivers the within-store path only: owner / admin can
create / read / update / cancel bookings for their store's devices; member is
read-only; cross-tenant operations collapse to 404 (no enumeration leak —
same defence as DeviceService). HQ panorama, schedule-grid, and the customer
own endpoint land in slices 03 / 04.

Three integrity guards worth calling out (see plan-device-booking.md §4.5):

- ``_assert_no_overlap`` — the time-slot conflict check. Left-closed /
  right-open (D4): a new booking conflicts iff
  ``new_start < existing_end AND existing_start < new_end`` on the same
  device in the same tenant, among *active* states only (pending / confirmed
  / in_service). Conflicts raise ``BizError`` → **400** (D1 — the repo has no
  409 concept; feature_list.json's "409" was a typo, corrected in plan §8).
  Back-to-back bookings (one ends 11:00, next starts 11:00) do NOT conflict.
- ``_assert_device_in_tenant`` — the device must be a *live* device in the
  caller's tenant (reuses ``DeviceRepository.get_for_tenant``, which filters
  ``is_deleted``). A nonexistent device and another tenant's device both
  collapse to the same BizError 400 — no enumeration leak.
- ``_assert_customer_in_tenant`` — when ``customer_id`` is non-None, it must
  have a live ``CustomerProfile`` in the caller's tenant (same check device
  bind uses). Walk-in bookings (customer_id None) skip this (D3).

Status-guard rule (plan §4.5): ``status`` / ``started_at`` / ``ended_at`` /
``feedback`` are never settable via create / update — the create/update
schemas don't carry them, so they cannot leak in. ``status`` moves only via
``cancel`` (pending → cancelled). ``update`` is further restricted to
``pending`` bookings (D10): a cancelled / done / etc. booking is terminal and
cannot be "rescheduled" back to life (and ``device_id`` is immutable on
update — change-device = cancel + recreate).

Permission guards use ``permission_service.require`` (owner / admin write,
member read). Slice 03 will replace the router-level read guard with the
endpoint-body HQ branch; slice 01 keeps read behind ``require_permission(
"bookings", "read")`` at the router.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.repositories.booking import BookingRepository
from app.repositories.customer import CustomerProfileRepository
from app.repositories.device import DeviceRepository
from app.schemas.booking import (
    BookingCreate,
    BookingRead,
    BookingUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import permission_service

# Bookings that may be rescheduled via PUT. Only ``pending`` is mutable
# (D10): once a booking has moved past pending (cancelled / in_service /
# done / no_show / confirmed-placeholder) it is terminal / owned by another
# action endpoint and PUT must refuse. ``confirmed`` is a CHECK placeholder
# this feature never writes, so it's not listed as mutable either.
_MUTABLE_STATUSES: frozenset[str] = frozenset({"pending"})


class BookingService:
    OBJECT = "bookings"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = BookingRepository(db)
        self.devices = DeviceRepository(db)
        self.customers = CustomerProfileRepository(db)

    # ------------------------------------------------------------- helpers

    async def _to_read(self, booking: Booking) -> BookingRead:
        data = {c.name: getattr(booking, c.name) for c in booking.__table__.columns}
        return BookingRead.model_validate(data)

    async def _get_live_booking(
        self, booking_id: str, tenant_id: str
    ) -> Booking:
        """Fetch a booking, enforcing tenancy (no soft-delete — D8).

        Cross-tenant / nonexistent all collapse to the same NotFoundError so
        the API can't be probed for "does this id exist in another tenant"
        (enumeration defence, mirrors ``DeviceService._get_live_device``).
        Bookings are never soft-deleted, so unlike Device there is no
        ``is_deleted`` filter — a cancelled booking still resolves here.
        """
        booking = await self.repo.get_for_tenant(booking_id, tenant_id)
        if booking is None:
            raise NotFoundError(f"预约不存在: {booking_id}")
        return booking

    async def _assert_device_in_tenant(
        self, tenant_id: str, device_id: str
    ) -> None:
        """Raise BizError if ``device_id`` is not a *live* device in this tenant.

        ``DeviceRepository.get_for_tenant`` already filters ``is_deleted``,
        so a soft-deleted device returns None — same path as nonexistent / a
        foreign tenant's device. All three collapse to one BizError 400 (no
        enumeration leak — mirrors the device cross-tenant → 404 defence on
        the read side, but writes use 400 to match the overlap / customer
        conventions).
        """
        device = await self.devices.get_for_tenant(device_id, tenant_id)
        if device is None:
            raise BizError(f"设备在本门店不存在: {device_id}")

    async def _assert_customer_in_tenant(
        self, tenant_id: str, customer_id: str | None
    ) -> None:
        """Raise BizError if ``customer_id`` is non-None but has no *live*
        ``CustomerProfile`` in this tenant.

        Walk-in bookings (customer_id None) skip this entirely (D3). For a
        bound booking the check is the same one device-bind uses: the global
        ``Customer`` may exist in many stores, so "is this our customer" is
        answered by ``CustomerProfileRepository.get_by_customer_tenant``.
        Nonexistent + cross-tenant both collapse to one BizError 400 (no
        enumeration).
        """
        if customer_id is None:
            return
        profile = await self.customers.get_by_customer_tenant(
            customer_id, tenant_id
        )
        if profile is None:
            raise BizError(f"客户在本门店不存在: {customer_id}")

    async def _assert_no_overlap(
        self,
        tenant_id: str,
        device_id: str,
        new_start,
        new_end,
        *,
        exclude_id: str | None = None,
    ) -> None:
        """Raise BizError (400, NOT 409 — D1) if an active booking on this
        device overlaps ``[new_start, new_end)``.

        ``exclude_id`` lets ``update`` skip the booking being rescheduled.
        See ``BookingRepository.find_overlap`` for the left-closed /
        right-open semantics + the active-states filter.
        """
        clash = await self.repo.find_overlap(
            tenant_id,
            device_id,
            new_start,
            new_end,
            exclude_id=exclude_id,
        )
        if clash is not None:
            raise BizError(
                f"设备时段冲突:该设备在 {new_start.isoformat()} ~ "
                f"{new_end.isoformat()} 已有预约 {clash.id}"
            )

    @staticmethod
    def _assert_window_valid(start, end) -> None:
        """Raise BizError (400) unless ``end > start``.

        This is the service-layer enforcement of the ``scheduled_end_at >
        scheduled_start_at`` invariant. It can't be a Pydantic
        ``model_validator`` because the raw ``ValueError`` it would raise
        embeds an unserializable exception object in the 422 error ``ctx``
        (see ``BookingCreate`` docstring / ``TenantConfigUpdate.theme_color``
        for the same hazard). A ``BizError`` serializes to a clean 400.
        """
        if end <= start:
            raise BizError("scheduled_end_at 必须晚于 scheduled_start_at")

    # ----------------------------------------------------------------- read

    async def list(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[BookingRead]:
        """All bookings in the caller's tenant (slice 01 — within-store only).

        Slice 03 will add the HQ panorama branch (cross-tenant viewers).
        """
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "read",
            platform_role=platform_role,
        )
        bookings = await self.repo.list_for_tenant(tenant_id)
        return [await self._to_read(b) for b in bookings]

    async def get(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        platform_role: str | None = None,
    ) -> BookingRead:
        """One booking for the caller. A foreign tenant's id collapses to
        NotFoundError (404) — no enumeration leak."""
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "read",
            platform_role=platform_role,
        )
        booking = await self._get_live_booking(booking_id, tenant_id)
        return await self._to_read(booking)

    # ---------------------------------------------------------------- write

    async def create(
        self,
        actor_id: str,
        tenant_id: str,
        payload: BookingCreate,
        platform_role: str | None = None,
    ) -> BookingRead:
        """Create a booking. New bookings always start ``pending`` — the
        ``status`` / ``started_at`` / ``ended_at`` / ``feedback`` fields are
        not on ``BookingCreate`` (status-guard rule), so a client sending
        them has those keys dropped by Pydantic."""
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "create",
            platform_role=platform_role,
        )
        await self._assert_device_in_tenant(tenant_id, payload.device_id)
        await self._assert_customer_in_tenant(tenant_id, payload.customer_id)
        self._assert_window_valid(
            payload.scheduled_start_at, payload.scheduled_end_at
        )
        await self._assert_no_overlap(
            tenant_id, payload.device_id, payload.scheduled_start_at,
            payload.scheduled_end_at,
        )
        booking = Booking(
            tenant_id=tenant_id,
            device_id=payload.device_id,
            customer_id=payload.customer_id,
            created_by=actor_id,
            # status defaults to "pending" via the model + DB server_default;
            # never read from the payload.
            scheduled_start_at=payload.scheduled_start_at,
            scheduled_end_at=payload.scheduled_end_at,
            notes=payload.notes,
        )
        await self.repo.add(booking)
        await self.db.commit()
        # Re-fetch so server defaults (created_at/updated_at/status) are loaded
        # — commit expires the ORM object and reading attributes directly
        # would trigger a lazy async load (MissingGreenlet).
        fresh = await self.repo.get_for_tenant(booking.id, tenant_id)
        assert fresh is not None  # just created, must exist
        return await self._to_read(fresh)

    async def update(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        payload: BookingUpdate,
        platform_role: str | None = None,
    ) -> BookingRead:
        """Reschedule / re-note a booking. Only ``pending`` bookings are
        mutable (D10); ``device_id`` is immutable (change-device = cancel +
        recreate). Time changes re-run the overlap check excluding self."""
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "update",
            platform_role=platform_role,
        )
        booking = await self._get_live_booking(booking_id, tenant_id)
        if booking.status not in _MUTABLE_STATUSES:
            raise BizError(
                f"仅 pending 状态的预约可修改,当前状态: {booking.status}"
            )

        data = payload.model_dump(exclude_unset=True)

        # Resolve the effective window (mix of current + patched values) so
        # the overlap check sees the post-update slot, not the pre-update one.
        new_start = data.get("scheduled_start_at", booking.scheduled_start_at)
        new_end = data.get("scheduled_end_at", booking.scheduled_end_at)
        # Defensive: a single-side patch (only start, or only end) can invert
        # the window against the stored value, so re-validate the effective
        # pair here (the create path validates the full pair).
        self._assert_window_valid(new_start, new_end)

        if "customer_id" in data:
            await self._assert_customer_in_tenant(
                tenant_id, data["customer_id"]
            )
        await self._assert_no_overlap(
            tenant_id,
            booking.device_id,
            new_start,
            new_end,
            exclude_id=booking_id,
        )

        for key, value in data.items():
            setattr(booking, key, value)
        await self.db.flush()
        await self.db.commit()
        fresh = await self.repo.get_for_tenant(booking_id, tenant_id)
        assert fresh is not None
        return await self._to_read(fresh)

    async def cancel(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        platform_role: str | None = None,
    ) -> bool:
        """Transition a booking to ``cancelled``. Returns ``already_cancelled``
        — True if the booking was already cancelled (idempotent no-op, no DB
        write), False if this call performed the transition.

        Idempotency (D9 + acceptance criterion E): re-cancelling an already-
        cancelled booking is a no-op that still returns 204, mirroring the
        DELETE-is-idempotent convention used by device unbind. Cancelling a
        booking in any *other* non-pending state (in_service / done / no_show
        / confirmed-placeholder) is refused with BizError 400 — those states
        are owned by device-poweron's action endpoints and must not be
        reachable from here.
        """
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "delete",
            platform_role=platform_role,
        )
        booking = await self._get_live_booking(booking_id, tenant_id)
        if booking.status == "cancelled":
            return True
        if booking.status != "pending":
            raise BizError(
                f"仅 pending 状态的预约可取消,当前状态: {booking.status}"
            )
        booking.status = "cancelled"
        await self.db.flush()
        await self.db.commit()
        return False
