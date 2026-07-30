"""Device API tests — slice 01 (within-store CRUD + integrity guards) + slice 03
HQ panorama (E chapter) + slice 04 bind/unbind (F chapter) +
platform-cross-tenant-write slice 01 (P chapter).

NOTE: the former "K. backfill (slice 02)" chapter moved to
``tests/test_permission_backfill.py`` in perm-backfill-dedupe and is now
parametrized across devices + bookings (see plan-perm-backfill-dedupe.md §5).

Chapter layout (matches plan-devices-crud-ui.md §8 + §10 + slice 03/04 +
plan-platform-cross-tenant-write.md §6 切片 01):
- A. owner/admin CRUD — create + list + get + update + delete, full-field assertions
- B. cross-tenant isolation — devices in tnt-iso-2 invisible; GET/PUT/DELETE → 404
- C. (tenant_id, serial_number) uniqueness — duplicate 400, reusable after soft delete
- D. permission matrix — member read-only (write → 403); unauth → 401
- E. HQ panorama (slice 03) — super_admin + hq_staff cross-tenant read with the
  ``DeviceHqRead`` panorama fields (tenant_name / model_name / customer_name);
  hq_staff writes without tenant_id → 400 (was 403 before platform-cross-tenant-write).
- F. bind/unbind (slice 04):
  - F1 bind success → 200 + already_bound:false
  - F2 bind same customer again → 200 + already_bound:true (idempotent, no write)
  - F3 bind a different customer (overwrite) → 200 + already_bound:false
  - F4 unbind success → 204
  - F5 unbind a device with no binding → 204 (idempotent no-op, NOT 404)
  - F6 bind a customer that exists only in another tenant → 400 BizError
  - F7 bind a nonexistent customer → 400 BizError
  - F8 member bind → 403 (no devices:update)
- G. status transitions — active↔maintenance↔retired all legal; bad value → 422
- H. model_id integrity (service-layer guard, NOT FK RESTRICT which is a dead-bolt):
  - H1 create with soft-deleted model_id → 400 BizError
  - H2 create with nonexistent model_id → 400 BizError
  - H3 update pointing at soft-deleted model → 400 BizError
  - H4 device referencing a soft-deleted model still GETs fine
  - H5 (behavioural note only, no test — covered by device-models API tests)
- (K. backfill chapter moved to tests/test_permission_backfill.py — parametrized)
- P. platform-cross-tenant-write slice 01 — super_admin + hq_staff cross-tenant
  writes on devices (POST/PUT/DELETE/bind/unbind), with payload.tenant_id =
  target store. Plus reverse anti-forgery guards (store roles carrying
  tenant_id → 400) and the helper contract (``is_platform_writer``,
  ``resolve_target_tenant``).
  - P0 helper contract: ``is_platform_writer`` + ``resolve_target_tenant`` unit
  - P1 super_admin / hq_staff POST {tenant_id} → 201 (cross-tenant create)
  - P2 super_admin / hq_staff PUT {tenant_id} on target-store device → 200
  - P3 super_admin / hq_staff DELETE ?tenant_id on target-store device → 204
  - P4 super_admin / hq_staff bind {tenant_id, customer_id} on target → 200
  - P5 super_admin / hq_staff unbind ?tenant_id on target-store device → 204
  - P6 platform writer POST without tenant_id → 400 (D1 必填)
  - P7 store role POST with tenant_id: owner/admin → 400 (D1-2 anti-forgery);
    member/customer → 403 (router casbin refuses before service body — a forged
    tenant_id does NOT unlock writes for roles lacking them)
  - P8 platform writer POST {tenant_id, customer_id=<目标店 customer>} → 201 (D2-ii)
  - P9 platform writer POST {tenant_id, customer_id=<不存在>} → 400 (guard fires)

Test-organization note (matches test_device_models_api.py): each test uses ONE
client fixture. Mixing super_admin_client with app_client/member_client in the
same function would corrupt the shared ``owner`` user (super_admin_client
mutates owner.platform_role to super_admin, leaking into app_client's view).
"""

from decimal import Decimal

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ---------------------------------------------------------------- helpers


async def _seed_model(db_session, **overrides):
    """Insert a DeviceModel row directly (bypass the API).

    Devices reference device_models via FK; tests need a model row to exist
    before any device can be created.
    """
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
    """Insert a Device row directly (bypass the API)."""
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


async def _seed_customer(db_session, *, name, identity_key, **overrides):
    """Insert a global Customer row directly (for the HQ ``customer_name`` field).

    Devices reference the *global* Customer (not CustomerProfile), so the HQ
    panorama's ``customer_name`` comes from ``Customer.name``. Seeded directly
    because creating one through the customers API would pull in the full
    profile machinery and tenant-scope the write — we just need an identity
    row to bind a device to.
    """
    from app.models.customer import Customer

    defaults = {"name": name, "identity_key": identity_key}
    defaults.update(overrides)
    customer = Customer(**defaults)
    db_session.add(customer)
    await db_session.commit()
    return customer


async def _seed_customer_with_profile(
    db_session, *, tenant_id, name, identity_key=None, **overrides
):
    """Insert a global Customer + a live ``CustomerProfile`` in ``tenant_id``.

    This is what the bind endpoint actually validates against — bind checks
    "does this ``customer_id`` have a live ``CustomerProfile`` in *my*
    tenant" (via ``CustomerProfileRepository.get_by_customer_tenant``), so a
    bare global Customer with no profile in this tenant is unbinddable.
    Returns ``(customer, profile)``.
    """
    import uuid

    from app.models.customer import CustomerProfile

    if identity_key is None:
        # identity_key is globally unique among live rows; keep it unique so
        # multiple F-chapter customers don't collide on the partial index.
        identity_key = f"phone-{uuid.uuid4().hex}"
    customer = await _seed_customer(
        db_session, name=name, identity_key=identity_key
    )
    profile = CustomerProfile(
        customer_id=customer.id,
        tenant_id=tenant_id,
        status=overrides.pop("status", "active"),
        **overrides,
    )
    db_session.add(profile)
    await db_session.commit()
    return customer, profile


# ----------------------------------------------------- A. owner/admin CRUD


@pytest.mark.asyncio
async def test_owner_create_list_get_update_delete(app_client, db_session):
    """Full CRUD round-trip as the tenant owner. Asserts every field on the
    read DTO so a schema-shape regression (added/renamed field) surfaces."""
    model = await _seed_model(db_session, name="BP-Chamber-X100")
    # create
    resp = await app_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "SN-001",
            "status": "active",
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["model_id"] == model.id
    assert body["serial_number"] == "SN-001"
    assert body["status"] == "active"
    assert body["customer_id"] is None
    assert body["created_by"] is not None  # owner user id
    assert "id" in body and "tenant_id" in body
    assert "created_at" in body and "updated_at" in body
    device_id = body["id"]

    # list
    resp = await app_client.get("/api/v1/devices/", headers=AUTH)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == device_id

    # get
    resp = await app_client.get(f"/api/v1/devices/{device_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["serial_number"] == "SN-001"

    # update (status + serial)
    resp = await app_client.put(
        f"/api/v1/devices/{device_id}",
        json={"status": "maintenance", "serial_number": "SN-001-renamed"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["status"] == "maintenance"
    assert updated["serial_number"] == "SN-001-renamed"
    # Unchanged fields preserved.
    assert updated["model_id"] == model.id

    # delete (soft)
    resp = await app_client.delete(
        f"/api/v1/devices/{device_id}", headers=AUTH
    )
    assert resp.status_code == 204
    # List no longer contains it.
    resp = await app_client.get("/api/v1/devices/", headers=AUTH)
    assert all(d["id"] != device_id for d in resp.json())
    # Direct GET → 404.
    resp = await app_client.get(f"/api/v1/devices/{device_id}", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_read_create_update_but_not_delete(
    tenant_admin_client, db_session
):
    """admin has devices:read/create/update (not delete) — mirrors the
    customer convention."""
    model = await _seed_model(db_session, name="AdminModel")
    resp = await tenant_admin_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "ADM-1"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    device_id = resp.json()["id"]

    resp = await tenant_admin_client.put(
        f"/api/v1/devices/{device_id}",
        json={"status": "retired"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "retired"

    resp = await tenant_admin_client.get("/api/v1/devices/", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # admin has no devices:delete → 403.
    resp = await tenant_admin_client.delete(
        f"/api/v1/devices/{device_id}", headers=AUTH
    )
    assert resp.status_code == 403


# ---------------------------------------------- B. cross-tenant isolation


@pytest.mark.asyncio
async def test_cross_tenant_get_put_delete_returns_404(
    app_client, db_session, test_env
):
    """Devices in another tenant are invisible: GET/PUT/DELETE all 404 (no
    'exists but not yours' leak → no enumeration)."""
    model = await _seed_model(db_session, name="IsoModel")
    # Seed a device in ANOTHER tenant.
    other_tenant_id = f"tnt-iso-{__import__('uuid').uuid4().hex}"
    from app.models.tenant import Tenant

    db_session.add(Tenant(id=other_tenant_id, name="Iso Tenant"))
    await db_session.commit()
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=model.id,
        serial="ISO-1",
    )

    # The owner (test_env.tenant_id) cannot see other_tenant_id's device.
    resp = await app_client.get(
        f"/api/v1/devices/{other_device.id}", headers=AUTH
    )
    assert resp.status_code == 404
    resp = await app_client.put(
        f"/api/v1/devices/{other_device.id}",
        json={"status": "retired"},
        headers=AUTH,
    )
    assert resp.status_code == 404
    resp = await app_client.delete(
        f"/api/v1/devices/{other_device.id}", headers=AUTH
    )
    assert resp.status_code == 404
    # List scoped to caller's tenant → empty.
    resp = await app_client.get("/api/v1/devices/", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []


# --------------------------------- C. (tenant_id, serial_number) uniqueness


@pytest.mark.asyncio
async def test_duplicate_serial_in_same_tenant_400(app_client, db_session):
    model = await _seed_model(db_session, name="DupModel")
    resp = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "DUP"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    resp = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "DUP"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_serial_reusable_after_soft_delete(app_client, db_session):
    """Partial unique index exempts soft-deleted rows: a deleted device's
    serial can be reused."""
    model = await _seed_model(db_session, name="ReuseModel")
    create = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "REUSE"},
        headers=AUTH,
    )
    did = create.json()["id"]
    resp = await app_client.delete(f"/api/v1/devices/{did}", headers=AUTH)
    assert resp.status_code == 204
    # Now REUSE is free again.
    resp = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "REUSE"},
        headers=AUTH,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_update_serial_to_existing_in_use_400(app_client, db_session):
    """Renaming device A's serial to device B's in-use serial → 400."""
    model = await _seed_model(db_session, name="RenameModel")
    a = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "A"},
        headers=AUTH,
    )
    await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "B"},
        headers=AUTH,
    )
    resp = await app_client.put(
        f"/api/v1/devices/{a.json()['id']}",
        json={"serial_number": "B"},
        headers=AUTH,
    )
    assert resp.status_code == 400


# ----------------------------------------- D. permission matrix + unauth


@pytest.mark.asyncio
async def test_member_read_only_end_to_end(member_client, db_session, test_env):
    """member has devices:read only — writes (create/update/delete) → 403.

    Data is seeded via db_session in the shared test_env tenant so we don't
    have to mix the owner-writing-then-member-reading pattern (which would
    require two clients in one test and risk mutating the shared owner).
    """
    model = await _seed_model(db_session, name="MemberRO")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="MEM-RO",
    )
    # member can read the list.
    resp = await member_client.get("/api/v1/devices/", headers=AUTH)
    assert resp.status_code == 200
    assert any(d["id"] == device.id for d in resp.json())
    # member can read one.
    resp = await member_client.get(
        f"/api/v1/devices/{device.id}", headers=AUTH
    )
    assert resp.status_code == 200
    # member cannot create.
    resp = await member_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "MEM-NEW"},
        headers=AUTH,
    )
    assert resp.status_code == 403
    # member cannot update.
    resp = await member_client.put(
        f"/api/v1/devices/{device.id}",
        json={"status": "retired"},
        headers=AUTH,
    )
    assert resp.status_code == 403
    # member cannot delete.
    resp = await member_client.delete(
        f"/api/v1/devices/{device.id}", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_401(test_env):
    """No Authorization header → 401 (get_current_user raises 401)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/devices/")
        assert resp.status_code == 401


# ----------------------------------------- E. HQ panorama (slice 03)
#
# super_admin and hq_staff are cross-tenant viewers: ``GET /`` and
# ``GET /{id}`` return the ``DeviceHqRead`` panorama across EVERY tenant,
# carrying ``tenant_name`` / ``model_name`` / ``customer_name``. hq_staff is
# read-only — writes (create/update/delete) fall through to casbin where the
# member tenant role (no devices:create/update/delete) → 403.
#
# Each test uses ONE client fixture (see the file header note): super_admin
# tests use ``super_admin_client``, hq_staff tests use ``hq_staff_client``.
# Cross-tenant device data is seeded directly via db_session (the client's
# tenant is test_env.tenant_id; we add a second tenant + device to prove the
# panorama sees across the boundary).


async def _seed_two_tenant_devices(db_session, test_env):
    """Seed a model + a customer + one device in EACH of two tenants.

    Returns ``(own_device, other_device, other_tenant_id, customer, model)``
    so E-chapter tests can assert cross-tenant visibility + panorama fields
    without each test re-doing the setup. ``own_device`` is bound to the
    global Customer so ``customer_name`` is non-null on it; ``other_device``
    has no binding (``customer_name`` is None — also worth asserting).
    """
    import uuid

    from app.models.tenant import Tenant

    model = await _seed_model(db_session, name="HQ-Pano-Model")
    customer = await _seed_customer(
        db_session, name="张三", identity_key="phone-13800000000"
    )
    # Device in the caller's own tenant (test_env.tenant_id), customer-bound.
    own_device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="HQ-OWN",
        customer_id=customer.id,
    )
    # Device in a SECOND tenant (no customer binding).
    other_tenant_id = f"tnt-hq-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="HQ Other Tenant"))
    await db_session.commit()
    other_device = await _seed_device(
        db_session,
        tenant_id=other_tenant_id,
        model_id=model.id,
        serial="HQ-OTHER",
    )
    return own_device, other_device, other_tenant_id, customer, model


@pytest.mark.asyncio
async def test_super_admin_list_returns_hq_panorama(
    super_admin_client, db_session, test_env
):
    """super_admin ``GET /`` returns ``DeviceHqRead`` across every tenant —
    including the panorama fields tenant_name / model_name / customer_name,
    and devices from tenants other than the caller's own."""
    own, other, other_tenant_id, customer, model = await _seed_two_tenant_devices(
        db_session, test_env
    )
    resp = await super_admin_client.get("/api/v1/devices/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    items = {d["id"]: d for d in resp.json()}
    # Both tenants' devices are visible (cross-tenant panorama).
    assert own.id in items
    assert other.id in items
    # Panorama fields populated on the own-tenant device.
    own_row = items[own.id]
    assert own_row["tenant_id"] == test_env.tenant_id
    assert own_row["tenant_name"] == "Test Tenant"
    assert own_row["model_name"] == model.name
    assert own_row["customer_name"] == customer.name
    # The other-tenant device carries the other tenant's name; no customer
    # binding → customer_name is None (not omitted, not error).
    other_row = items[other.id]
    assert other_row["tenant_id"] == other_tenant_id
    assert other_row["tenant_name"] == "HQ Other Tenant"
    assert other_row["model_name"] == model.name
    assert other_row["customer_name"] is None


@pytest.mark.asyncio
async def test_super_admin_get_one_returns_hq_panorama(
    super_admin_client, db_session, test_env
):
    """super_admin ``GET /{id}`` on ANOTHER tenant's device returns 200 +
    ``DeviceHqRead`` (the HQ viewer can read any tenant's device; no 404)."""
    _own, other, _other_tenant_id, _customer, model = (
        await _seed_two_tenant_devices(db_session, test_env)
    )
    resp = await super_admin_client.get(
        f"/api/v1/devices/{other.id}", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == other.id
    assert body["model_name"] == model.name
    assert body["tenant_name"] == "HQ Other Tenant"
    # ``customer_name`` is present even on an unbound device (None, not absent).
    assert body["customer_name"] is None


@pytest.mark.asyncio
async def test_hq_staff_list_returns_hq_panorama(
    hq_staff_client, db_session, test_env
):
    """hq_staff sees the same panorama as super_admin on reads — the bypass
    is ``permission_service.check``'s ``hq_staff`` + ``read`` short-circuit.
    This is the core regression guard for slice 03: before slice 03, the
    router-level ``require_permission("devices","read")`` 403'd hq_staff."""
    own, other, _other_tenant_id, customer, model = (
        await _seed_two_tenant_devices(db_session, test_env)
    )
    resp = await hq_staff_client.get("/api/v1/devices/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    items = {d["id"]: d for d in resp.json()}
    assert own.id in items and other.id in items
    own_row = items[own.id]
    assert own_row["tenant_name"] == "Test Tenant"
    assert own_row["model_name"] == model.name
    assert own_row["customer_name"] == customer.name


@pytest.mark.asyncio
async def test_hq_staff_write_without_tenant_id_400(hq_staff_client, db_session, test_env):
    """hq_staff is a platform writer on devices: writes are allowed through
    ``check`` (plan-platform-cross-tenant-write §4.5.4 — the bypass lives in
    ``check``, not the router dependency), but the service body's
    ``resolve_target_tenant`` REQUIRES ``payload.tenant_id`` for platform
    writers → 400 when it's missing (D1 必填守卫).

    This test was ``test_hq_staff_writes_are_403`` before slice 01; the old
    403 came from ``check`` falling through to casbin (hq_staff had no
    devices:create). Slice 01 lifts hq_staff to a platform writer on devices,
    so the failure mode shifts from 403 (casbin deny) to 400 (missing target
    tenant). The 200/201 success path is covered by the P chapter below.
    """
    model = await _seed_model(db_session, name="HQ-Write-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="HQ-WRITE",
    )
    resp = await hq_staff_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "HQ-NEW"},
        headers=AUTH,
    )
    assert resp.status_code == 400
    resp = await hq_staff_client.put(
        f"/api/v1/devices/{device.id}",
        json={"status": "retired"},
        headers=AUTH,
    )
    assert resp.status_code == 400
    resp = await hq_staff_client.delete(
        f"/api/v1/devices/{device.id}", headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_hq_get_soft_deleted_device_returns_404(
    super_admin_client, db_session, test_env
):
    """HQ ``GET /{id}`` on a soft-deleted device → 404 (the panorama excludes
    soft-deleted rows, same as the within-store path). Guards against the HQ
    branch accidentally surfacing tombstones."""
    model = await _seed_model(db_session, name="HQ-SoftDel-Model")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial="HQ-SOFTDEL",
        is_deleted=True,
    )
    resp = await super_admin_client.get(
        f"/api/v1/devices/{device.id}", headers=AUTH
    )
    assert resp.status_code == 404


# ------------------------------------------------ F. bind/unbind (slice 04)
#
# Bind is a POST-to-sub-resource action: ``POST /devices/{id}/bind`` returns
# **200, not 201** (the device already exists; bind is an assignment). The
# body carries ``already_bound`` so a client can tell "newly bound" from
# "idempotent repeat of the same customer". unbind (``DELETE``) returns 204
# even on an unbound device — DELETE is idempotent by REST convention, which
# saves the client a GET-then-DELETE round-trip.
#
# Bind guard is ``require_permission("devices", "update")`` (owner/admin),
# NOT ``require_super_admin``: devices is a tenant-level resource, binding a
# customer is a within-store business action (group attach uses super_admin
# only because group is platform-level — don't conflate).
#
# Bind requires the ``customer_id`` to have a *live* ``CustomerProfile`` in
# the caller's tenant (Customer is a platform-level identity; the per-tenant
# profile is what makes them "this store's customer"). A nonexistent customer
# and a customer that exists only in another tenant both collapse to the same
# 400 — no enumeration leak (mirrors the device cross-tenant → 404 defence).


async def _seed_device_in_test_tenant(db_session, test_env, *, serial):
    """F-chapter helper: one model + one unbound device in test_env's tenant.

    F tests mostly start from an unbound device and a customer-with-profile,
    so this keeps the boilerplate in one place. The device has ``customer_id
    = None`` — bind tests assert the before/after.
    """
    model = await _seed_model(db_session, name=f"F-Model-{serial}")
    device = await _seed_device(
        db_session,
        tenant_id=test_env.tenant_id,
        model_id=model.id,
        serial=serial,
    )
    return device


@pytest.mark.asyncio
async def test_f1_bind_success_200_already_bound_false(
    app_client, db_session, test_env
):
    """F1: bind an unbound device → 200 + ``already_bound: false``. A new
    binding was written."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F1")
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="F1-客户"
    )
    resp = await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": customer.id},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["device_id"] == device.id
    assert body["customer_id"] == customer.id
    assert body["already_bound"] is False
    # The binding actually persisted.
    get = await app_client.get(f"/api/v1/devices/{device.id}", headers=AUTH)
    assert get.json()["customer_id"] == customer.id


@pytest.mark.asyncio
async def test_f2_bind_same_customer_idempotent_200_already_bound_true(
    app_client, db_session, test_env
):
    """F2: bind the SAME customer twice → second call is 200 +
    ``already_bound: true`` and writes nothing (idempotent)."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F2")
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="F2-客户"
    )
    first = await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": customer.id},
        headers=AUTH,
    )
    assert first.json()["already_bound"] is False
    # Second bind, same customer → idempotent no-op.
    second = await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": customer.id},
        headers=AUTH,
    )
    assert second.status_code == 200, second.text
    assert second.json()["already_bound"] is True
    assert second.json()["customer_id"] == customer.id


@pytest.mark.asyncio
async def test_f3_bind_different_customer_overwrites_200(
    app_client, db_session, test_env
):
    """F3: bind customer A, then bind customer B → second call is 200 +
    ``already_bound: false`` (overwrite, not idempotent). Binding now points
    at B."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F3")
    cust_a, _pa = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="F3-A"
    )
    cust_b, _pb = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="F3-B"
    )
    await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": cust_a.id},
        headers=AUTH,
    )
    resp = await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": cust_b.id},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["already_bound"] is False
    assert body["customer_id"] == cust_b.id
    get = await app_client.get(f"/api/v1/devices/{device.id}", headers=AUTH)
    assert get.json()["customer_id"] == cust_b.id


@pytest.mark.asyncio
async def test_f4_unbind_success_204(app_client, db_session, test_env):
    """F4: unbind a bound device → 204, and the device now has no customer."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F4")
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="F4-客户"
    )
    await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": customer.id},
        headers=AUTH,
    )
    resp = await app_client.delete(
        f"/api/v1/devices/{device.id}/bind", headers=AUTH
    )
    assert resp.status_code == 204
    get = await app_client.get(f"/api/v1/devices/{device.id}", headers=AUTH)
    assert get.json()["customer_id"] is None


@pytest.mark.asyncio
async def test_f5_unbind_unbound_device_204_idempotent(
    app_client, db_session, test_env
):
    """F5: unbind a device that was NEVER bound → 204 (DELETE idempotent
    no-op, NOT 404). Avoids forcing the client to GET-then-DELETE."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F5")
    resp = await app_client.delete(
        f"/api/v1/devices/{device.id}/bind", headers=AUTH
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_f6_bind_customer_from_other_tenant_400(
    app_client, db_session, test_env
):
    """F6: bind a customer whose only ``CustomerProfile`` is in ANOTHER
    tenant → 400. The customer identity exists globally, but it's not "this
    store's customer" → bind refused (and indistinguishable from a
    nonexistent customer — no enumeration)."""
    import uuid

    from app.models.tenant import Tenant

    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F6")
    # A customer with a profile in a DIFFERENT tenant.
    other_tenant_id = f"tnt-f6-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_tenant_id, name="F6 Other Tenant"))
    await db_session.commit()
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=other_tenant_id, name="F6-外店客户"
    )
    resp = await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": customer.id},
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_f7_bind_nonexistent_customer_400(app_client, db_session, test_env):
    """F7: bind a customer id that doesn't exist at all → 400. Collapses to
    the same BizError as F6 (no way to tell "exists elsewhere" from "never
    existed" — enumeration defence)."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F7")
    resp = await app_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": "cust-does-not-exist"},
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_f8_member_bind_403(member_client, db_session, test_env):
    """F8: member has no ``devices:update`` → bind is 403 (and unbind too).
    member is read-only across the whole devices surface, bind included."""
    device = await _seed_device_in_test_tenant(db_session, test_env, serial="F8")
    customer, _profile = await _seed_customer_with_profile(
        db_session, tenant_id=test_env.tenant_id, name="F8-客户"
    )
    resp = await member_client.post(
        f"/api/v1/devices/{device.id}/bind",
        json={"customer_id": customer.id},
        headers=AUTH,
    )
    assert resp.status_code == 403
    resp = await member_client.delete(
        f"/api/v1/devices/{device.id}/bind", headers=AUTH
    )
    assert resp.status_code == 403


# ----------------------------------------- G. status transitions + bad value


@pytest.mark.asyncio
async def test_status_transitions_all_legal(app_client, db_session):
    """active → maintenance → retired → active — every transition is legal
    (no state machine here, just a field set)."""
    model = await _seed_model(db_session, name="StatusFlow")
    create = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "FLOW"},
        headers=AUTH,
    )
    did = create.json()["id"]
    for next_status in ("maintenance", "retired", "active"):
        resp = await app_client.put(
            f"/api/v1/devices/{did}",
            json={"status": next_status},
            headers=AUTH,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == next_status


@pytest.mark.asyncio
async def test_status_invalid_value_422(app_client, db_session):
    """Bad status value → Pydantic Literal rejects it as 422 (the DB CHECK
    constraint is defence-in-depth; the schema is the front guard)."""
    model = await _seed_model(db_session, name="BadStatus")
    resp = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "BAD", "status": "online"},
        headers=AUTH,
    )
    assert resp.status_code == 422


# ----------------------------------------- H. model_id integrity (service)


@pytest.mark.asyncio
async def test_h1_create_with_soft_deleted_model_400(app_client, db_session):
    """Soft-deleted model_id → BizError 400 (the real guard; FK RESTRICT
    never fires under soft-delete-only DeviceModelService.delete)."""
    model = await _seed_model(db_session, name="SoftDeleted")
    # Soft-delete via ORM (the production delete path is also soft).
    from datetime import UTC, datetime

    from app.models.device_model import DeviceModel

    fresh = await db_session.get(DeviceModel, model.id)
    assert fresh is not None
    fresh.is_deleted = True
    fresh.deleted_at = datetime.now(UTC)
    await db_session.commit()

    resp = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "ANY"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_h2_create_with_nonexistent_model_400(app_client):
    """Nonexistent model_id → BizError 400 (no FK violation leaks out as 500)."""
    resp = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": "model-does-not-exist", "serial_number": "ANY"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_h3_update_to_soft_deleted_model_400(app_client, db_session):
    """Re-pointing a device at a soft-deleted model → 400."""
    from datetime import UTC, datetime

    from app.models.device_model import DeviceModel

    live = await _seed_model(db_session, name="Live")
    dead = await _seed_model(db_session, name="Dead")
    dead_row = await db_session.get(DeviceModel, dead.id)
    assert dead_row is not None
    dead_row.is_deleted = True
    dead_row.deleted_at = datetime.now(UTC)
    await db_session.commit()

    create = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": live.id, "serial_number": "POINT"},
        headers=AUTH,
    )
    did = create.json()["id"]
    resp = await app_client.put(
        f"/api/v1/devices/{did}",
        json={"model_id": dead.id},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_h4_device_referencing_soft_deleted_model_still_gets(app_client, db_session):
    """If a device's model is soft-deleted AFTER the device was created, the
    device still reads back fine (FK RESTRICT is a dead-bolt; the model row
    physically remains, just flagged is_deleted). The model picker UX on the
    frontend will grey it out — backend just returns the data."""
    from datetime import UTC, datetime

    from app.models.device_model import DeviceModel

    model = await _seed_model(db_session, name="LaterDeleted")
    create = await app_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "SURVIVE"},
        headers=AUTH,
    )
    did = create.json()["id"]
    # Soft-delete the model after the device exists.
    row = await db_session.get(DeviceModel, model.id)
    assert row is not None
    row.is_deleted = True
    row.deleted_at = datetime.now(UTC)
    await db_session.commit()

    resp = await app_client.get(f"/api/v1/devices/{did}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["model_id"] == model.id


# ----------------------------------------- P. platform-cross-tenant-write slice 01
#
# Platform writers (super_admin + hq_staff) unlock cross-tenant WRITES on
# devices: POST/PUT/DELETE/bind/unbind carrying ``payload.tenant_id`` (= the
# target store). The casbin ``require`` in the service body is skipped (hq_staff
# has no tenant role); ``resolve_target_tenant`` enforces two guards:
#   * platform writer missing tenant_id → 400 (D1 必填)
#   * store role carrying tenant_id → 400 (D1-2 防伪造)
#
# Plan patch (recorded in plan §4.5.4): for hq_staff writes to actually reach
# the service body, ``permission_service.check`` must bypass casbin for
# platform writers on devices/bookings — otherwise the router-level
# ``require_permission`` dependency 403's hq_staff before the service runs
# (hq_staff's casbin role "member" lacks devices:create/update/delete). The
# bypass is scoped to (``is_platform_writer`` AND obj in {devices, bookings});
# customers/groups/users stay read-only for hq_staff (Out of Scope).
#
# DELETE has no body, so ``tenant_id`` rides as a query param on delete/unbind
# (``?tenant_id=<target>``); POST/PUT/bind carry it in the body. Store roles
# omit it entirely (anti-forgery).
#
# Each P test seeds its own target tenant + model + (sometimes) device, so it
# does not depend on which second tenant a platform fixture happened to create.
# Platform-writer tests use ``super_admin_client`` OR ``hq_staff_client``; the
# reverse anti-forgery tests (P7) use the store-role fixtures (one per role).


async def _seed_target_tenant_with_model(db_session, *, name="P Target"):
    """Fresh tenant + a model row visible to it (models are platform-level, so
    one model serves every tenant). Returns ``(target_tenant_id, model)``.

    Tenant id stays ≤32 chars (the DB column width) — ``tnt-p-`` + 24 hex."""
    import uuid

    from app.models.tenant import Tenant

    target_tenant_id = f"tnt-p-{uuid.uuid4().hex[:24]}"
    db_session.add(Tenant(id=target_tenant_id, name=name))
    await db_session.commit()
    model = await _seed_model(db_session, name=f"P-Model-{target_tenant_id[-8:]}")
    return target_tenant_id, model


@pytest.mark.asyncio
async def test_p0_helper_contract():
    """P0: ``is_platform_writer`` boundary = {super_admin, hq_staff};
    ``resolve_target_tenant`` resolves correctly for all 4 input combos.

    Pure-function contract test (no DB) — mirrors how ``is_cross_tenant_viewer``
    is tested in test_hq_platform_role.py.
    """
    from app.services._tenant_target import resolve_target_tenant
    from app.services.errors import BizError
    from app.services.permission_service import is_platform_writer

    # Boundary: super_admin + hq_staff are writers; everything else is not.
    assert is_platform_writer("super_admin") is True
    assert is_platform_writer("hq_staff") is True
    assert is_platform_writer(None) is False
    assert is_platform_writer("owner") is False
    assert is_platform_writer("customer") is False

    # Platform writer + tenant_id → that tenant.
    assert (
        resolve_target_tenant("user-tnt", "payload-tnt", "super_admin")
        == "payload-tnt"
    )
    assert (
        resolve_target_tenant("user-tnt", "payload-tnt", "hq_staff")
        == "payload-tnt"
    )
    # Platform writer without tenant_id → 400 (D1 必填).
    with pytest.raises(BizError):
        resolve_target_tenant("user-tnt", None, "super_admin")
    with pytest.raises(BizError):
        resolve_target_tenant("user-tnt", None, "hq_staff")
    # Store role without tenant_id → user.tenant_id.
    assert resolve_target_tenant("user-tnt", None, None) == "user-tnt"
    assert resolve_target_tenant("user-tnt", None, "owner") == "user-tnt"
    # Store role carrying tenant_id → 400 (D1-2 防伪造).
    with pytest.raises(BizError):
        resolve_target_tenant("user-tnt", "payload-tnt", None)
    with pytest.raises(BizError):
        resolve_target_tenant("user-tnt", "payload-tnt", "owner")


@pytest.mark.asyncio
async def test_p1_platform_writer_create_cross_tenant(
    super_admin_client, hq_staff_client, db_session, test_env
):
    """P1: super_admin + hq_staff POST /devices/ with ``tenant_id`` → 201,
    creating a device in the TARGET store (not their own). Verifies the device
    physically lands in the target tenant via a direct DB read."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)

    # super_admin creates in target store.
    resp = await super_admin_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P1-SA",
            "tenant_id": target_tenant_id,
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    sa_body = resp.json()
    assert sa_body["tenant_id"] == target_tenant_id

    # hq_staff creates in target store (a different serial — uniqueness guard
    # is per-tenant, but keep serials distinct to avoid confusion).
    resp = await hq_staff_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P1-HQ",
            "tenant_id": target_tenant_id,
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    hq_body = resp.json()
    assert hq_body["tenant_id"] == target_tenant_id

    # Physically verify both devices landed in the target tenant.
    from app.models.device import Device

    rows = (
        await db_session.execute(
            Device.__table__.select().where(
                Device.__table__.c.tenant_id == target_tenant_id
            )
        )
    ).mappings().all()
    serials = {r["serial_number"] for r in rows}
    assert {"P1-SA", "P1-HQ"} <= serials, serials


@pytest.mark.asyncio
async def test_p2_platform_writer_update_cross_tenant(
    super_admin_client, hq_staff_client, db_session, test_env
):
    """P2: super_admin + hq_staff PUT /devices/{id} with ``tenant_id`` → 200,
    mutating a device that lives in the target store."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)
    # Seed a device in the target store (the platform writer will mutate it).
    sa_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P2-SA-SEED",
    )
    hq_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P2-HQ-SEED",
    )

    resp = await super_admin_client.put(
        f"/api/v1/devices/{sa_device.id}",
        json={"tenant_id": target_tenant_id, "status": "retired"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "retired"

    resp = await hq_staff_client.put(
        f"/api/v1/devices/{hq_device.id}",
        json={"tenant_id": target_tenant_id, "status": "maintenance"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "maintenance"


@pytest.mark.asyncio
async def test_p3_platform_writer_delete_cross_tenant(
    super_admin_client, hq_staff_client, db_session, test_env
):
    """P3: super_admin + hq_staff DELETE /devices/{id}?tenant_id=<target> → 204,
    soft-deleting a device in the target store. DELETE has no body, so tenant_id
    rides as a query param (plan §4.5.4 patch note)."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)
    sa_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P3-SA-SEED",
    )
    hq_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P3-HQ-SEED",
    )

    resp = await super_admin_client.delete(
        f"/api/v1/devices/{sa_device.id}?tenant_id={target_tenant_id}",
        headers=AUTH,
    )
    assert resp.status_code == 204, resp.text

    resp = await hq_staff_client.delete(
        f"/api/v1/devices/{hq_device.id}?tenant_id={target_tenant_id}",
        headers=AUTH,
    )
    assert resp.status_code == 204, resp.text

    # Both devices are now soft-deleted → a follow-up GET by the platform
    # writer returns 404 (the panorama excludes soft-deleted rows, mirroring
    # the within-store _get_live_device path). Verified via the client rather
    # than ``db_session.get`` because the test session's identity map caches
    # the pre-delete state.
    for did in (sa_device.id, hq_device.id):
        resp = await super_admin_client.get(
            f"/api/v1/devices/{did}", headers=AUTH
        )
        assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_p4_platform_writer_bind_cross_tenant(
    super_admin_client, hq_staff_client, db_session, test_env
):
    """P4: super_admin + hq_staff POST /devices/{id}/bind with
    ``{customer_id, tenant_id}`` → 200, binding a device in the target store
    to a customer who has a live profile in that target store."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)
    sa_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P4-SA-SEED",
    )
    hq_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P4-HQ-SEED",
    )
    # Customer with a live profile in the TARGET tenant (bind validates this).
    sa_customer, _ = await _seed_customer_with_profile(
        db_session, tenant_id=target_tenant_id, name="P4-SA-客户"
    )
    hq_customer, _ = await _seed_customer_with_profile(
        db_session, tenant_id=target_tenant_id, name="P4-HQ-客户"
    )

    resp = await super_admin_client.post(
        f"/api/v1/devices/{sa_device.id}/bind",
        json={"customer_id": sa_customer.id, "tenant_id": target_tenant_id},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["already_bound"] is False

    resp = await hq_staff_client.post(
        f"/api/v1/devices/{hq_device.id}/bind",
        json={"customer_id": hq_customer.id, "tenant_id": target_tenant_id},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["already_bound"] is False


@pytest.mark.asyncio
async def test_p5_platform_writer_unbind_cross_tenant(
    super_admin_client, hq_staff_client, db_session, test_env
):
    """P5: super_admin + hq_staff DELETE /devices/{id}/bind?tenant_id=<target>
    → 204, unbinding a device in the target store. unbind is DELETE → query
    param for tenant_id."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)
    # Seed two devices, each pre-bound to a customer in the target tenant.
    sa_customer, _ = await _seed_customer_with_profile(
        db_session, tenant_id=target_tenant_id, name="P5-SA-客户"
    )
    hq_customer, _ = await _seed_customer_with_profile(
        db_session, tenant_id=target_tenant_id, name="P5-HQ-客户"
    )
    sa_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P5-SA-SEED",
        customer_id=sa_customer.id,
    )
    hq_device = await _seed_device(
        db_session,
        tenant_id=target_tenant_id,
        model_id=model.id,
        serial="P5-HQ-SEED",
        customer_id=hq_customer.id,
    )

    resp = await super_admin_client.delete(
        f"/api/v1/devices/{sa_device.id}/bind?tenant_id={target_tenant_id}",
        headers=AUTH,
    )
    assert resp.status_code == 204, resp.text

    resp = await hq_staff_client.delete(
        f"/api/v1/devices/{hq_device.id}/bind?tenant_id={target_tenant_id}",
        headers=AUTH,
    )
    assert resp.status_code == 204, resp.text

    # Both devices now have no customer binding → verified via the client's
    # own GET (the test session's identity map would otherwise serve stale
    # pre-unbind state). The panorama DeviceHqRead still carries customer_id
    # as null.
    for did in (sa_device.id, hq_device.id):
        resp = await super_admin_client.get(
            f"/api/v1/devices/{did}", headers=AUTH
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["customer_id"] is None


@pytest.mark.asyncio
async def test_p6_platform_writer_create_without_tenant_id_400(
    super_admin_client, hq_staff_client, db_session
):
    """P6: platform writers POST /devices/ WITHOUT tenant_id → 400 (D1 必填).
    Both super_admin and hq_staff must name the target store; the bypass in
    ``check`` does NOT excuse them from naming where to write."""
    model = await _seed_model(db_session, name="P6-Model")

    resp = await super_admin_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "P6-SA"},
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text

    resp = await hq_staff_client.post(
        "/api/v1/devices/",
        json={"model_id": model.id, "serial_number": "P6-HQ"},
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_p7_owner_create_with_tenant_id_400(app_client, db_session):
    """P7 (owner): store role carrying tenant_id → 400 (D1-2 防伪造). The owner
    is forbidden from forging a target tenant to write cross-store."""
    model = await _seed_model(db_session, name="P7-Owner-Model")
    resp = await app_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P7-OWNER",
            "tenant_id": "tnt-forged-by-owner",
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_p7_admin_create_with_tenant_id_400(tenant_admin_client, db_session):
    """P7 (admin): same anti-forgery guard for the tenant admin role."""
    model = await _seed_model(db_session, name="P7-Admin-Model")
    resp = await tenant_admin_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P7-ADMIN",
            "tenant_id": "tnt-forged-by-admin",
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_p7_member_create_with_tenant_id_403(member_client, db_session):
    """P7 (member): member has no ``devices:create`` in casbin, so the router-
    level ``require_permission`` dependency refuses the request (403) BEFORE
    the service body runs — regardless of whether member carries a forged
    ``tenant_id``. This is the correct behaviour: a forged tenant_id MUST NOT
    unlock create for a role that lacks it (plan D1-2 anti-forgery is about
    owner/admin who DO have create; member is already refused upstream).
    Documented here as the negative complement to P7-owner/admin → 400."""
    model = await _seed_model(db_session, name="P7-Member-Model")
    resp = await member_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P7-MEMBER",
            "tenant_id": "tnt-forged-by-member",
        },
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p7_customer_create_with_tenant_id_403(
    customer_client_factory, db_session
):
    """P7 (customer): customer principal has no ``devices:create`` at all →
    the router-level ``require_permission`` dependency refuses (403) before
    the service body. Same rationale as member: a forged tenant_id does not
    unlock writes for a role that lacks them."""
    model = await _seed_model(db_session, name="P7-Customer-Model")
    client = await customer_client_factory(customer_id="cust-p7")
    resp = await client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P7-CUSTOMER",
            "tenant_id": "tnt-forged-by-customer",
        },
        headers=AUTH,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_p8_platform_writer_create_with_target_customer_201(
    super_admin_client, db_session
):
    """P8 (D2-ii): platform writer POST /devices/ with tenant_id + customer_id
    pointing at a customer who has a live profile in the TARGET store → 201.
    The ``_assert_customer_in_tenant`` guard uses effective_tenant_id, so a
    target-store customer passes; a customer from another store would fail
    (P9 covers the negative)."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)
    customer, _ = await _seed_customer_with_profile(
        db_session, tenant_id=target_tenant_id, name="P8-目标店客户"
    )

    resp = await super_admin_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P8-WITH-CUST",
            "tenant_id": target_tenant_id,
            "customer_id": customer.id,
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant_id"] == target_tenant_id
    assert body["customer_id"] == customer.id


@pytest.mark.asyncio
async def test_p9_platform_writer_create_with_nonexistent_customer_400(
    super_admin_client, db_session
):
    """P9: platform writer POST /devices/ with tenant_id + customer_id that
    has NO live profile in the target store → 400. The guard correctly refuses
    a cross-store or nonexistent customer (D2-ii negative)."""
    target_tenant_id, model = await _seed_target_tenant_with_model(db_session)

    resp = await super_admin_client.post(
        "/api/v1/devices/",
        json={
            "model_id": model.id,
            "serial_number": "P9-BAD-CUST",
            "tenant_id": target_tenant_id,
            "customer_id": "cust-does-not-exist",
        },
        headers=AUTH,
    )
    assert resp.status_code == 400, resp.text
