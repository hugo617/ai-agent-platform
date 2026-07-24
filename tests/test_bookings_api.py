"""Booking API tests — slice 01 (Booking table + overlap + status-guarded CRUD).

Chapter layout (matches plan-device-booking.md slice 01 acceptance criteria):
- A. owner/admin CRUD — create + list + get + update + cancel, full-field
  assertions; admin can create/update but NOT cancel (cancel reuses the
  delete perm, which admin lacks — mirrors devices).
- B. cross-tenant isolation — bookings in another tenant invisible;
  GET/PUT/cancel → 404 (no enumeration leak).
- C. time-slot overlap (D4 left-closed/right-open, D1 → 400 NOT 409):
  - C1 same device same window overlap → 400
  - C2 back-to-back (one ends 11:00, next starts 11:00) → 201 (no conflict)
  - C3 cancelled booking's slot reusable → 201
  - C4 reschedule (PUT) excludes self → 200
- D. status-guard (schema is the front guard):
  - D1 POST with status=done → created, status still pending
  - D2 PUT with status → ignored (status unchanged)
  - D3 POST with started_at/feedback → ignored (still None)
- E. status transitions (pending↔cancelled):
  - E1 pending → cancel → 204, then GET shows cancelled
  - E2 cancelled → PUT reschedule → 400 (terminal, not mutable)
  - E3 cancelled → cancel again → 204 (idempotent no-op)
- F. permission matrix — member read-only (write → 403); admin no cancel
  (delete perm → 403); unauth → 401.
- G. walk-in (customer_id None) — created 201, GET shows null customer_id.
- H. device SET NULL — soft-deleted device's booking still GETs (FK SET NULL
  keeps the row; device_id stays but the device is gone).
- K. backfill (slice 02): bring pre-existing tenants up to the bookings perm set.
  - K1 fixture: a tenant with NO bookings policies (DB + casbin)
  - K2 run backfill_bookings_perms_for_existing_tenants
  - K3 owner gets bookings:create/read/update/delete + menu:bookings
  - K4 member gets bookings:read + menu:bookings but NOT bookings:create
  - K5 idempotent: re-run backfill, no error, no duplicate grants
  - K6 other existing perms (customers:read, devices:read) untouched
- HQ. panorama (slice 03) — super_admin + hq_staff cross-tenant read with the
  ``BookingHqRead`` panorama fields (tenant_name / device_name / customer_name);
  hq_staff writes (create/update/cancel) → 403.
- SCH. schedule grid (slice 03) — GET /devices/{device_id}/schedule day
  aggregation: same-day bookings grouped under one key; empty days omitted;
  cross-tenant / nonexistent device → 404.

Test-organization note (matches test_devices_api.py): each test uses ONE
client fixture. The conftest seeds bookings:* perms for owner/admin/member
(simulating a backfilled tenant, same rationale as devices) so slice-01 tests
can exercise the CRUD path today; production DEFAULT_*_PERMS gets them in
slice 02.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

AUTH = {"Authorization": "Bearer fake"}

# A fixed reference instant for deterministic window construction. Using a
# far-future date keeps tests independent of "today" and avoids any
# date-filter surprises in future slices.
_BASE = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)


def _window(start_offset_hours: float = 0, duration_hours: float = 1):
    """Build a (start, end) pair offset from _BASE. Returns ISO strings
    suitable for JSON bodies + the aware datetimes for direct ORM seeding."""
    start = _BASE + timedelta(hours=start_offset_hours)
    end = start + timedelta(hours=duration_hours)
    return start, end


# ---------------------------------------------------------------- helpers


async def _seed_model(db_session, **overrides):
    """Insert a DeviceModel row directly (bookings reference devices, which
    reference device_models via FK)."""
    from app.models.device_model import DeviceModel

    defaults = {
        "name": f"M-{overrides.get('name', 'x')}",
        "unit_cost": Decimal("1234.56"),
        "specs": {"form_factor": "chamber"},
    }
    defaults.update(overrides)
    model = DeviceModel(**defaults)
    db_session.add(model)
    await db_session.commit()
    return model


async def _seed_device(db_session, *, tenant_id, model_id, serial, **overrides):
    """Insert a Device row directly (the booking's device_id target)."""
    from app.models.device import Device

    defaults = {
        "tenant_id": tenant_id,
        "model_id": model_id,
        "serial_number": serial,
    }
    defaults.update(overrides)
    device = Device(**defaults)
    db_session.add(device)
    await db_session.commit()
    return device


async def _seed_customer_with_profile(
    db_session, *, tenant_id, name, identity_key=None, **overrides
):
    """Insert a global Customer + a live CustomerProfile in tenant_id.

    Bookings reference the *global* Customer (customers.id), but the service's
    ``_assert_customer_in_tenant`` check needs a live ``CustomerProfile`` in
    the caller's tenant — so a bare global Customer with no profile here would
    fail the create guard. Returns ``(customer, profile)``.
    """
    import uuid

    from app.models.customer import Customer, CustomerProfile

    if identity_key is None:
        identity_key = f"phone-{uuid.uuid4().hex}"
    customer = Customer(name=name, identity_key=identity_key)
    db_session.add(customer)
    await db_session.commit()
    profile = CustomerProfile(
        customer_id=customer.id,
        tenant_id=tenant_id,
        status=overrides.pop("status", "active"),
        **overrides,
    )
    db_session.add(profile)
    await db_session.commit()
    return customer, profile


def _iso(dt) -> str:
    return dt.isoformat()


def _iso_q(dt) -> str:
    """ISO-8601 string safe to embed in a URL query string.

    ``datetime.isoformat()`` on a tz-aware value yields ``...+00:00``, and the
    ``+`` is decoded as a space by query-string parsing → 422. The ``Z``
    suffix is equivalent (UTC) and URL-safe. Used for the schedule endpoint's
    ``start`` / ``end`` query params."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------- A. owner/admin CRUD


@pytest.mark.asyncio
async def test_a_owner_create_list_get_update_cancel(app_client, db_session, test_env):
    """Full CRUD round-trip as the tenant owner. Asserts every field on the
    read DTO so a schema-shape regression (added/renamed field) surfaces."""
    model = await _seed_model(db_session, name="A-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="A-DEV"
    )
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="A-客户"
    )
    start, end = _window(0, 1)

    # create
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "customer_id": customer.id,
            "scheduled_start_at": _iso(start),
            "scheduled_end_at": _iso(end),
            "notes": "首次预约",
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["device_id"] == device.id
    assert body["customer_id"] == customer.id
    assert body["status"] == "pending"  # always starts pending
    assert body["notes"] == "首次预约"
    # Lifecycle placeholders owned by device-poweron are present but None.
    assert body["started_at"] is None
    assert body["ended_at"] is None
    assert body["feedback"] is None
    assert body["created_by"] is not None  # owner user id
    assert "id" in body and "tenant_id" in body
    assert "created_at" in body and "updated_at" in body
    booking_id = body["id"]

    # list
    resp = await app_client.get("/api/v1/bookings/", headers=AUTH)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == booking_id

    # get
    resp = await app_client.get(f"/api/v1/bookings/{booking_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["notes"] == "首次预约"

    # update (reschedule window + notes; device_id immutable)
    new_start, new_end = _window(24, 1)  # next day, no overlap with self
    resp = await app_client.put(
        f"/api/v1/bookings/{booking_id}",
        json={
            "scheduled_start_at": _iso(new_start),
            "scheduled_end_at": _iso(new_end),
            "notes": "改约",
        },
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["notes"] == "改约"
    assert updated["scheduled_start_at"] is not None
    # Unchanged fields preserved.
    assert updated["device_id"] == device.id
    assert updated["status"] == "pending"

    # cancel (pending → cancelled, 204)
    resp = await app_client.post(
        f"/api/v1/bookings/{booking_id}/cancel", headers=AUTH
    )
    assert resp.status_code == 204
    # GET reflects the cancelled status (row stays — no soft delete).
    resp = await app_client.get(f"/api/v1/bookings/{booking_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # List still contains it (cancelled bookings are NOT filtered out).
    resp = await app_client.get("/api/v1/bookings/", headers=AUTH)
    assert any(b["id"] == booking_id for b in resp.json())


@pytest.mark.asyncio
async def test_a_admin_can_create_update_but_not_cancel(
    tenant_admin_client, db_session, test_env
):
    """admin has bookings:read/create/update (not delete). cancel reuses the
    delete perm, so admin CANNOT cancel — mirrors the devices convention."""
    model = await _seed_model(db_session, name="ADM-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="ADM-DEV"
    )
    start, end = _window(0, 1)
    resp = await tenant_admin_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(start),
            "scheduled_end_at": _iso(end),
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    booking_id = resp.json()["id"]

    new_start, new_end = _window(48, 1)
    resp = await tenant_admin_client.put(
        f"/api/v1/bookings/{booking_id}",
        json={
            "scheduled_start_at": _iso(new_start),
            "scheduled_end_at": _iso(new_end),
        },
        headers=AUTH,
    )
    assert resp.status_code == 200

    resp = await tenant_admin_client.get("/api/v1/bookings/", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # admin has no bookings:delete → cancel is 403.
    resp = await tenant_admin_client.post(
        f"/api/v1/bookings/{booking_id}/cancel", headers=AUTH
    )
    assert resp.status_code == 403


# ---------------------------------------------- B. cross-tenant isolation


@pytest.mark.asyncio
async def test_b_cross_tenant_get_put_cancel_returns_404(
    app_client, db_session, test_env
):
    """Bookings in another tenant are invisible: GET/PUT/cancel all 404 (no
    'exists but not yours' leak → no enumeration)."""
    import uuid

    from app.models.booking import Booking
    from app.models.tenant import Tenant

    model = await _seed_model(db_session, name="ISO-Model")
    other_tenant_id = f"tnt-iso-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="Iso Tenant"))
    await db_session.commit()
    other_device = await _seed_device(
        db_session, tenant_id=other_tenant_id, model_id=model.id, serial="ISO-DEV"
    )
    start, end = _window(0, 1)
    # Seed a booking directly in the OTHER tenant.
    other_booking = Booking(
        tenant_id=other_tenant_id,
        device_id=other_device.id,
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    db_session.add(other_booking)
    await db_session.commit()

    # The owner (test_env.tenant_id) cannot see / touch other_tenant's booking.
    resp = await app_client.get(
        f"/api/v1/bookings/{other_booking.id}", headers=AUTH
    )
    assert resp.status_code == 404
    new_start, new_end = _window(72, 1)
    resp = await app_client.put(
        f"/api/v1/bookings/{other_booking.id}",
        json={
            "scheduled_start_at": _iso(new_start),
            "scheduled_end_at": _iso(new_end),
        },
        headers=AUTH,
    )
    assert resp.status_code == 404
    resp = await app_client.post(
        f"/api/v1/bookings/{other_booking.id}/cancel", headers=AUTH
    )
    assert resp.status_code == 404
    # List scoped to caller's tenant → empty.
    resp = await app_client.get("/api/v1/bookings/", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []


# ------------------------------- C. time-slot overlap (D4 / D1: 400 not 409)


@pytest.mark.asyncio
async def test_c1_overlap_same_device_same_window_400(app_client, db_session, test_env):
    """Same device, overlapping window → 400 (BizError, NOT 409 — D1)."""
    model = await _seed_model(db_session, name="C1-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="C1-DEV"
    )
    s1, e1 = _window(0, 2)  # 10:00–12:00
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s1),
            "scheduled_end_at": _iso(e1),
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    # Overlapping: 11:00–13:00 (intersects 11:00–12:00).
    s2, e2 = _window(1, 2)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s2),
            "scheduled_end_at": _iso(e2),
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_c2_back_to_back_no_conflict_201(app_client, db_session, test_env):
    """Back-to-back: one ends 11:00, next starts 11:00 → 201 (left-closed /
    right-open means the boundary touches but does not overlap)."""
    model = await _seed_model(db_session, name="C2-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="C2-DEV"
    )
    s1, e1 = _window(0, 1)  # 10:00–11:00
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s1),
            "scheduled_end_at": _iso(e1),
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    # Starts exactly when the first ends: 11:00–12:00.
    s2, e2 = _window(1, 1)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s2),
            "scheduled_end_at": _iso(e2),
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_c3_cancelled_slot_reusable_201(app_client, db_session, test_env):
    """A cancelled booking has released its slot: the same window can be
    booked again (active-states-only overlap filter)."""
    model = await _seed_model(db_session, name="C3-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="C3-DEV"
    )
    s, e = _window(0, 1)
    first = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert first.status_code == 201
    # Cancel it → slot released.
    cancel = await app_client.post(
        f"/api/v1/bookings/{first.json()['id']}/cancel", headers=AUTH
    )
    assert cancel.status_code == 204
    # Same window now bookable again.
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_c4_reschedule_excludes_self_200(app_client, db_session, test_env):
    """PUT moves the window — the overlap check must exclude the booking
    being moved, otherwise it would always conflict with its own old slot."""
    model = await _seed_model(db_session, name="C4-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="C4-DEV"
    )
    s, e = _window(0, 2)  # 10:00–12:00
    create = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    bid = create.json()["id"]
    # Reschedule within an overlapping window (11:00–13:00 overlaps old
    # 10:00–12:00). exclude_id=self → must succeed.
    ns, ne = _window(1, 2)
    resp = await app_client.put(
        f"/api/v1/bookings/{bid}",
        json={
            "scheduled_start_at": _iso(ns),
            "scheduled_end_at": _iso(ne),
        },
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text


# ----------------------------------- D. status-guard (schema front guard)


@pytest.mark.asyncio
async def test_d1_post_status_ignored_still_pending(app_client, db_session, test_env):
    """POST with status=done in the body → created, status is still pending
    (the create schema doesn't carry status; Pydantic drops the unknown key)."""
    model = await _seed_model(db_session, name="D1-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="D1-DEV"
    )
    s, e = _window(0, 1)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
            "status": "done",  # must be ignored
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_d2_put_status_ignored(app_client, db_session, test_env):
    """PUT with status in the body → ignored, status unchanged (only /cancel
    can move status)."""
    model = await _seed_model(db_session, name="D2-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="D2-DEV"
    )
    s, e = _window(0, 1)
    create = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    bid = create.json()["id"]
    resp = await app_client.put(
        f"/api/v1/bookings/{bid}",
        json={"status": "done", "notes": "试图改状态"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"  # unchanged
    assert body["notes"] == "试图改状态"  # notes DID apply


@pytest.mark.asyncio
async def test_d3_post_lifecycle_fields_ignored(app_client, db_session, test_env):
    """POST with started_at / feedback → ignored (those are owned by
    device-poweron's /start / /end; never settable on create)."""
    model = await _seed_model(db_session, name="D3-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="D3-DEV"
    )
    s, e = _window(0, 1)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
            "started_at": _iso(s),
            "feedback": {"score": 5},
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["started_at"] is None
    assert body["feedback"] is None


# --------------------- E. status transitions (pending↔cancelled)


@pytest.mark.asyncio
async def test_e1_pending_cancel_204(app_client, db_session, test_env):
    """pending → cancel → 204, GET shows cancelled."""
    model = await _seed_model(db_session, name="E1-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="E1-DEV"
    )
    s, e = _window(0, 1)
    create = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    bid = create.json()["id"]
    resp = await app_client.post(f"/api/v1/bookings/{bid}/cancel", headers=AUTH)
    assert resp.status_code == 204
    get = await app_client.get(f"/api/v1/bookings/{bid}", headers=AUTH)
    assert get.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_e2_cancelled_put_reschedule_400(app_client, db_session, test_env):
    """cancelled is terminal: PUT reschedule → 400 (D10 — can't revive a
    cancelled booking by moving its window)."""
    model = await _seed_model(db_session, name="E2-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="E2-DEV"
    )
    s, e = _window(0, 1)
    create = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    bid = create.json()["id"]
    await app_client.post(f"/api/v1/bookings/{bid}/cancel", headers=AUTH)
    ns, ne = _window(96, 1)
    resp = await app_client.put(
        f"/api/v1/bookings/{bid}",
        json={
            "scheduled_start_at": _iso(ns),
            "scheduled_end_at": _iso(ne),
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_e3_cancel_idempotent_204(app_client, db_session, test_env):
    """Re-cancelling an already-cancelled booking → 204 (idempotent no-op,
    no DB write). Mirrors DELETE-idempotency (device unbind convention)."""
    model = await _seed_model(db_session, name="E3-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="E3-DEV"
    )
    s, e = _window(0, 1)
    create = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    bid = create.json()["id"]
    first = await app_client.post(f"/api/v1/bookings/{bid}/cancel", headers=AUTH)
    assert first.status_code == 204
    second = await app_client.post(f"/api/v1/bookings/{bid}/cancel", headers=AUTH)
    assert second.status_code == 204
    get = await app_client.get(f"/api/v1/bookings/{bid}", headers=AUTH)
    assert get.json()["status"] == "cancelled"


# ----------------------------------------- F. permission matrix + unauth


@pytest.mark.asyncio
async def test_f_member_read_only_end_to_end(member_client, db_session, test_env):
    """member has bookings:read only — create/update/cancel → 403."""
    model = await _seed_model(db_session, name="F-Member-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="F-MEM-DEV"
    )
    s, e = _window(0, 1)
    # Seed a booking via db_session (owner path) so member has something to read.
    from app.models.booking import Booking

    booking = Booking(
        tenant_id=test_env.tenant_id,
        device_id=device.id,
        scheduled_start_at=s,
        scheduled_end_at=e,
    )
    db_session.add(booking)
    await db_session.commit()

    # member can read the list + one.
    resp = await member_client.get("/api/v1/bookings/", headers=AUTH)
    assert resp.status_code == 200
    assert any(b["id"] == booking.id for b in resp.json())
    resp = await member_client.get(f"/api/v1/bookings/{booking.id}", headers=AUTH)
    assert resp.status_code == 200
    # member cannot create.
    resp = await member_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 403
    # member cannot update.
    resp = await member_client.put(
        f"/api/v1/bookings/{booking.id}",
        json={"notes": "x"},
        headers=AUTH,
    )
    assert resp.status_code == 403
    # member cannot cancel.
    resp = await member_client.post(
        f"/api/v1/bookings/{booking.id}/cancel", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_f_hq_staff_writes_are_403(hq_staff_client, db_session, test_env):
    """hq_staff is the HQ read-only viewer — writes (create/update/cancel) all
    403. The hq_staff fixture binds the user to the ``member`` tenant role (no
    bookings:create/update/delete in casbin), and ``permission_service.check``
    only short-circuits hq_staff for ``act == "read"`` — writes fall through to
    casbin and are denied. Acceptance F lists hq_staff write → 403 explicitly.

    NOTE: slice 01 keeps reads behind a router-level ``require_permission(
    "bookings", "read")``; the member role grants bookings:read so hq_staff
    (bound to member) CAN read here. Slice 03 moves the read guard into the
    endpoint body so the HQ panorama branch serves hq_staff without a tenant
    role — that refactor is where the hq_staff read test belongs."""
    model = await _seed_model(db_session, name="F-HQ-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="F-HQ-DEV"
    )
    s, e = _window(0, 1)
    # hq_staff cannot create.
    resp = await hq_staff_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 403
    # Seed a booking via db_session so we have an id to update/cancel.
    from app.models.booking import Booking

    booking = Booking(
        tenant_id=test_env.tenant_id,
        device_id=device.id,
        scheduled_start_at=s,
        scheduled_end_at=e,
    )
    db_session.add(booking)
    await db_session.commit()
    # hq_staff cannot update.
    ns, ne = _window(120, 1)
    resp = await hq_staff_client.put(
        f"/api/v1/bookings/{booking.id}",
        json={"scheduled_start_at": _iso(ns), "scheduled_end_at": _iso(ne)},
        headers=AUTH,
    )
    assert resp.status_code == 403
    # hq_staff cannot cancel.
    resp = await hq_staff_client.post(
        f"/api/v1/bookings/{booking.id}/cancel", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_f_unauthenticated_401(test_env):
    """No Authorization header → 401 (get_current_user raises 401)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/bookings/")
        assert resp.status_code == 401


# ----------------------------------------- G. walk-in (customer_id None)


@pytest.mark.asyncio
async def test_g_walk_in_customer_none_201(app_client, db_session, test_env):
    """Walk-in booking (customer_id omitted / null) → created 201; GET shows
    customer_id null. The customer guard is skipped when customer_id is None
    (D3)."""
    model = await _seed_model(db_session, name="G-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="G-DEV"
    )
    s, e = _window(0, 1)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
            # customer_id intentionally absent → walk-in.
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    bid = resp.json()["id"]
    assert resp.json()["customer_id"] is None
    get = await app_client.get(f"/api/v1/bookings/{bid}", headers=AUTH)
    assert get.json()["customer_id"] is None


@pytest.mark.asyncio
async def test_g_customer_not_in_tenant_400(app_client, db_session, test_env):
    """customer_id that has no live profile in this tenant → 400 (nonexistent
    + cross-tenant both collapse to the same BizError — no enumeration)."""
    import uuid

    from app.models.customer import Customer
    from app.models.tenant import Tenant

    model = await _seed_model(db_session, name="G2-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="G2-DEV"
    )
    # A customer whose only profile is in a DIFFERENT tenant.
    other_tenant_id = f"tnt-g2-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="G2 Other Tenant"))
    await db_session.commit()
    customer = Customer(name="外店客户", identity_key=f"phone-{uuid.uuid4().hex}")
    db_session.add(customer)
    await db_session.commit()
    from app.models.customer import CustomerProfile

    db_session.add(
        CustomerProfile(
            customer_id=customer.id, tenant_id=other_tenant_id, status="active"
        )
    )
    await db_session.commit()

    s, e = _window(0, 1)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "customer_id": customer.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


# ----------------------------------------- H. device SET NULL (FK dead-bolt)


@pytest.mark.asyncio
async def test_h_soft_deleted_device_booking_still_gets(
    app_client, db_session, test_env
):
    """A booking whose device is soft-deleted AFTER the booking was created
    still reads back fine (device_id FK is SET NULL — the booking row survives;
    the device_id column keeps its value but the device relation is gone).
    Mirrors the devices.customer_id convention."""
    from datetime import UTC, datetime

    from app.models.device import Device

    model = await _seed_model(db_session, name="H-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="H-DEV"
    )
    s, e = _window(0, 1)
    create = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    bid = create.json()["id"]
    # Soft-delete the device after the booking exists.
    row = await db_session.get(Device, device.id)
    assert row is not None
    row.is_deleted = True
    row.deleted_at = datetime.now(UTC)
    await db_session.commit()

    resp = await app_client.get(f"/api/v1/bookings/{bid}", headers=AUTH)
    assert resp.status_code == 200
    # device_id is preserved (SET NULL is the FK ondelete behaviour for a
    # HARD delete; under the current soft-delete path the column value stays).
    assert resp.json()["device_id"] == device.id


@pytest.mark.asyncio
async def test_h_create_with_device_not_in_tenant_400(
    app_client, db_session, test_env
):
    """device_id that is not a live device in this tenant → 400 (nonexistent +
    cross-tenant + soft-deleted all collapse to one BizError — no enumeration)."""
    import uuid

    from app.models.tenant import Tenant

    model = await _seed_model(db_session, name="H2-Model")
    other_tenant_id = f"tnt-h2-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="H2 Other Tenant"))
    await db_session.commit()
    other_device = await _seed_device(
        db_session, tenant_id=other_tenant_id, model_id=model.id, serial="H2-OTHER"
    )
    s, e = _window(0, 1)
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": other_device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_h_customer_set_null_fk_declared():
    """Acceptance H also covers the customer side of the SET NULL dead-bolt:
    when a Customer is hard-deleted, the booking row must survive with
    ``customer_id`` cleared (FK ``ondelete=SET NULL``), NOT be cascaded.

    The runtime SET NULL behaviour is enforced by Postgres at FK-check time
    (SQLite via aiosqlite does not enable FK enforcement by default, so the
    column-clear cannot be exercised in the in-memory test DB). What we CAN
    assert here is that the ORM model declares the constraint correctly —
    that declaration is what the migration emits and what Postgres enforces.
    This keeps the test honest about the SQLite limitation while still
    guarding the H-chapter contract (booking survives a customer hard-delete).
    """
    from app.models.booking import Booking

    fk = list(Booking.__table__.c.customer_id.foreign_keys)[0]
    assert fk.column.table.name == "customers"
    # ondelete must be SET NULL — a RESTRICT/CASCADE here would take the booking
    # down with a hard-deleted customer, violating the H contract.
    assert fk.ondelete == "SET NULL"


# ----------------------------------------- validation edge: inverted window


@pytest.mark.asyncio
async def test_create_inverted_window_400(app_client, db_session, test_env):
    """scheduled_end <= scheduled_start → 400 (BizError, enforced in the
    service — see BookingCreate docstring for why it's not a schema
    ``model_validator``)."""
    model = await _seed_model(db_session, name="Inv-Model")
    device = await _seed_device(
        db_session, tenant_id=test_env.tenant_id, model_id=model.id, serial="INV-DEV"
    )
    s, e = _window(1, -1)  # end before start
    resp = await app_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


# ----------------------------------------- K. backfill (slice 02)
#
# K chapter verifies ``backfill_bookings_perms_for_existing_tenants``: the
# function that brings pre-existing tenants (created before slice 02 shipped)
# up to the bookings permission set. Each test stands alone (no client fixture
# — these are pure DB + permission_service assertions) so they don't interact
# with the shared owner/seeded-casbin state in the A-H chapters.
#
# The test_env's seeded enforcer already carries bookings:* policies for
# test_env.tenant_id (simulating a backfilled tenant — see conftest). For K we
# create a FRESH tenant with zero bookings grants and run the backfill against it.


async def _seed_backfill_target_tenant(db_session, test_env=None):
    """K1: build a tenant that pre-dates device-booking slice 02.

    The tenant has the three system roles (owner/admin/member) and a couple of
    unrelated permission grants (customers:read, devices:read) to prove the K6
    contract — backfill must NOT touch other perms. Critically, it has ZERO
    bookings-related rows (no Permission rows, no RolePermission grants, no
    casbin policies) when this helper returns.

    The non-bookings grants are mirrored in BOTH the DB (SCD2 grants) AND
    casbin (so ``permission_service.check`` returns True before backfill —
    without the casbin policy the DB grant is invisible to enforcement).
    Mirroring is the same two-step write path the production
    ``seed_tenant_defaults`` uses.
    """
    import uuid

    from app.models.rbac import Permission, Role, RolePermission
    from app.models.tenant import Tenant

    tenant_id = f"tnt-k-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=tenant_id, name="K Backfill Target"))

    # Three system roles.
    role_ids: dict[str, str] = {}
    for code in ("owner", "admin", "member"):
        rid = uuid.uuid4().hex
        db_session.add(
            Role(
                id=rid,
                tenant_id=tenant_id,
                name=code.capitalize(),
                code=code,
                is_system=True,
                data_scope="tenant",
            )
        )
        role_ids[code] = rid

    # Seed an unrelated permission (customers:read) on all three roles +
    # a second unrelated perm (devices:read) to prove backfill doesn't touch
    # existing grants (K6). Mirrored in casbin below so ``check`` returns True.
    perm_id = uuid.uuid4().hex
    db_session.add(
        Permission(
            id=perm_id,
            tenant_id=tenant_id,
            name="客户-查看",
            code="customers:read",
            type="api",
            is_system=True,
        )
    )
    dev_perm_id = uuid.uuid4().hex
    db_session.add(
        Permission(
            id=dev_perm_id,
            tenant_id=tenant_id,
            name="设备-查看",
            code="devices:read",
            type="api",
            is_system=True,
        )
    )
    from datetime import UTC, datetime

    for code in ("owner", "admin", "member"):
        db_session.add(
            RolePermission(
                role_id=role_ids[code],
                permission_id=perm_id,
                tenant_id=tenant_id,
                valid_from=datetime.now(UTC),
                valid_to=None,
            )
        )
    # devices:read only on owner (just to exercise the K6 untouched contract;
    # the specific role distribution doesn't matter for the assertions below).
    db_session.add(
        RolePermission(
            role_id=role_ids["owner"],
            permission_id=dev_perm_id,
            tenant_id=tenant_id,
            valid_from=datetime.now(UTC),
            valid_to=None,
        )
    )
    await db_session.commit()

    # Casbin mirror — the SCD2 grants above are the source of truth but casbin
    # is what ``check`` actually reads. Add the same (role, obj, act) pairs so
    # the pre-backfill assertions pass (K6 is "other perms work before AND
    # after").
    if test_env is not None:
        for role in ("owner", "admin", "member"):
            test_env.enforcer.add_policy(role, tenant_id, "customers", "read")
        test_env.enforcer.add_policy("owner", tenant_id, "devices", "read")

    return tenant_id, role_ids


@pytest.mark.asyncio
async def test_k_backfill_grants_bookings_perms_correctly(db_session, test_env):
    """K2 + K3 + K4: backfill grants owner the full bookings set, member only
    read; both pick up menu:bookings. Verified through the production code path
    (permission_service.check) so a casbin-sync regression surfaces."""
    from unittest.mock import patch

    from app.core import casbin_enforcer as casbin_mod
    from app.services.permission_service import (
        backfill_bookings_perms_for_existing_tenants,
        permission_service,
    )

    tenant_id, _ = await _seed_backfill_target_tenant(db_session, test_env)
    # The enforcer patch mirrors what app_client sets up: without it, the
    # production ``get_enforcer`` would route casbin calls to the unrelated
    # global SQLite DB (MissingGreenlet). Patch for the whole test.
    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        # K2: run the backfill. ``db`` must be the same session the assertions
        # use so the writes are visible (test fixture shares one connection).
        stats = await backfill_bookings_perms_for_existing_tenants(db_session)

        # The backfill should have added: owner gets 4 api + 1 menu = 5; admin
        # 3 + 1 = 4; member 1 + 1 = 2. The seeded customers:read (3) and
        # devices:read (1) are NOT counted (pre-existing → grant was a no-op).
        assert stats[tenant_id] == 5 + 4 + 2, stats

        # K3: owner gets all four bookings api perms + menu:bookings. The role
        # name itself is a casbin subject (see conftest _make_casbin), so we
        # check the role directly — no user binding needed.
        for act in ("create", "read", "update", "delete"):
            ok = await permission_service.check(
                "owner", tenant_id, "bookings", act
            )
            assert ok, f"owner should have bookings:{act} after backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", "bookings")
        assert ok, "owner should have menu:bookings after backfill"

        # K4: member gets bookings:read + menu:bookings only — NOT create.
        ok = await permission_service.check("member", tenant_id, "bookings", "read")
        assert ok, "member should have bookings:read after backfill"
        denied = await permission_service.check(
            "member", tenant_id, "bookings", "create"
        )
        assert not denied, "member must NOT get bookings:create (anti-overgrant)"


@pytest.mark.asyncio
async def test_k_backfill_idempotent(db_session, test_env):
    """K5: re-running backfill on an already-backfilled tenant is a no-op —
    same grants, no error, no duplicate rows."""
    from unittest.mock import patch

    from sqlalchemy import select

    from app.core import casbin_enforcer as casbin_mod
    from app.models.rbac import RolePermission
    from app.services.permission_service import (
        backfill_bookings_perms_for_existing_tenants,
    )

    tenant_id, _ = await _seed_backfill_target_tenant(db_session, test_env)

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        await backfill_bookings_perms_for_existing_tenants(db_session)
        # Snapshot the post-backfill grants so we can detect drift after the
        # second run (active = valid_to IS NULL).
        before_rows = (
            await db_session.execute(
                select(RolePermission).where(
                    RolePermission.tenant_id == tenant_id,
                    RolePermission.valid_to.is_(None),
                )
            )
        ).scalars().all()
        before_ids = {r.id for r in before_rows}

        # K5: run it again. Must not raise, must report zero new grants
        # (everything is already there), must not create duplicate grant rows.
        second = await backfill_bookings_perms_for_existing_tenants(db_session)
        assert second[tenant_id] == 0, "second run must add 0 grants"

        after_rows = (
            await db_session.execute(
                select(RolePermission).where(
                    RolePermission.tenant_id == tenant_id,
                    RolePermission.valid_to.is_(None),
                )
            )
        ).scalars().all()
        after_ids = {r.id for r in after_rows}
        assert before_ids == after_ids, "no new grant rows should appear"


@pytest.mark.asyncio
async def test_k_backfill_preserves_other_perms(db_session, test_env):
    """K6: backfill touches ONLY bookings/menu:bookings. The pre-existing
    customers:read and devices:read grants survive unchanged — both before/after
    the backfill."""
    from unittest.mock import patch

    from app.core import casbin_enforcer as casbin_mod
    from app.services.permission_service import (
        backfill_bookings_perms_for_existing_tenants,
        permission_service,
    )

    tenant_id, _ = await _seed_backfill_target_tenant(db_session, test_env)

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        # Pre-backfill: customers:read works for owner/admin/member; devices:read
        # works for owner. (No bookings perms yet.)
        for role in ("owner", "admin", "member"):
            ok = await permission_service.check(
                role, tenant_id, "customers", "read"
            )
            assert ok, f"{role} had customers:read before backfill"
        ok = await permission_service.check("owner", tenant_id, "devices", "read")
        assert ok, "owner had devices:read before backfill"

        await backfill_bookings_perms_for_existing_tenants(db_session)

        # Post-backfill: the original perms still work AND bookings perms work.
        for role in ("owner", "admin", "member"):
            ok = await permission_service.check(
                role, tenant_id, "customers", "read"
            )
            assert ok, f"{role} should still have customers:read after backfill"
        ok = await permission_service.check("owner", tenant_id, "devices", "read")
        assert ok, "owner should still have devices:read after backfill"
        # And a bookings perm does work (backfill actually did something).
        ok = await permission_service.check("owner", tenant_id, "bookings", "read")
        assert ok, "owner should have bookings:read after backfill"


# ============================================================================
# HQ panorama (slice 03) — super_admin / hq_staff cross-tenant read.
#
# These mirror the devices.py slice-03 HQ tests: cross-tenant viewers see
# ``BookingHqRead`` (with tenant_name / device_name / customer_name) across
# EVERY tenant, while writes stay 403 for hq_staff (read-only viewer).
#
# Each test uses ONE client fixture (see the file header note):
# super_admin tests use ``super_admin_client`` (seeds a 2nd tenant "Other
# Tenant" + cross-user + marks owner as super_admin), hq_staff tests use
# ``hq_staff_client`` (seeds a 2nd tenant + binds the user as member with
# platform_role=hq_staff). Mixing fixtures in one function would corrupt the
# shared owner user.
# ============================================================================


async def _seed_two_tenant_bookings(db_session, test_env):
    """Seed one booking in the caller's own tenant AND one in a 2nd tenant,
    each with its own device + customer, so cross-tenant HQ assertions have
    data in both stores. Returns the seeded rows.

    The 2nd tenant mirrors what ``super_admin_client`` / ``hq_staff_client``
    seed ("Other Tenant") but creates its own to stay self-contained (the
    fixtures' tenant is for the user-membership side; the bookings need a
    device + customer in that tenant too, which the fixtures don't provide).
    """
    import uuid

    from app.models.booking import Booking
    from app.models.tenant import Tenant

    model = await _seed_model(db_session, name="HQ-Model")

    # Own-tenant device + customer + booking.
    own_device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="HQ-OWN",
    )
    own_customer, _own_profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="HQ-本店客户"
    )
    own_start, own_end = _window(0, 1)
    own_booking = Booking(
        tenant_id=test_env.tenant_id,
        device_id=own_device.id,
        customer_id=own_customer.id,
        scheduled_start_at=own_start,
        scheduled_end_at=own_end,
        notes="本店预约",
    )
    db_session.add(own_booking)

    # 2nd tenant + its device + customer + booking.
    other_tenant_id = f"tnt-hq-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="HQ Other Tenant"))
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=model.id,
        serial="HQ-OTHER",
    )
    other_customer, _other_profile = await _seed_customer_with_profile(
        db_session, tenant_id=other_tenant_id, name="HQ-他店客户"
    )
    other_start, other_end = _window(24, 1)
    other_booking = Booking(
        tenant_id=other_tenant_id,
        device_id=other_device.id,
        customer_id=other_customer.id,
        scheduled_start_at=other_start,
        scheduled_end_at=other_end,
        notes="他店预约",
    )
    db_session.add(other_booking)
    await db_session.commit()
    return {
        "own_booking": own_booking,
        "own_device": own_device,
        "own_customer": own_customer,
        "other_booking": other_booking,
        "other_device": other_device,
        "other_customer": other_customer,
        "other_tenant_id": other_tenant_id,
        "model": model,
    }


@pytest.mark.asyncio
async def test_hq1_super_admin_list_returns_panorama(
    super_admin_client, db_session, test_env
):
    """HQ-1: super_admin ``GET /bookings/`` returns ``BookingHqRead`` across
    every tenant — panorama fields tenant_name / device_name / customer_name
    populated, and bookings from tenants other than the caller's own are
    visible (the core cross-tenant read guarantee)."""
    seeded = await _seed_two_tenant_bookings(db_session, test_env)
    resp = await super_admin_client.get("/api/v1/bookings/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    items = {b["id"]: b for b in resp.json()}
    # Both tenants' bookings visible.
    assert seeded["own_booking"].id in items
    assert seeded["other_booking"].id in items

    own_row = items[seeded["own_booking"].id]
    assert own_row["tenant_name"] == "Test Tenant"
    # device_name sourced from serial_number (devices have no name column).
    assert own_row["device_name"] == "HQ-OWN"
    assert own_row["customer_name"] == "HQ-本店客户"

    other_row = items[seeded["other_booking"].id]
    assert other_row["tenant_name"] == "HQ Other Tenant"
    assert other_row["device_name"] == "HQ-OTHER"
    assert other_row["customer_name"] == "HQ-他店客户"


@pytest.mark.asyncio
async def test_hq2_super_admin_get_one_cross_tenant_returns_panorama(
    super_admin_client, db_session, test_env
):
    """HQ-2: super_admin ``GET /bookings/{id}`` on ANOTHER tenant's booking
    returns 200 + ``BookingHqRead`` (the HQ viewer reads any tenant's booking;
    no 404 for a foreign id — unlike the tenant-role path)."""
    seeded = await _seed_two_tenant_bookings(db_session, test_env)
    resp = await super_admin_client.get(
        f"/api/v1/bookings/{seeded['other_booking'].id}", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == seeded["other_booking"].id
    assert body["tenant_name"] == "HQ Other Tenant"
    assert body["device_name"] == "HQ-OTHER"
    assert body["customer_name"] == "HQ-他店客户"


@pytest.mark.asyncio
async def test_hq2b_super_admin_get_nonexistent_returns_404(
    super_admin_client, db_session, test_env
):
    """HQ-2b: HQ ``GET /{id}`` on a nonexistent id → 404 (the panorama path
    turns a missing row into NotFoundError, same surface as within-store)."""
    resp = await super_admin_client.get(
        "/api/v1/bookings/nonexistent-id-xxx", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_hq3_hq_staff_list_returns_panorama(
    hq_staff_client, db_session, test_env
):
    """HQ-3: hq_staff sees the same panorama as super_admin on reads — the
    bypass is ``permission_service.check``'s ``hq_staff`` + ``read``
    short-circuit. This is the core regression guard: before slice 03, the
    router-level ``require_permission("bookings","read")`` 403'd hq_staff."""
    seeded = await _seed_two_tenant_bookings(db_session, test_env)
    resp = await hq_staff_client.get("/api/v1/bookings/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    items = {b["id"]: b for b in resp.json()}
    assert seeded["own_booking"].id in items
    assert seeded["other_booking"].id in items
    own_row = items[seeded["own_booking"].id]
    assert own_row["tenant_name"] == "Test Tenant"
    assert own_row["device_name"] == "HQ-OWN"
    assert own_row["customer_name"] == "HQ-本店客户"


@pytest.mark.asyncio
async def test_hq4_hq_staff_writes_are_403(hq_staff_client, db_session, test_env):
    """HQ-4: hq_staff is read-only — create / update / cancel all 403.

    The hq_staff fixture binds the user to the ``member`` tenant role (no
    bookings:create/update/delete in casbin), and ``permission_service.check``
    only short-circuits hq_staff for ``act == "read"`` — writes fall through
    to casbin and are denied. The HQ viewer can SEE everything but touch
    nothing (WIP=1 boundary)."""
    model = await _seed_model(db_session, name="HQ-Write-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="HQ-WRITE",
    )
    s, e = _window(0, 1)
    # create → 403 (router-level require_permission("bookings","create"))
    resp = await hq_staff_client.post(
        "/api/v1/bookings/",
        json={
            "device_id": device.id,
            "scheduled_start_at": _iso(s),
            "scheduled_end_at": _iso(e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 403

    # Seed a booking directly (hq_staff can't create one) to exercise update/cancel.
    from app.models.booking import Booking

    booking = Booking(
        tenant_id=test_env.tenant_id,
        device_id=device.id,
        scheduled_start_at=s,
        scheduled_end_at=e,
    )
    db_session.add(booking)
    await db_session.commit()

    new_s, new_e = _window(48, 1)
    resp = await hq_staff_client.put(
        f"/api/v1/bookings/{booking.id}",
        json={
            "scheduled_start_at": _iso(new_s),
            "scheduled_end_at": _iso(new_e),
        },
        headers=AUTH,
    )
    assert resp.status_code == 403
    resp = await hq_staff_client.post(
        f"/api/v1/bookings/{booking.id}/cancel", headers=AUTH
    )
    assert resp.status_code == 403


# ============================================================================
# Schedule grid (slice 03) — GET /devices/{device_id}/schedule
#
# Day-grouped booking aggregation: ``{ "2030-01-01": [booking, ...], ... }``.
# Only days with ≥1 booking appear. Cross-tenant device → 404 (enumeration
# defence, same as GET /devices/{id}).
# ============================================================================


@pytest.mark.asyncio
async def test_sch1_two_bookings_same_day_aggregated(
    app_client, db_session, test_env
):
    """SCH-1: two bookings on the same device + same day → one date key with
    both bookings (len==2), ordered by scheduled_start_at asc."""
    from app.models.booking import Booking

    model = await _seed_model(db_session, name="SCH1-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="SCH1-DEV",
    )
    # Two bookings on the same day (_BASE day): 10:00–11:00 and 14:00–15:00.
    s1, e1 = _window(0, 1)
    s2, e2 = _window(4, 1)
    for s, e in ((s1, e1), (s2, e2)):
        db_session.add(
            Booking(
                tenant_id=test_env.tenant_id,
                device_id=device.id,
                scheduled_start_at=s,
                scheduled_end_at=e,
            )
        )
    await db_session.commit()

    # Window must cover _BASE (2030-01-01). Use an explicit wide range so the
    # test is independent of "today".
    range_start = _iso_q(_BASE - timedelta(days=1))
    range_end = _iso_q(_BASE + timedelta(days=2))
    resp = await app_client.get(
        f"/api/v1/devices/{device.id}/schedule?start={range_start}&end={range_end}",
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    grid = resp.json()
    # One day key, two bookings under it.
    assert len(grid) == 1, f"expected one day key, got {list(grid.keys())}"
    day_key = next(iter(grid.keys()))
    assert day_key == _BASE.date().isoformat()
    assert len(grid[day_key]) == 2
    # Ordered by scheduled_start_at asc.
    starts = [b["scheduled_start_at"] for b in grid[day_key]]
    assert starts == sorted(starts)


@pytest.mark.asyncio
async def test_sch2_empty_days_omitted(app_client, db_session, test_env):
    """SCH-2: days with no booking do NOT appear as keys (omitted, not
    keyed to []). Two bookings on different days → two keys, nothing in
    between."""
    from app.models.booking import Booking

    model = await _seed_model(db_session, name="SCH2-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="SCH2-DEV",
    )
    # Day 0 (_BASE) and day 3 — days 1 and 2 are empty.
    s1, e1 = _window(0, 1)
    s2, e2 = _window(72, 1)  # 3 days later
    for s, e in ((s1, e1), (s2, e2)):
        db_session.add(
            Booking(
                tenant_id=test_env.tenant_id,
                device_id=device.id,
                scheduled_start_at=s,
                scheduled_end_at=e,
            )
        )
    await db_session.commit()

    range_start = _iso_q(_BASE - timedelta(days=1))
    range_end = _iso_q(_BASE + timedelta(days=5))
    resp = await app_client.get(
        f"/api/v1/devices/{device.id}/schedule?start={range_start}&end={range_end}",
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    grid = resp.json()
    assert set(grid.keys()) == {
        _BASE.date().isoformat(),
        (_BASE + timedelta(days=3)).date().isoformat(),
    }
    # Each day has exactly one booking.
    assert all(len(v) == 1 for v in grid.values())


@pytest.mark.asyncio
async def test_sch3_cross_tenant_device_returns_404(
    app_client, db_session, test_env
):
    """SCH-3: a device belonging to ANOTHER tenant → 404 (read-side
    enumeration defence). The owner (test_env.tenant_id) must not learn
    whether a foreign device id exists. Mirrors GET /devices/{id}."""
    import uuid

    from app.models.tenant import Tenant

    model = await _seed_model(db_session, name="SCH3-Model")
    other_tenant_id = f"tnt-sch-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="SCH Other Tenant"))
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=model.id,
        serial="SCH3-OTHER",
    )
    await db_session.commit()

    range_start = _iso_q(_BASE - timedelta(days=1))
    range_end = _iso_q(_BASE + timedelta(days=2))
    resp = await app_client.get(
        f"/api/v1/devices/{other_device.id}/schedule?start={range_start}&end={range_end}",
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sch4_nonexistent_device_returns_404(app_client, db_session, test_env):
    """SCH-4: a totally nonexistent device id → 404 (same surface as
    cross-tenant; no distinction between "missing" and "foreign")."""
    range_start = _iso_q(_BASE - timedelta(days=1))
    range_end = _iso_q(_BASE + timedelta(days=2))
    resp = await app_client.get(
        "/api/v1/devices/nonexistent-device-id/schedule"
        f"?start={range_start}&end={range_end}",
        headers=AUTH,
    )
    assert resp.status_code == 404


# ============================================================================
# M. customer own endpoint (slice 04) — GET /me/bookings.
#
# A customer principal (a token whose claims carry ``customer_id``) sees ONLY
# the bookings whose ``customer_id`` equals its own. Store-staff accounts (no
# ``customer_id`` claim) get 403 — this is a customer-only surface. The backend
# injects the id from the resolved principal and NEVER trusts a client-supplied
# ``customer_id`` query param (M4 anti-override check).
#
# The ``customer_client`` fixture (conftest) mints a token with a ``customer_id``
# claim; ``BookingService.list_my_bookings`` reads it off ``current_user`` and
# filters via ``BookingRepository.list_for_customer``.
# ============================================================================


async def _seed_my_bookings_fixture(db_session, test_env):
    """Seed the data the M-chapter tests share: one device/model, two customers
    (``own`` + ``other``), and bookings bound to each. Returns the seeded rows.

    ``own_customer`` gets 2 bookings; ``other_customer`` gets 1. A walk-in
    booking (customer_id None) is also seeded for M3. Each test picks the
    ``customer_id`` to impersonate and re-reads the list itself (keeps tests
    independent of seed ordering drift)."""
    model = await _seed_model(db_session, name="MY-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="MY-DEV",
    )
    own_customer, _own_profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="我的客户"
    )
    other_customer, _other_profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="他人客户"
    )

    from app.models.booking import Booking

    bookings = []
    # Two bookings for own_customer (distinct windows, no overlap).
    for i, offset in enumerate((0, 2)):
        s, e = _window(offset, 1)
        b = Booking(
            tenant_id=test_env.tenant_id,
            device_id=device.id,
            customer_id=own_customer.id,
            scheduled_start_at=s,
            scheduled_end_at=e,
            notes=f"我的预约{i}",
        )
        db_session.add(b)
        bookings.append(b)
    # One booking for other_customer.
    s_o, e_o = _window(4, 1)
    other_b = Booking(
        tenant_id=test_env.tenant_id,
        device_id=device.id,
        customer_id=other_customer.id,
        scheduled_start_at=s_o,
        scheduled_end_at=e_o,
        notes="他人预约",
    )
    db_session.add(other_b)
    # One walk-in booking (customer_id None) — M3 asserts it never appears.
    s_w, e_w = _window(6, 1)
    walkin_b = Booking(
        tenant_id=test_env.tenant_id,
        device_id=device.id,
        customer_id=None,
        scheduled_start_at=s_w,
        scheduled_end_at=e_w,
        notes="散客 walk-in",
    )
    db_session.add(walkin_b)
    await db_session.commit()
    return {
        "model": model,
        "device": device,
        "own_customer": own_customer,
        "other_customer": other_customer,
        "own_booking_ids": [b.id for b in bookings],
        "other_booking_id": other_b.id,
        "walkin_booking_id": walkin_b.id,
    }


@pytest.mark.asyncio
async def test_m1_customer_sees_only_own_bookings(
    customer_client_factory, db_session, test_env
):
    """M1: a customer principal sees only the bookings whose ``customer_id``
    matches its own. Seeds 2 own + 1 other + 1 walk-in, impersonates the own
    customer, asserts exactly the 2 own bookings come back (no other-customer,
    no walk-in)."""
    seeded = await _seed_my_bookings_fixture(db_session, test_env)
    own_id = seeded["own_customer"].id
    client = await customer_client_factory(customer_id=own_id)

    resp = await client.get("/api/v1/me/bookings", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned_ids = {b["id"] for b in body}
    assert returned_ids == set(seeded["own_booking_ids"]), (
        f"expected only own bookings {seeded['own_booking_ids']}, got {returned_ids}"
    )
    # Defence-in-depth: the other customer's + walk-in bookings must NOT leak.
    assert seeded["other_booking_id"] not in returned_ids
    assert seeded["walkin_booking_id"] not in returned_ids
    # Shape: BookingRead (no HQ panorama fields tenant_name/device_name).
    assert "tenant_name" not in body[0]
    assert "device_name" not in body[0]


@pytest.mark.asyncio
async def test_m2_store_staff_without_customer_id_gets_403(
    app_client, db_session, test_env
):
    """M2: a store-staff account (a normal tenant principal with NO
    ``customer_id`` claim) calling GET /me/bookings → 403. This endpoint is a
    customer-only surface; staff use GET /bookings/ instead. ``app_client``
    impersonates the tenant owner — no customer_id claim — so it must be
    rejected. (No seed data needed: the identity check fires before any read.)"""
    resp = await app_client.get("/api/v1/me/bookings", headers=AUTH)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_m3_walkin_booking_absent_from_customer_view(
    customer_client_factory, db_session, test_env
):
    """M3: a walk-in booking (customer_id NULL) must NOT appear in ANY
    customer's /me/bookings — it has no customer binding, so no customer
    principal owns it. Impersonate the own customer; the walk-in booking seeded
    in the fixture must be absent from the returned set."""
    seeded = await _seed_my_bookings_fixture(db_session, test_env)
    own_id = seeded["own_customer"].id
    client = await customer_client_factory(customer_id=own_id)

    resp = await client.get("/api/v1/me/bookings", headers=AUTH)
    assert resp.status_code == 200, resp.text
    returned_ids = {b["id"] for b in resp.json()}
    assert seeded["walkin_booking_id"] not in returned_ids, (
        "walk-in booking must never surface under any customer's /me/bookings"
    )
    # And the OTHER customer impersonation also excludes the walk-in.
    other_client = await customer_client_factory(
        customer_id=seeded["other_customer"].id
    )
    resp2 = await other_client.get("/api/v1/me/bookings", headers=AUTH)
    assert resp2.status_code == 200, resp2.text
    assert seeded["walkin_booking_id"] not in {
        b["id"] for b in resp2.json()
    }


@pytest.mark.asyncio
async def test_m4_endpoint_ignores_supplied_customer_id_param(
    customer_client_factory, db_session, test_env
):
    """M4 (anti-override): the endpoint MUST NOT honour a client-supplied
    ``customer_id`` query param. Impersonate the own customer but request the
    OTHER customer's id in the query string — the response still contains only
    the own customer's bookings. This is the vertical-line defence in the
    plan risk table (customer own bypass → High)."""
    seeded = await _seed_my_bookings_fixture(db_session, test_env)
    own_id = seeded["own_customer"].id
    other_id = seeded["other_customer"].id
    client = await customer_client_factory(customer_id=own_id)

    # Try to impersonate the other customer via the query string.
    resp = await client.get(
        f"/api/v1/me/bookings?customer_id={other_id}", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    returned_ids = {b["id"] for b in resp.json()}
    # Own bookings only — the other customer's booking must NOT leak despite
    # the param naming it.
    assert returned_ids == set(seeded["own_booking_ids"])
    assert seeded["other_booking_id"] not in returned_ids


# ============================================================================
# N. MeResponse.customer_id exposure (slice 07).
#
# The SPA's /bookings three-way fork keys off ``me.customer_id``: a customer
# principal lands on the read-only "my bookings" view, while store staff (no
# customer binding) stay on the store CRUD view. That requires the
# ``GET /auth/me`` response to actually carry the token's ``customer_id`` —
# CurrentUser has had it since slice 04, but MeResponse (the API contract) did
# not expose it. Slice 07 surfaces it.
#
# Two cases: a customer-bound token sees its own customer_id in the response;
# a store-staff token sees null (no claim). ``app_client`` is a staff principal
# with no customer claim.
# ============================================================================


async def test_n1_me_response_exposes_customer_id_for_customer_principal(
    customer_client_factory,
):
    """N1: a customer-bound token's GET /auth/me returns its ``customer_id`` in
    the response body. The frontend reads this to route to MyBookingsView."""
    own_id = f"c-{uuid.uuid4().hex}"
    client = await customer_client_factory(customer_id=own_id)

    resp = await client.get("/api/v1/auth/me", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer_id"] == own_id


async def test_n2_me_response_customer_id_null_for_store_staff(app_client):
    """N2: a store-staff token (no customer claim) returns ``customer_id: null``
    so the frontend's hasCustomerIdentity(me) helper correctly falls through to
    the store CRUD view. ``app_client`` is the tenant owner — no customer_id."""
    resp = await app_client.get("/api/v1/auth/me", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer_id"] is None


# ============================================================================
# P. lifecycle action endpoints (device-poweron slice 01)
# ----------------------------------------------------------------------------
# POST /bookings/{id}/start | /end | /no-show drive the booking through its
# active lifecycle via the ``booking_state`` pure function (6 legal edges).
# This chapter pins the full contract: legal transitions + side effects,
# illegal transitions → 400, the start permission matrix (customer own /
# walk-in guard / store owner+admin / member / hq_staff), the end/no-show
# owner-only matrix (admin 403 — no bookings:delete), and cross-tenant → 404.
#
# Non-pending starting states (confirmed / in_service / done / no_show) are
# seeded by direct DB writes (Booking(..., status=...)) — device-booking
# never produces them via the API, but the 6-state CHECK allows them and the
# state machine must handle each. Mirrors the cross-tenant / special-state
# seeding pattern at L1228 / L1599.
# ============================================================================


async def _seed_lifecycle_fixture(db_session, test_env):
    """Seed the rows the P-chapter tests share: one device/model, one bound
    customer, one walk-in (customer_id None) — all bookings start ``pending``
    unless a test overrides ``status`` at seed time (the helper exposes a
    factory for that). Returns the seeded rows + a ``make_booking`` factory.

    Keeping one fixture for the whole chapter avoids re-seeding a device per
    test; each test mints its own booking(s) via ``make_booking`` so they
    don't interfere (distinct windows, no overlap)."""
    model = await _seed_model(db_session, name="PWR-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="PWR-DEV",
    )
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="开机测试客户"
    )

    from app.models.booking import Booking

    async def make_booking(
        *,
        status: str = "pending",
        customer_id: str | None = customer.id,
        offset_hours: float = 10,
    ) -> Booking:
        """Direct-DB insert of a booking in the caller's tenant. ``status``
        defaults to pending (the only state device-booking writes via API);
        tests wanting a non-pending starting state pass it explicitly — the
        6-state CHECK constraint allows it, and the state machine must handle
        each. ``customer_id=None`` produces a walk-in booking."""
        start, end = _window(offset_hours, 1)
        b = Booking(
            tenant_id=test_env.tenant_id,
            device_id=device.id,
            customer_id=customer_id,
            status=status,
            scheduled_start_at=start,
            scheduled_end_at=end,
        )
        db_session.add(b)
        await db_session.commit()
        await db_session.refresh(b)
        return b

    return {
        "model": model,
        "device": device,
        "customer": customer,
        "make_booking": make_booking,
    }


# ----------------------------------------------------- P-1: legal edges (6)


# Each legal edge: (starting status, action path, expected status, side-effect
# assertion key). Mirrors ``booking_state._TRANSITIONS``. Parametrized so all 6
# edges are covered; ``start`` / ``end`` return BookingRead (assert the
# timestamp landed), ``no_show`` returns 204 (no body).
@pytest.mark.parametrize(
    ("start_status", "action_path", "expected_status", "side_effect"),
    [
        ("pending", "start", "in_service", "started_at"),
        ("confirmed", "start", "in_service", "started_at"),
        ("in_service", "end", "done", "ended_at"),
        ("pending", "no-show", "no_show", None),
        ("confirmed", "no-show", "no_show", None),
        ("in_service", "no-show", "no_show", None),
    ],
    ids=[
        "pending__start",
        "confirmed__start",
        "in_service__end",
        "pending__no_show",
        "confirmed__no_show",
        "in_service__no_show",
    ],
)
@pytest.mark.asyncio
async def test_p1_legal_transition_writes_side_effect(
    app_client,
    db_session,
    test_env,
    start_status,
    action_path,
    expected_status,
    side_effect,
):
    """P-1: each of the 6 legal edges flips the booking to ``expected_status``
    and, for start/end, writes the corresponding timestamp column. Non-pending
    starting states are seeded by direct DB write (the API never produces them
    in device-booking, but the state machine must handle them)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status=start_status)

    if action_path == "end":
        resp = await app_client.post(
            f"/api/v1/bookings/{booking.id}/end",
            headers=AUTH,
            json={"feedback": {"rating": 5}},
        )
    else:
        resp = await app_client.post(
            f"/api/v1/bookings/{booking.id}/{action_path}", headers=AUTH
        )

    assert resp.status_code == 200 or resp.status_code == 204, resp.text
    if action_path == "no-show":
        assert resp.status_code == 204
    else:
        body = resp.json()
        assert body["status"] == expected_status
        if side_effect is not None:
            assert body[side_effect] is not None, (
                f"{side_effect} should be set after {action_path}"
            )


# ------------------------------------------------- P-2: illegal → 400


# Each illegal edge the plan calls out, plus the terminal-state invariant.
# (The exhaustive 12-pair coverage lives in test_booking_state.py; here we
# pin the API surface: 400 not 409, and the message is locale-correct.)
@pytest.mark.parametrize(
    ("start_status", "action_path"),
    [
        # Can't end what hasn't started.
        ("pending", "end"),
        # Can't restart an in-service booking.
        ("in_service", "start"),
        # Terminal states reject every action.
        ("done", "start"),
        ("done", "end"),
        ("done", "no-show"),
        ("cancelled", "start"),
        ("cancelled", "end"),
        ("cancelled", "no-show"),
        ("no_show", "start"),
        ("no_show", "end"),
        ("no_show", "no-show"),
    ],
    ids=lambda v: v.replace("_", "__") if isinstance(v, str) else v,
)
@pytest.mark.asyncio
async def test_p2_illegal_transition_returns_400(
    app_client, db_session, test_env, start_status, action_path
):
    """P-2: any illegal ``(state, action)`` → 400 (InvalidTransition subclasses
    BizError; the repo has no 409 concept — plan §0 D1). Covers terminal-state
    rejection + the "can't end pending" / "can't restart in_service" rules."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status=start_status)

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/{action_path}", headers=AUTH
    )
    assert resp.status_code == 400, (
        f"expected 400 for ({start_status}, {action_path}), "
        f"got {resp.status_code}: {resp.text}"
    )


# ------------------------------------------- P-3: start permission matrix


@pytest.mark.asyncio
async def test_p3_start_customer_own_booking_200(
    customer_client_factory, db_session, test_env
):
    """P-3a: a customer principal starting their own pending booking → 200.
    The customer path bypasses casbin (no tenant role needed) and keys off
    ``customer_id`` ownership instead."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()
    client = await customer_client_factory(customer_id=fixture["customer"].id)

    resp = await client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "in_service"
    assert resp.json()["started_at"] is not None


@pytest.mark.asyncio
async def test_p3_start_customer_other_booking_403(
    customer_client_factory, db_session, test_env
):
    """P-3b: a customer principal starting another customer's booking → 403
    (ownership check: booking.customer_id != principal customer_id)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()
    # A different customer principal — not the booking's owner.
    client = await customer_client_factory(
        customer_id=f"other-{uuid.uuid4().hex}"
    )

    resp = await client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p3_start_customer_walkin_booking_403(
    customer_client_factory, db_session, test_env
):
    """P-3c: a customer principal starting a walk-in booking (customer_id
    None) → 403 (walk-in guard fires before the ownership check; walk-in
    bookings are store-staff-only to start — anti-impersonation, plan §0 D5)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](customer_id=None)
    client = await customer_client_factory(customer_id=fixture["customer"].id)

    resp = await client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p3_start_owner_200(app_client, db_session, test_env):
    """P-3d: store owner starting any pending booking → 200 (has
    bookings:update). Owner is the ``app_client`` fixture."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_p3_start_admin_200(tenant_admin_client, db_session, test_env):
    """P-3e: store admin starting a pending booking → 200 (admin has
    bookings:update; only end/no-show are admin-forbidden, not start)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await tenant_admin_client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_p3_start_admin_walkin_200(
    tenant_admin_client, db_session, test_env
):
    """P-3f: store admin starting a walk-in booking → 200 (admin can start
    walk-ins; the walk-in restriction is customer-only, not store-only)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](customer_id=None)

    resp = await tenant_admin_client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_p3_start_member_403(member_client, db_session, test_env):
    """P-3g: store member starting a booking → 403 (member has no
    bookings:update; member is read-only across the booking surface)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await member_client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p3_start_hq_staff_403(hq_staff_client, db_session, test_env):
    """P-3h: hq_staff starting a booking → 403 (HQ is read-only; hq_staff has
    no store-side write role, and the store path requires bookings:update)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await hq_staff_client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p3_start_unauthenticated_401(test_env, db_session):
    """P-3i: no Authorization header → 401 (get_current_user refuses before
    the action runs). No DB seeding needed — the auth guard fires first, so
    the booking id is irrelevant (any id hits 401 before lookup)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/bookings/any-id/start"
        )
    assert resp.status_code == 401, resp.text


# --------------------------------------- P-4: end / no-show owner-only


@pytest.mark.asyncio
async def test_p4_end_owner_200_writes_feedback(
    app_client, db_session, test_env
):
    """P-4a: store owner ending an in_service booking → 200, ``ended_at`` set
    + ``feedback`` persisted. Owner is the only role with bookings:delete."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/end",
        headers=AUTH,
        json={"feedback": {"note": "服务顺利", "rating": 5}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["ended_at"] is not None
    assert body["feedback"] == {"note": "服务顺利", "rating": 5}


@pytest.mark.asyncio
async def test_p4_end_admin_403(tenant_admin_client, db_session, test_env):
    """P-4b: store admin ending a booking → 403. DEFAULT_ADMIN_PERMS omits
    bookings:delete (admin can't delete business records — same convention
    that makes admin unable to cancel). Plan §0 B2."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")

    resp = await tenant_admin_client.post(
        f"/api/v1/bookings/{booking.id}/end", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p4_end_customer_403(
    customer_client_factory, db_session, test_env
):
    """P-4c: customer ending a booking → 403 (end is store-staff-only;
    customer path is not even reachable — the customer_id branch is
    start-only)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")
    client = await customer_client_factory(customer_id=fixture["customer"].id)

    resp = await client.post(
        f"/api/v1/bookings/{booking.id}/end", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p4_end_member_403(member_client, db_session, test_env):
    """P-4d: store member ending a booking → 403 (no bookings:delete)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")

    resp = await member_client.post(
        f"/api/v1/bookings/{booking.id}/end", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p4_end_hq_staff_403(hq_staff_client, db_session, test_env):
    """P-4e: hq_staff ending a booking → 403 (HQ read-only)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")

    resp = await hq_staff_client.post(
        f"/api/v1/bookings/{booking.id}/end", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p4_no_show_owner_204(app_client, db_session, test_env):
    """P-4f: store owner no-showing a pending booking → 204 (pure status
    flip, no body, no timestamp written)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/no-show", headers=AUTH
    )
    assert resp.status_code == 204, resp.text
    # Re-fetch to confirm the status landed; started_at/ended_at stay null
    # (no_show owns no timestamp).
    get_resp = await app_client.get(
        f"/api/v1/bookings/{booking.id}", headers=AUTH
    )
    body = get_resp.json()
    assert body["status"] == "no_show"
    assert body["started_at"] is None
    assert body["ended_at"] is None


@pytest.mark.asyncio
async def test_p4_no_show_admin_403(
    tenant_admin_client, db_session, test_env
):
    """P-4g: store admin no-showing → 403 (no bookings:delete, same as end)."""
    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await tenant_admin_client.post(
        f"/api/v1/bookings/{booking.id}/no-show", headers=AUTH
    )
    assert resp.status_code == 403, resp.text


# --------------------------------------- P-5: cross-tenant → 404


@pytest.mark.asyncio
async def test_p5_cross_tenant_actions_return_404(
    app_client, db_session, test_env
):
    """P-5: operating on another tenant's booking → 404 for all three actions
    (no enumeration leak — ``_get_live_booking`` is tenant-scoped, so a foreign
    id collapses to NotFoundError just like a nonexistent one). Seeds a 2nd
    tenant with its own booking; the caller's tenant-scoped repo can't see it.
    """
    import uuid

    from app.models.booking import Booking
    from app.models.tenant import Tenant

    fixture = await _seed_lifecycle_fixture(db_session, test_env)

    # A booking in a foreign tenant (its own device, so the row is internally
    # consistent; the caller just can't see it).
    other_tenant_id = f"tnt-pwr-{uuid.uuid4().hex}"
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=fixture["model"].id,
        serial="PWR-OTHER-DEV",
    )
    db_session.add(Tenant(id=other_tenant_id, name="P 章节他租户"))
    start, end = _window(20, 1)
    other_booking = Booking(
        tenant_id=other_tenant_id,
        device_id=other_device.id,
        customer_id=None,
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    db_session.add(other_booking)
    await db_session.commit()

    for action in ("start", "end", "no-show"):
        resp = await app_client.post(
            f"/api/v1/bookings/{other_booking.id}/{action}", headers=AUTH
        )
        assert resp.status_code == 404, (
            f"{action} on foreign booking should be 404, got "
            f"{resp.status_code}: {resp.text}"
        )


@pytest.mark.asyncio
async def test_p5_cross_tenant_customer_start_404(
    customer_client_factory, db_session, test_env
):
    """P-5b: a customer principal starting a foreign-tenant booking → 404
    (not 403). The tenant-scoped fetch fires before the ownership check, so
    the caller learns nothing about whether the id exists elsewhere. The
    customer principal still carries a tenant_id, so the same _get_live_booking
    path applies."""
    import uuid

    from app.models.booking import Booking
    from app.models.tenant import Tenant

    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    other_tenant_id = f"tnt-pwrc-{uuid.uuid4().hex}"
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=fixture["model"].id,
        serial="PWR-OTHER-C-DEV",
    )
    db_session.add(Tenant(id=other_tenant_id, name="P 章节他租户(customer 路径)"))
    start, end = _window(22, 1)
    other_booking = Booking(
        tenant_id=other_tenant_id,
        device_id=other_device.id,
        customer_id=fixture["customer"].id,  # same global customer id
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    db_session.add(other_booking)
    await db_session.commit()

    client = await customer_client_factory(customer_id=fixture["customer"].id)
    resp = await client.post(
        f"/api/v1/bookings/{other_booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_p5_cross_tenant_non_owner_returns_404_not_403(
    tenant_admin_client, db_session, test_env
):
    """P-5c: a cross-tenant caller WITHOUT ``bookings:delete`` must still get
    404 (not 403) on ``end`` / ``no-show``. The tenant-scoped fetch runs BEFORE
    the permission check (mirrors ``start`` / plan §4.5), so a foreign booking
    collapses to NotFoundError before ``require`` ever runs — no enumeration
    leak regardless of the caller's role. ``tenant_admin_client`` is an admin
    in the CALLER's tenant (no delete perm), but the booking lives in another
    tenant entirely, so the 404 path fires first.
    """
    import uuid

    from app.models.booking import Booking
    from app.models.tenant import Tenant

    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    other_tenant_id = f"tnt-pwrno-{uuid.uuid4().hex}"
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=fixture["model"].id,
        serial="PWR-NO-OWNER-DEV",
    )
    db_session.add(Tenant(id=other_tenant_id, name="P 章节他租户(非 owner)"))
    start, end = _window(24, 1)
    other_booking = Booking(
        tenant_id=other_tenant_id,
        device_id=other_device.id,
        customer_id=None,
        status="in_service",  # so /end is a legal edge if it were reachable
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    db_session.add(other_booking)
    await db_session.commit()

    for action in ("end", "no-show"):
        resp = await tenant_admin_client.post(
            f"/api/v1/bookings/{other_booking.id}/{action}", headers=AUTH
        )
        assert resp.status_code == 404, (
            f"{action} by cross-tenant non-owner should be 404 (not 403), "
            f"got {resp.status_code}: {resp.text}"
        )


# ------------------------------------------- P-6: side-effect persistence


@pytest.mark.asyncio
async def test_p6_started_at_persisted_after_start(
    app_client, db_session, test_env
):
    """P-6a: ``started_at`` is non-None after a successful start. Re-reads
    from the DB (not just the response body) to confirm the column truly
    persisted, and that ``ended_at`` (owned by /end) stays None.

    We assert non-None rather than ``>= before`` because SQLite stores
    tz-aware datetimes as naive (drops the tzinfo on round-trip), so an
    aware-vs-naive comparison would raise — and the persistence itself, not
    the exact instant, is what this test pins. Postgres keeps the tz; both
    confirm the column was written."""
    from sqlalchemy import select

    from app.models.booking import Booking as BookingModel

    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/start", headers=AUTH
    )
    assert resp.status_code == 200, resp.text

    # Re-read the row from the DB (separate session) to prove persistence.
    async with test_env.factory() as session:
        row = (
            await session.execute(
                select(BookingModel).where(BookingModel.id == booking.id)
            )
        ).scalar_one()
        assert row.status == "in_service"
        assert row.started_at is not None
        # end's column stays untouched.
        assert row.ended_at is None


@pytest.mark.asyncio
async def test_p6_ended_at_and_feedback_persisted_after_end(
    app_client, db_session, test_env
):
    """P-6b: ``ended_at`` + ``feedback`` round-trip through the DB after end.
    The feedback dict survives verbatim (SQLAlchemy JSON column, not JSONB —
    SQLite and Postgres behave identically). ``ended_at`` is asserted non-None
    (see P-6a for why we don't compare instants across SQLite's tz drop)."""
    from sqlalchemy import select

    from app.models.booking import Booking as BookingModel

    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")
    payload = {"rating": 4, "tags": ["friendly", "on-time"], "note": "测试反馈"}

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/end",
        headers=AUTH,
        json={"feedback": payload},
    )
    assert resp.status_code == 200, resp.text

    async with test_env.factory() as session:
        row = (
            await session.execute(
                select(BookingModel).where(BookingModel.id == booking.id)
            )
        ).scalar_one()
        assert row.status == "done"
        assert row.ended_at is not None
        assert row.feedback == payload


@pytest.mark.asyncio
async def test_p6_end_without_feedback_leaves_column_null(
    app_client, db_session, test_env
):
    """P-6c: ending with no body (or feedback: null) leaves the ``feedback``
    column at its previous value (None for a fresh booking) — the endpoint
    treats feedback as optional and only writes when provided."""
    from sqlalchemy import select

    from app.models.booking import Booking as BookingModel

    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"](status="in_service")

    # No body at all — FastAPI treats the optional payload as None.
    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/end", headers=AUTH
    )
    assert resp.status_code == 200, resp.text

    async with test_env.factory() as session:
        row = (
            await session.execute(
                select(BookingModel).where(BookingModel.id == booking.id)
            )
        ).scalar_one()
        assert row.status == "done"
        assert row.feedback is None


@pytest.mark.asyncio
async def test_p6_no_show_writes_no_timestamp(
    app_client, db_session, test_env
):
    """P-6d: no-show writes neither ``started_at`` nor ``ended_at`` — it's a
    pure status flip. ``started_at`` / ``ended_at`` are owned by start / end
    respectively (plan §0 D4); a no-show records nothing about when the
    absence was judged."""
    from sqlalchemy import select

    from app.models.booking import Booking as BookingModel

    fixture = await _seed_lifecycle_fixture(db_session, test_env)
    booking = await fixture["make_booking"]()

    resp = await app_client.post(
        f"/api/v1/bookings/{booking.id}/no-show", headers=AUTH
    )
    assert resp.status_code == 204, resp.text

    async with test_env.factory() as session:
        row = (
            await session.execute(
                select(BookingModel).where(BookingModel.id == booking.id)
            )
        ).scalar_one()
        assert row.status == "no_show"
        assert row.started_at is None
        assert row.ended_at is None
