"""Booking service — tenant-scoped CRUD over device-usage reservations.

Within-store path (slice 01): owner / admin can create / read / update /
cancel bookings for their store's devices; member is read-only; cross-tenant
operations collapse to 404 (no enumeration leak — same defence as
DeviceService). HQ panorama, schedule-grid, and the customer own endpoint land
in slices 03 / 04.

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
member read). Slice 03 replaces the router-level read guard with the
endpoint-body HQ branch: cross-tenant viewers (super_admin / hq_staff) skip
the per-tenant ``require`` and instead get the panorama via
``list_all_with_meta`` / ``get_all_with_meta`` → ``BookingHqRead``.

Slice 03 also adds ``get_device_schedule`` — the per-device windowed read
backing the schedule-grid endpoint, aggregated by day into
``dict[date, list[BookingRead]]``. Day aggregation is done in Python
(``itertools.groupby``) rather than SQL ``GROUP BY DATE(...)`` so SQLite
tests and real Postgres behave identically (``DATE()`` semantics drift on
tz-aware datetimes across the two).
"""

# ``from __future__ import annotations`` makes every annotation a lazily-
# evaluated string. Required here because this class defines a method named
# ``list`` (slice 01), which would otherwise shadow the builtin ``list``
# *inside the class body* — and ``get_device_schedule``'s return annotation
# ``dict[date, list[BookingRead]]`` (defined later in the body) would then
# subscript the method, not the builtin, raising
# ``TypeError: 'function' object is not subscriptable`` at class-definition
# time. String annotations defer that lookup to call sites (module scope),
# where ``list`` is still the builtin.
from __future__ import annotations

from datetime import date, datetime
from itertools import groupby

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.repositories.booking import BookingRepository
from app.repositories.customer import CustomerProfileRepository
from app.repositories.device import DeviceRepository
from app.schemas.booking import (
    BookingCreate,
    BookingHqRead,
    BookingRead,
    BookingUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import is_cross_tenant_viewer, permission_service

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

    async def _to_hq_read(self, booking: Booking) -> BookingHqRead:
        """Build the HQ panorama DTO from a booking whose tenant/device/customer
        relationships are already loaded (by ``list_all_with_meta`` /
        ``get_all_with_meta``). Reading ``booking.tenant.name`` here is safe
        because the repository ``selectinload``-ed them — no lazy load, no
        ``MissingGreenlet``.

        ``*_name`` fall back to None if the relationship is unloaded or the
        related row is gone — a walk-in booking has no ``customer``, and a
        booking whose device was hard-deleted (FK SET NULL) has no ``device``;
        the HQ view still shows the booking.

        Note: ``device_name`` is sourced from ``Device.serial_number`` —
        devices have no ``name`` column (``serial_number`` IS their business
        identifier). The field is named ``device_name`` for frontend symmetry
        with ``tenant_name`` / ``customer_name``.
        """
        data = {c.name: getattr(booking, c.name) for c in booking.__table__.columns}
        tenant = getattr(booking, "tenant", None)
        device = getattr(booking, "device", None)
        customer = getattr(booking, "customer", None)
        data["tenant_name"] = getattr(tenant, "name", None)
        # Device's display identifier is its serial number.
        data["device_name"] = getattr(device, "serial_number", None)
        data["customer_name"] = getattr(customer, "name", None)
        return BookingHqRead.model_validate(data)

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
    ) -> list[BookingRead] | list[BookingHqRead]:
        """Bookings for the caller.

        Cross-tenant viewers (super_admin / hq_staff) get the HQ panorama —
        every tenant's bookings as ``BookingHqRead`` with tenant/device/
        customer names. No per-tenant ``require`` runs for them: hq_staff has
        no tenant role, and the read bypass lives in
        ``permission_service.check`` (``hq_staff`` + ``read`` short-circuit;
        ``super_admin`` bypass).

        Tenant roles (owner / admin / member) get their own tenant's bookings
        as ``BookingRead`` after ``require("bookings", "read")`` (member
        passes because the default perms grant ``bookings:read``).
        """
        if is_cross_tenant_viewer(platform_role):
            bookings = await self.repo.list_all_with_meta()
            return [await self._to_hq_read(b) for b in bookings]
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
    ) -> BookingRead | BookingHqRead:
        """One booking for the caller.

        Cross-tenant viewers (super_admin / hq_staff) read any tenant's
        booking via ``get_all_with_meta`` → ``BookingHqRead``; a missing id
        collapses to NotFoundError (404), same surface as the within-store
        path (no enumeration leak).

        Tenant roles go through ``require("bookings", "read")`` +
        ``_get_live_booking`` (tenant-scoped, so a foreign booking is 404).
        """
        if is_cross_tenant_viewer(platform_role):
            booking = await self.repo.get_all_with_meta(booking_id)
            if booking is None:
                raise NotFoundError(f"预约不存在: {booking_id}")
            return await self._to_hq_read(booking)
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "read",
            platform_role=platform_role,
        )
        booking = await self._get_live_booking(booking_id, tenant_id)
        return await self._to_read(booking)

    async def get_device_schedule(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        range_start: datetime,
        range_end: datetime,
        platform_role: str | None = None,
    ) -> dict[date, list[BookingRead]]:
        """The day-grouped booking schedule for one device, in
        ``[range_start, range_end)``.

        Returns ``{date: [booking, ...]}`` — only days with at least one
        booking appear (empty days are omitted, not keyed to ``[]``; the
        frontend iterates ``Object.keys``). Within each day the bookings are
        ordered by ``scheduled_start_at`` ascending (the repo's order).

        Guard: the device must be a *live* device in the caller's tenant
        (``DeviceRepository.get_for_tenant`` filters ``is_deleted``). A
        foreign tenant's device or a nonexistent id collapses to
        NotFoundError (404) — this is the read-side enumeration defence the
        plan specifies for the schedule endpoint (NOT BizError 400 like the
        write-path device check; reads use 404 so probing "does this device
        exist in another tenant" gets no signal).

        Day aggregation is in Python (``groupby``) not SQL: the repo already
        returns bookings ordered by ``scheduled_start_at`` asc, and
        ``.date()`` on a tz-aware datetime is deterministic across SQLite and
        Postgres (unlike ``func.date()`` / ``DATE()``, whose tz handling
        differs between the two backends).
        """
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "read",
            platform_role=platform_role,
        )
        # Tenant-scoped device existence check → 404 on foreign / missing
        # (read-path enumeration defence; mirrors GET /devices/{id}).
        device = await self.devices.get_for_tenant(device_id, tenant_id)
        if device is None:
            raise NotFoundError(f"设备不存在: {device_id}")
        bookings = await self.repo.list_for_device_schedule(
            tenant_id, device_id, range_start, range_end
        )
        schedule: dict[date, list[BookingRead]] = {}
        # groupby needs sorted input; the repo already returns ascending by
        # scheduled_start_at, so grouping by its .date() is stable.
        for day, group in groupby(
            bookings, key=lambda b: b.scheduled_start_at.date()
        ):
            schedule[day] = [await self._to_read(b) for b in group]
        return schedule

    async def list_my_bookings(
        self, customer_id: str | None
    ) -> list[BookingRead]:
        """The customer-principal's own bookings (slice 04, ``GET /me/bookings``).

        ``customer_id`` is read off the resolved principal by the endpoint —
        it never comes from request input (the plan's anti-override defence
        against "fetch another customer's bookings"). A store-staff token has
        ``customer_id`` None and is rejected here with ``PermissionError`` (→
        403): this is a customer-only surface, and staff read via
        ``GET /bookings/`` instead.

        Returns ``BookingRead`` (NOT ``BookingHqRead``) — a customer only ever
        sees their own rows, so the cross-tenant panorama fields
        (``tenant_name`` / ``device_name`` / ``customer_name``) are pointless;
        the plain within-store shape is what the customer view renders. The
        repo query is customer-scoped and ignores tenancy (a customer is a
        global identity), so a customer with bookings across stores sees all
        of them.
        """
        if customer_id is None:
            raise PermissionError(
                "GET /me/bookings 仅限客户身份;门店员工请使用 GET /bookings/"
            )
        bookings = await self.repo.list_for_customer(customer_id)
        return [await self._to_read(b) for b in bookings]

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
