"""Device API tests — slice 01 (within-store CRUD + integrity guards) + slice 02
permission backfill (K chapter) + slice 03 HQ panorama (E chapter) + slice 04
bind/unbind (F chapter).

Chapter layout (matches plan-devices-crud-ui.md §8 + §10 + slice 03/04):
- A. owner/admin CRUD — create + list + get + update + delete, full-field assertions
- B. cross-tenant isolation — devices in tnt-iso-2 invisible; GET/PUT/DELETE → 404
- C. (tenant_id, serial_number) uniqueness — duplicate 400, reusable after soft delete
- D. permission matrix — member read-only (write → 403); unauth → 401
- E. HQ panorama (slice 03) — super_admin + hq_staff cross-tenant read with the
  ``DeviceHqRead`` panorama fields (tenant_name / model_name / customer_name);
  hq_staff writes (create/update/delete) → 403.
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
- K. backfill (slice 02): bring pre-existing tenants up to the devices perm set.
  - K1 fixture: a tenant with NO devices policies (DB + casbin)
  - K2 run backfill_devices_perms_for_existing_tenants
  - K3 owner gets devices:create/read/update/delete + menu:devices
  - K4 member gets devices:read + menu:devices but NOT devices:create
  - K5 idempotent: re-run backfill, no error, no duplicate grants
  - K6 other existing perms (customers:read) untouched

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
async def test_hq_staff_writes_are_403(hq_staff_client, db_session, test_env):
    """hq_staff is read-only: create/update/delete all 403.

    The hq_staff fixture binds the user to the ``member`` tenant role (no
    devices:create/update/delete in casbin), and ``permission_service.check``
    only short-circuits hq_staff for ``act == "read"`` — writes fall through
    to casbin and are denied. This is the WIP=1 boundary: the HQ viewer can
    SEE everything but touch nothing."""
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
    assert resp.status_code == 403
    resp = await hq_staff_client.put(
        f"/api/v1/devices/{device.id}",
        json={"status": "retired"},
        headers=AUTH,
    )
    assert resp.status_code == 403
    resp = await hq_staff_client.delete(
        f"/api/v1/devices/{device.id}", headers=AUTH
    )
    assert resp.status_code == 403


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


# ----------------------------------------- K. backfill (slice 02)
#
# K chapter verifies ``backfill_devices_perms_for_existing_tenants``: the
# function that brings pre-existing tenants (created before slice 02 shipped)
# up to the devices permission set. Each test stands alone (no client fixture —
# these are pure DB + permission_service assertions) so they don't interact
# with the shared owner/seeded-casbin state in the A-H chapters.
#
# The test_env's seeded enforcer already carries devices:* policies for
# test_env.tenant_id (simulating a backfilled tenant — see conftest). For K we
# create a FRESH tenant with zero devices grants and run the backfill against it.


async def _seed_backfill_target_tenant(db_session, test_env=None):
    """K1: build a tenant that pre-dates devices-crud-ui.

    The tenant has the three system roles (owner/admin/member) and a couple of
    unrelated permission grants (customers:read, menu:agents) to prove the K6
    contract — backfill must NOT touch other perms. Critically, it has ZERO
    devices-related rows (no Permission rows, no RolePermission grants, no
    casbin policies) when this helper returns.

    The non-devices grants are mirrored in BOTH the DB (SCD2 grants) AND
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
    # a menu perm (menu:agents) on owner. These prove backfill doesn't touch
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
    menu_perm_id = uuid.uuid4().hex
    db_session.add(
        Permission(
            id=menu_perm_id,
            tenant_id=tenant_id,
            name="菜单-智能体",
            code="menu:agents",
            type="menu",
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
    db_session.add(
        RolePermission(
            role_id=role_ids["owner"],
            permission_id=menu_perm_id,
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
        test_env.enforcer.add_policy("owner", tenant_id, "menu", "agents")

    return tenant_id, role_ids


@pytest.mark.asyncio
async def test_k_backfill_grants_devices_perms_correctly(db_session, test_env):
    """K2 + K3 + K4: backfill grants owner the full devices set, member only
    read; both pick up menu:devices. Verified through the production code path
    (permission_service.check) so a casbin-sync regression surfaces."""
    from unittest.mock import patch

    from app.core import casbin_enforcer as casbin_mod
    from app.services.permission_service import (
        backfill_devices_perms_for_existing_tenants,
        permission_service,
    )

    tenant_id, _ = await _seed_backfill_target_tenant(db_session, test_env)
    # The enforcer patch mirrors what app_client sets up: without it, the
    # production ``get_enforcer`` would route casbin calls to the unrelated
    # global SQLite DB (MissingGreenlet). Patch for the whole test.
    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        # K2: run the backfill. ``db`` must be the same session the assertions
        # use so the writes are visible (test fixture shares one connection).
        stats = await backfill_devices_perms_for_existing_tenants(db_session)

        # The backfill should have added: owner gets 4 api + 1 menu = 5; admin
        # 3 + 1 = 4; member 1 + 1 = 2. The seeded customers:read (3) and
        # menu:agents (1) are NOT counted (pre-existing → grant was a no-op).
        assert stats[tenant_id] == 5 + 4 + 2, stats

        # K3: owner gets all four devices api perms + menu:devices. The role
        # name itself is a casbin subject (see conftest _make_casbin), so we
        # check the role directly — no user binding needed.
        for act in ("create", "read", "update", "delete"):
            ok = await permission_service.check(
                "owner", tenant_id, "devices", act
            )
            assert ok, f"owner should have devices:{act} after backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", "devices")
        assert ok, "owner should have menu:devices after backfill"

        # K4: member gets devices:read + menu:devices only — NOT create.
        ok = await permission_service.check("member", tenant_id, "devices", "read")
        assert ok, "member should have devices:read after backfill"
        denied = await permission_service.check(
            "member", tenant_id, "devices", "create"
        )
        assert not denied, "member must NOT get devices:create (anti-overgrant)"


@pytest.mark.asyncio
async def test_k_backfill_idempotent(db_session, test_env):
    """K5: re-running backfill on an already-backfilled tenant is a no-op —
    same grants, no error, no duplicate rows."""
    from unittest.mock import patch

    from sqlalchemy import select

    from app.core import casbin_enforcer as casbin_mod
    from app.models.rbac import RolePermission
    from app.services.permission_service import (
        backfill_devices_perms_for_existing_tenants,
    )

    tenant_id, _ = await _seed_backfill_target_tenant(db_session, test_env)

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        await backfill_devices_perms_for_existing_tenants(db_session)
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
        second = await backfill_devices_perms_for_existing_tenants(db_session)
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
    """K6: backfill touches ONLY devices/menu:devices. The pre-existing
    customers:read and menu:agents grants survive unchanged — both before/after
    the backfill."""
    from unittest.mock import patch

    from app.core import casbin_enforcer as casbin_mod
    from app.services.permission_service import (
        backfill_devices_perms_for_existing_tenants,
        permission_service,
    )

    tenant_id, _ = await _seed_backfill_target_tenant(db_session, test_env)

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        # Pre-backfill: customers:read works for owner/admin/member; menu:agents
        # works for owner. (No devices perms yet.)
        for role in ("owner", "admin", "member"):
            ok = await permission_service.check(
                role, tenant_id, "customers", "read"
            )
            assert ok, f"{role} had customers:read before backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", "agents")
        assert ok, "owner had menu:agents before backfill"

        await backfill_devices_perms_for_existing_tenants(db_session)

        # Post-backfill: the original perms still work AND devices perms work.
        for role in ("owner", "admin", "member"):
            ok = await permission_service.check(
                role, tenant_id, "customers", "read"
            )
            assert ok, f"{role} should still have customers:read after backfill"
        ok = await permission_service.check("owner", tenant_id, "menu", "agents")
        assert ok, "owner should still have menu:agents after backfill"
        # And a devices perm does work (backfill actually did something).
        ok = await permission_service.check("owner", tenant_id, "devices", "read")
        assert ok, "owner should have devices:read after backfill"
