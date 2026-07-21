"""Device API tests — slice 01 (within-store CRUD + integrity guards).

Chapter layout (matches plan-devices-crud-ui.md §8):
- A. owner/admin CRUD — create + list + get + update + delete, full-field assertions
- B. cross-tenant isolation — devices in tnt-iso-2 invisible; GET/PUT/DELETE → 404
- C. (tenant_id, serial_number) uniqueness — duplicate 400, reusable after soft delete
- D. permission matrix — member read-only (write → 403); unauth → 401
- G. status transitions — active↔maintenance↔retired all legal; bad value → 422
- H. model_id integrity (service-layer guard, NOT FK RESTRICT which is a dead-bolt):
  - H1 create with soft-deleted model_id → 400 BizError
  - H2 create with nonexistent model_id → 400 BizError
  - H3 update pointing at soft-deleted model → 400 BizError
  - H4 device referencing a soft-deleted model still GETs fine
  - H5 (behavioural note only, no test — covered by device-models API tests)

Slice 03 (HQ panorama) / slice 04 (bind/unbind) / slice 02 K-chapter (backfill)
land in their own slices.

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
