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

from datetime import UTC, date, datetime, time, timedelta
from itertools import groupby

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.repositories.booking import BookingRepository
from app.repositories.customer import CustomerProfileRepository
from app.repositories.device import DeviceRepository
from app.schemas.booking import (
    BookingCreate,
    BookingEndPayload,
    BookingHqRead,
    BookingRead,
    BookingUpdate,
)
from app.services._tenant_target import resolve_target_tenant
from app.services.booking_state import transition as booking_transition
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import (
    is_cross_tenant_viewer,
    is_platform_writer,
    permission_service,
)
from app.services.principal import Principal

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
        # Principal absorbs the role + tenant + scope reasoning that used to be
        # inlined as ``resolve_target_tenant`` / ``is_platform_writer`` /
        # ``is_cross_tenant_viewer`` calls in each method. Holds the same db
        # session object — no duplicate lifecycle (plan-principal-module.md §4.1).
        self.principal = Principal(db)

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
        access = await self.principal.for_read(
            actor_id=actor_id, user_tenant_id=tenant_id,
            obj=self.OBJECT, act="read", platform_role=platform_role,
        )
        if access.is_panorama:
            bookings = await self.repo.list_all_with_meta()
            return [await self._to_hq_read(b) for b in bookings]
        assert access.require is not None  # store branch always sets it
        await permission_service.require(
            actor_id, access.effective_tenant,
            access.require.obj, access.require.act,
            platform_role=platform_role,
        )
        bookings = await self.repo.list_for_tenant(access.effective_tenant)
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
        access = await self.principal.for_read(
            actor_id=actor_id, user_tenant_id=tenant_id,
            obj=self.OBJECT, act="read", platform_role=platform_role,
        )
        if access.is_panorama:
            booking = await self.repo.get_all_with_meta(booking_id)
            if booking is None:
                raise NotFoundError(f"预约不存在: {booking_id}")
            return await self._to_hq_read(booking)
        assert access.require is not None  # store branch always sets it
        await permission_service.require(
            actor_id, access.effective_tenant,
            access.require.obj, access.require.act,
            platform_role=platform_role,
        )
        booking = await self._get_live_booking(booking_id, access.effective_tenant)
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
        # Note(principal-scope): Principal 不覆盖此方法,原因:不用 helper。
        # 纯 store 路径,只有 ``require("read")`` 一行,无 helper 可消除。迁它
        # 只是改写法无 leverage。详见 plan-principal-module.md §4.2。
        # 边界由 ADR-0001(docs/adr/0001-principal-scope-boundary.md)钉死,扩展需先 supersede ADR。
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

    async def get_tenant_schedule(
        self,
        actor_id: str,
        tenant_id: str,
        target_date: date,
        target_tenant_id: str | None = None,
        platform_role: str | None = None,
    ) -> list[BookingHqRead]:
        # Note(principal-scope): Principal 不覆盖此方法,原因:panorama 变体 +
        # 无 require。HQ viewer 用 ``resolve_target_tenant`` 解析目标店 + 故意
        # 不跑 require(schedule-grid 是 bookings:read surface,default perms
        # 全 grant)。跟 for_read 默认带 require 有张力。详见 plan-principal-
        # module.md §4.2。
        # 边界由 ADR-0001(docs/adr/0001-principal-scope-boundary.md)钉死,扩展需先 supersede ADR。
        """One store's bookings for a single calendar day, as ``BookingHqRead``
        — backs ``GET /bookings/schedule-grid`` (booking-schedule-grid slice 02).

        The window is ``[target_date 00:00, target_date+1 00:00)`` in UTC. This
        mirrors the sibling ``GET /devices/{id}/schedule`` convention
        (``app/api/v1/devices.py``): all stored ``scheduled_start_at`` values
        are tz-aware UTC, so a UTC day window is the natural half-open range
        and keeps SQLite tests identical to real Postgres. (A non-UTC store's
        wall-clock day boundary would shift, but the project has no per-tenant
        timezone column today; resolving that is out of scope for this slice.)

        Authorization (read-path analogue of the platform-cross-tenant-write
        rule, plan §4.5 + slice 02 AC):

        - **Cross-tenant viewer** (super_admin / hq_staff): MUST pass
          ``target_tenant_id`` (the store to view); missing → ``BizError`` 400
          (reuses ``resolve_target_tenant`` so the rule is uniform with the
          write path). May view any store. The branch keys off the READ helper
          ``is_cross_tenant_viewer`` (not the write helper
          ``is_platform_writer``) so a future split — e.g. hq_staff read-only —
          keeps this read path serving the wider viewer set.
        - **Store role** (owner / admin / member): MUST NOT pass
          ``target_tenant_id`` — a client-supplied value is a cross-tenant
          forgery attempt → ``PermissionError`` 403 (NOT BizError 400: this is
          the read-path anti-forgery surface, and 403 matches the project's
          "store role reaches beyond its tenant" vocabulary). The effective
          target is always ``tenant_id`` (the caller's own).

        There is intentionally NO per-tenant ``permission_service.require``:
        the schedule-grid is a ``bookings:read`` surface and the default perms
        grant every tenant role ``bookings:read`` (member included), so a
        require would always pass and add nothing. Cross-tenant isolation is
        enforced structurally — the resolved target tenant is the ONLY tenant
        the repo query touches.
        """
        if is_cross_tenant_viewer(platform_role):
            # Cross-tenant viewer (super_admin / hq_staff): target must come
            # from the query param. Reuses ``resolve_target_tenant`` so the
            # "missing target → 400" rule is the same as on the write path
            # (``resolve_target_tenant`` branches on ``is_platform_writer``
            # internally, which today covers the same role set). Uses the READ
            # helper ``is_cross_tenant_viewer`` (not the write helper
            # ``is_platform_writer``) so if the two role sets ever diverge —
            # e.g. hq_staff becomes read-only — this read path keeps serving
            # the wider viewer set.
            effective_tenant = resolve_target_tenant(
                tenant_id, target_tenant_id, platform_role
            )
        else:
            # Store role: tenant_id is the caller's own. A client-supplied
            # target_tenant_id is a cross-tenant forgery → 403.
            if target_tenant_id is not None:
                raise PermissionError(
                    "门店角色不可指定目标租户(tenant_id)"
                )
            effective_tenant = resolve_target_tenant(
                tenant_id, None, platform_role
            )

        # Calendar-day window in UTC. ``combine`` with ``time.min``/``time.max``
        # would give 23:59:59.999999; we want a clean half-open [00:00, +1d 00:00)
        # so the endpoint matches the AC exactly.
        range_start = datetime.combine(target_date, time.min, tzinfo=UTC)
        range_end = datetime.combine(
            target_date + timedelta(days=1), time.min, tzinfo=UTC
        )
        bookings = await self.repo.list_for_tenant_schedule(
            effective_tenant, range_start, range_end
        )
        return [await self._to_hq_read(b) for b in bookings]

    async def list_my_bookings(
        self, customer_id: str | None
    ) -> list[BookingRead]:
        # Note(principal-scope): Principal 不覆盖此方法,原因:customer
        # principal 读路径。无 tenant 概念,按 customer_id 全局查。Principal
        # 的 actor+tenant+platform_role 三元组不适用。详见 plan-principal-
        # module.md §4.2。
        # 边界由 ADR-0001(docs/adr/0001-principal-scope-boundary.md)钉死,扩展需先 supersede ADR。
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
        them has those keys dropped by Pydantic.

        Platform writers (super_admin / hq_staff) skip the casbin require and
        target the store named by ``payload.tenant_id`` (required); store roles
        omit it (anti-forgery, see ``resolve_target_tenant``).
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=payload.tenant_id,
            obj=self.OBJECT, act="create", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        await self._assert_device_in_tenant(effective_tenant, payload.device_id)
        await self._assert_customer_in_tenant(
            effective_tenant, payload.customer_id
        )
        self._assert_window_valid(
            payload.scheduled_start_at, payload.scheduled_end_at
        )
        await self._assert_no_overlap(
            effective_tenant, payload.device_id, payload.scheduled_start_at,
            payload.scheduled_end_at,
        )
        booking = Booking(
            tenant_id=effective_tenant,
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
        fresh = await self.repo.get_for_tenant(booking.id, effective_tenant)
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
        recreate). Time changes re-run the overlap check excluding self.

        Platform writers target the store named by ``payload.tenant_id``;
        store roles omit it (anti-forgery).
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=payload.tenant_id,
            obj=self.OBJECT, act="update", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        booking = await self._get_live_booking(booking_id, effective_tenant)
        if booking.status not in _MUTABLE_STATUSES:
            raise BizError(
                f"仅 pending 状态的预约可修改,当前状态: {booking.status}"
            )

        data = payload.model_dump(exclude_unset=True)
        # ``tenant_id`` is a request-scoped routing field (which store to write
        # into), NOT an updatable column — drop it before setattr loop. The
        # booking's tenant is already locked by ``_get_live_booking`` above.
        data.pop("tenant_id", None)

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
                effective_tenant, data["customer_id"]
            )
        await self._assert_no_overlap(
            effective_tenant,
            booking.device_id,
            new_start,
            new_end,
            exclude_id=booking_id,
        )

        for key, value in data.items():
            setattr(booking, key, value)
        await self.db.flush()
        await self.db.commit()
        fresh = await self.repo.get_for_tenant(booking_id, effective_tenant)
        assert fresh is not None
        return await self._to_read(fresh)

    async def cancel(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        *,
        target_tenant_id: str | None = None,
        platform_role: str | None = None,
    ) -> bool:
        """Transition a booking to ``cancelled``. Returns ``already_cancelled``
        — True if the booking was already cancelled (idempotent no-op, no DB
        write), False if this call performed the transition.

        Idempotency (D9 + acceptance criterion E): re-cancelling an already-
        cancelled booking is a no-op that still returns 204, mirroring the
        DELETE-is-idempotent convention used by device unbind. The state flip
        itself goes through :func:`booking_state.transition` — the only legal
        ``cancel`` edge is ``pending → cancelled`` (plan-booking-state-cancel
        §4.0 D1); any other non-pending state (in_service / done / no_show /
        confirmed-placeholder) is refused by the state table with
        ``InvalidTransition`` → 400, unifying the error vocabulary with
        ``start`` / ``end`` / ``no_show`` (D4 — previously this raised a plain
        ``BizError``; status code unchanged).

        Platform writers target ``target_tenant_id`` (cancel is a POST action
        with no body, so the tenant_id rides as a query param at the router);
        store roles omit it (anti-forgery).

        Ordering NOTE (plan §8 Out of Scope): cancel keeps the original
        ``require`` → ``_get_live_booking`` order (NOT the ``get → require``
        order start/end/no_show use). Aligning is left to the separate
        ``booking-action-order-unify`` feature.
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=target_tenant_id,
            obj=self.OBJECT, act="delete", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        booking = await self._get_live_booking(booking_id, effective_tenant)
        if booking.status == "cancelled":
            return True
        booking.status = booking_transition(booking.status, "cancel")
        await self.db.flush()
        await self.db.commit()
        return False

    # ------------------------------------------------- lifecycle actions
    #
    # device-poweron slice 01: ``start`` / ``end`` / ``no_show`` drive the
    # booking through its active lifecycle. Each method is a thin orchestration
    # over :func:`booking_state.transition` — the state graph lives in exactly
    # one place, the Service only adds persistence + permission/ownership
    # checks. All three share the same shape:
    #
    #   1. resolve the tenant-scoped booking (cross-tenant → NotFoundError 404)
    #   2. enforce the caller-specific authorization (see each method's note)
    #   3. run the state machine; illegal edge → InvalidTransition → 400
    #   4. write the side-effect column(s) the action owns
    #
    # The ``start`` method is the only one that branches on caller kind
    # (customer vs store-staff); ``end`` / ``no_show`` are store-staff-only and
    # share a single authorization path (plan §0 D5/D6/D7).

    async def start(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        *,
        platform_role: str | None = None,
        customer_id: str | None = None,
        target_tenant_id: str | None = None,
    ) -> BookingRead:
        # Note(principal-scope): Principal 不覆盖此方法,原因:三叉 customer
        # principal。customer 分支走 ownership check(``booking.customer_id ==
        # customer_id``)是业务校验,不是角色判断;Principal 的
        # actor+tenant+platform_role 三元组对 customer 不适用。详见
        # plan-principal-module.md §4.2。
        # 边界由 ADR-0001(docs/adr/0001-principal-scope-boundary.md)钉死,扩展需先 supersede ADR。
        """Transition a booking to ``in_service`` (pending / confirmed →
        in_service), recording ``started_at``.

        Authorization (plan §0 D5/D7, B1): this endpoint serves THREE caller
        kinds and the split lives here in the body (NOT on a router-level
        ``require_permission`` — that would 403 the customer principal before
        it reached this branch, since a customer may carry no tenant role at
        all in production):

        - **Customer principal** (``customer_id is not None``): does NOT call
          ``permission_service.require``. Instead a two-step ownership check
          keyed off the principal's own ``customer_id`` (never request input,
          anti-override): first refuse walk-in bookings
          (``booking.customer_id is None`` → 403, "walk-in 预约仅门店员工可开机"),
          then require ``booking.customer_id == customer_id`` (else 403,
          "无权操作他人预约"). This mirrors the ``/me/bookings`` anti-override
          defence — the identity comes from the token, not the URL/body.
        - **Platform writer** (``is_platform_writer(platform_role)``): skip
          casbin require, treat as enhanced store principal — CAN start a
          walk-in booking (``booking.customer_id is None``). Targets the store
          named by ``target_tenant_id`` (required). Plan §4.5.3 D3-2.
        - **Store principal** (otherwise): calls
          ``permission_service.require(..., "bookings", "update")``. The
          ``:update`` perm is on owner AND admin (so both can start non-walk-in
          bookings), but NOT member → member gets 403. A store principal can
          start a walk-in booking (``booking.customer_id is None``) — that's
          the walk-in flow's whole point (D5).

        Time source: ``datetime.now(UTC)`` (tz-aware, plan §0 D4 v2),
        matching the ``DateTime(timezone=True)`` column definition — not naive
        ``utcnow()``.
        """
        effective_tenant = resolve_target_tenant(
            tenant_id, target_tenant_id, platform_role
        )
        booking = await self._get_live_booking(booking_id, effective_tenant)

        if customer_id is not None:
            # Customer principal — ownership check, no casbin require.
            if booking.customer_id is None:
                raise PermissionError("walk-in 预约仅门店员工可开机")
            if booking.customer_id != customer_id:
                raise PermissionError("无权操作他人预约")
        elif is_platform_writer(platform_role):
            # Platform writer — skip require, treat as enhanced store principal.
            # CAN start a walk-in (booking.customer_id None) — D3-2.
            pass
        else:
            # Store principal — casbin require on bookings:update.
            await permission_service.require(
                actor_id,
                effective_tenant,
                self.OBJECT,
                "update",
                platform_role=platform_role,
            )

        booking.status = booking_transition(booking.status, "start")
        booking.started_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()
        fresh = await self.repo.get_for_tenant(booking_id, effective_tenant)
        assert fresh is not None
        return await self._to_read(fresh)

    async def end(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        *,
        platform_role: str | None = None,
        payload: BookingEndPayload | None = None,
        target_tenant_id: str | None = None,
    ) -> BookingRead:
        """Transition a booking to ``done`` (in_service → done), recording
        ``ended_at`` and optionally ``feedback``.

        Authorization (plan §0 D6, B2): **store owner only** —
        ``permission_service.require(..., "bookings", "delete")``. The
        ``:delete`` perm is on owner but NOT admin (``DEFAULT_ADMIN_PERMS``
        omits it by convention — admin can't delete business records, same rule
        that makes admin unable to cancel). So admin / member / customer all →
        403; only owner passes. This is stricter than ``start`` on purpose:
        ending a service finalizes the billable record.

        Platform writers (super_admin / hq_staff) bypass the owner-only
        require and target ``target_tenant_id`` (required); they can end any
        store's in_service booking. Store roles omit it (anti-forgery).

        ``payload.feedback`` (if non-None) overwrites ``bookings.feedback``;
        ``None`` leaves the column untouched (the caller may end without a
        service note). The column is a SQLAlchemy ``JSON`` (not JSONB), so the
        dict round-trips identically on SQLite and Postgres.

        Ordering (plan §4.5, mirrors ``start``): the tenant-scoped fetch runs
        BEFORE ``require`` so a cross-tenant caller — owner or not — collapses
        to NotFoundError 404 (no enumeration leak, same defence as the start
        path). A within-tenant non-owner still hits ``require`` and gets 403,
        which is fine: they can already see the booking id via their own
        tenant's list, so the 403 leaks nothing. (``cancel`` in
        device-booking uses the opposite order; this slice does NOT change it
        — narrow-scope, leave cancel alone.)
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=target_tenant_id,
            obj=self.OBJECT, act="delete", platform_role=platform_role,
        )
        effective_tenant = access.effective_tenant
        booking = await self._get_live_booking(booking_id, effective_tenant)
        if access.require:
            await permission_service.require(
                actor_id, effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        booking.status = booking_transition(booking.status, "end")
        booking.ended_at = datetime.now(UTC)
        if payload is not None and payload.feedback is not None:
            booking.feedback = payload.feedback
        await self.db.flush()
        await self.db.commit()
        fresh = await self.repo.get_for_tenant(booking_id, effective_tenant)
        assert fresh is not None
        return await self._to_read(fresh)

    async def no_show(
        self,
        actor_id: str,
        tenant_id: str,
        booking_id: str,
        *,
        platform_role: str | None = None,
        target_tenant_id: str | None = None,
    ) -> None:
        """Transition a booking to ``no_show`` (pending / confirmed /
        in_service → no_show). Pure status flip — no timestamp is written
        (plan §0 D4: ``started_at`` / ``ended_at`` are owned by start / end;
        a no-show records nothing about when the absence was judged).

        Authorization is identical to ``end`` (plan §0 D6): owner only via
        ``bookings:delete``. Admin / member / customer → 403. Platform writers
        bypass and target ``target_tenant_id`` (required).

        Ordering mirrors ``end`` / ``start``: tenant-scoped fetch first, so a
        cross-tenant caller gets 404 (not 403) regardless of role — no
        enumeration leak. See ``end`` for the rationale.

        Returns ``None`` — the endpoint maps this to 204 (no body), mirroring
        ``/cancel`` (a state flip carries nothing the client needs to read
        back, unlike ``start`` / ``end`` whose timestamps refresh the UI).
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=target_tenant_id,
            obj=self.OBJECT, act="delete", platform_role=platform_role,
        )
        effective_tenant = access.effective_tenant
        booking = await self._get_live_booking(booking_id, effective_tenant)
        if access.require:
            await permission_service.require(
                actor_id, effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        booking.status = booking_transition(booking.status, "no_show")
        await self.db.flush()
        await self.db.commit()
