"""DeviceModel API tests — platform-level device catalogue management.

Covers: super_admin CRUD + soft delete, write-guard (403 for non-super_admin,
including hq_staff), read-field split (super_admin/hq_staff see unit_cost +
full specs; tenant users see only {id, name, specs.form_factor}), 404s,
duplicate-name (400), name reuse after soft delete, specs whole-replace
semantics, and 401 for unauthenticated requests.

Test-organization note (matches test_groups_api.py convention): each test
function uses ONE client fixture. Mixing super_admin_client with
app_client/member_client in the same function would corrupt the shared
``owner`` user — super_admin_client's setup mutates ``owner.platform_role``
to ``super_admin``, which would then leak into app_client's view. Field-split
tests therefore seed data via ``db_session`` (direct ORM) and assert on the
read endpoint of a single client role.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ---------------------------------------------------------------- helpers


async def _seed_model(db_session, **overrides):
    """Insert a DeviceModel row directly (bypass the API)."""
    from decimal import Decimal

    from app.models.device_model import DeviceModel

    defaults = {
        "name": f"M-{overrides.get('name', 'x')}",
        "unit_cost": Decimal("1234.56"),
        "specs": {"form_factor": "chamber", "voltage": "220V"},
    }
    defaults.update(overrides)
    model = DeviceModel(**defaults)
    db_session.add(model)
    await db_session.commit()
    return model


# ----------------------------------------------------- super_admin CRUD


@pytest.mark.asyncio
async def test_super_admin_create_and_get_model(super_admin_client):
    resp = await super_admin_client.post(
        "/api/v1/device-models/",
        json={
            "name": "Blood Pressure Chamber X100",
            "brand": "Acme",
            "supplier": "Acme Supplier",
            "unit_cost": "9800.00",
            "specs": {"form_factor": "chamber", "voltage": "220V"},
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Blood Pressure Chamber X100"
    assert body["brand"] == "Acme"
    assert body["unit_cost"] == "9800.00"  # Decimal serializes as str
    assert body["specs"] == {"form_factor": "chamber", "voltage": "220V"}
    model_id = body["id"]

    resp = await super_admin_client.get(
        f"/api/v1/device-models/{model_id}", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == model_id
    assert resp.json()["unit_cost"] == "9800.00"


@pytest.mark.asyncio
async def test_super_admin_list_empty_then_populated(super_admin_client):
    resp = await super_admin_client.get("/api/v1/device-models/", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []

    await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "M1", "unit_cost": "100.00"},
        headers=AUTH,
    )
    await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "M2", "unit_cost": "200.00"},
        headers=AUTH,
    )
    resp = await super_admin_client.get("/api/v1/device-models/", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_super_admin_update_model(super_admin_client):
    create = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "Old", "unit_cost": "100.00"},
        headers=AUTH,
    )
    mid = create.json()["id"]
    resp = await super_admin_client.put(
        f"/api/v1/device-models/{mid}",
        json={"name": "New", "brand": "BrandX"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "New"
    assert body["brand"] == "BrandX"
    # Unchanged fields preserved.
    assert body["unit_cost"] == "100.00"


@pytest.mark.asyncio
async def test_super_admin_update_duplicate_name_400(super_admin_client):
    await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "DUP", "unit_cost": "100.00"},
        headers=AUTH,
    )
    create_b = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "B", "unit_cost": "100.00"},
        headers=AUTH,
    )
    bid = create_b.json()["id"]
    resp = await super_admin_client.put(
        f"/api/v1/device-models/{bid}", json={"name": "DUP"}, headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_super_admin_create_duplicate_name_400(super_admin_client):
    await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "UNIQ", "unit_cost": "100.00"},
        headers=AUTH,
    )
    resp = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "UNIQ", "unit_cost": "200.00"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_super_admin_delete_soft_then_name_reusable(super_admin_client):
    create = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "ToDelete", "unit_cost": "100.00"},
        headers=AUTH,
    )
    mid = create.json()["id"]
    resp = await super_admin_client.delete(
        f"/api/v1/device-models/{mid}", headers=AUTH
    )
    assert resp.status_code == 204
    # Deleted model no longer in list.
    resp = await super_admin_client.get(
        "/api/v1/device-models/", headers=AUTH
    )
    assert all(m["id"] != mid for m in resp.json())
    # Direct get → 404.
    resp = await super_admin_client.get(
        f"/api/v1/device-models/{mid}", headers=AUTH
    )
    assert resp.status_code == 404
    # Name can be reused (partial unique index exempts the soft-deleted row).
    resp = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "ToDelete", "unit_cost": "100.00"},
        headers=AUTH,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_super_admin_get_nonexistent_404(super_admin_client):
    resp = await super_admin_client.get(
        "/api/v1/device-models/nope", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_update_nonexistent_404(super_admin_client):
    resp = await super_admin_client.put(
        "/api/v1/device-models/nope",
        json={"name": "X"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_delete_nonexistent_404(super_admin_client):
    resp = await super_admin_client.delete(
        "/api/v1/device-models/nope", headers=AUTH
    )
    assert resp.status_code == 404


# ------------------------------------------------- specs whole-replace (PUT)


@pytest.mark.asyncio
async def test_specs_whole_replace_on_update(super_admin_client):
    """PUT specs = whole-replace (no jsonb_set partial update).

    Create with specs={a:1, b:2}, update with specs={a:9} → final specs is
    exactly {a:9}, b is dropped.
    """
    create = await super_admin_client.post(
        "/api/v1/device-models/",
        json={
            "name": "Spec",
            "unit_cost": "100.00",
            "specs": {"a": 1, "b": 2},
        },
        headers=AUTH,
    )
    mid = create.json()["id"]
    resp = await super_admin_client.put(
        f"/api/v1/device-models/{mid}",
        json={"specs": {"a": 9}},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["specs"] == {"a": 9}


# --------------------------------------------- write guard (non-super_admin)


@pytest.mark.asyncio
async def test_tenant_owner_cannot_write(app_client):
    """Tenant owner (no platform_role) is blocked from all writes."""
    resp = await app_client.post(
        "/api/v1/device-models/",
        json={"name": "X", "unit_cost": "100.00"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_write(member_client):
    resp = await member_client.post(
        "/api/v1/device-models/",
        json={"name": "X", "unit_cost": "100.00"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_hq_staff_cannot_write(hq_staff_client):
    """hq_staff is a cross-tenant viewer (read full fields) but NOT a writer
    — only super_admin can reshape the catalogue."""
    resp = await hq_staff_client.post(
        "/api/v1/device-models/",
        json={"name": "X", "unit_cost": "100.00"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_list_401(test_env):
    """No Authorization header → 401 (get_current_user raises 401, not 403)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/device-models/")
        assert resp.status_code == 401


# --------------------------------------------- read field split / projection
#
# Each role gets its own test function. Data is seeded via db_session
# (direct ORM) so the test never depends on which client wrote it — avoids
# the super_admin_client fixture mutating owner.platform_role and leaking
# that into app_client's view.


@pytest.mark.asyncio
async def test_super_admin_sees_full_fields(super_admin_client, db_session):
    """super_admin GET → full DTO incl. unit_cost + complete specs."""
    await _seed_model(db_session, name="Full")
    resp = await super_admin_client.get(
        "/api/v1/device-models/", headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    assert item["name"] == "Full"
    assert item["unit_cost"] == "1234.56"
    assert item["specs"] == {"form_factor": "chamber", "voltage": "220V"}


@pytest.mark.asyncio
async def test_hq_staff_sees_full_fields(hq_staff_client, db_session):
    """hq_staff (cross-tenant viewer) GET → same full DTO as super_admin."""
    await _seed_model(db_session, name="Full")
    resp = await hq_staff_client.get(
        "/api/v1/device-models/", headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    assert item["unit_cost"] == "1234.56"
    assert item["specs"] == {"form_factor": "chamber", "voltage": "220V"}


@pytest.mark.asyncio
async def test_tenant_owner_sees_minimal_fields(app_client, db_session):
    """Tenant owner (no platform_role) GET → minimal DTO: no unit_cost, no
    brand/supplier, specs only {form_factor}."""
    await _seed_model(
        db_session,
        name="Limited",
        brand="Hidden",
        supplier="HiddenSup",
        specs={"form_factor": "chamber", "voltage": "220V", "weight": 35},
    )
    resp = await app_client.get("/api/v1/device-models/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    # Only the dropdown-essential keys are present.
    assert set(item.keys()) == {"id", "name", "specs"}
    assert item["name"] == "Limited"
    assert item["specs"] == {"form_factor": "chamber"}
    # Procurement-cost / supplier / brand are NOT exposed to store staff.
    assert "unit_cost" not in item
    assert "brand" not in item
    assert "supplier" not in item


@pytest.mark.asyncio
async def test_member_sees_minimal_fields(member_client, db_session):
    """member role GET → same minimal DTO as tenant owner."""
    await _seed_model(
        db_session,
        name="Limited",
        specs={"form_factor": "ring", "extra": "secret"},
    )
    resp = await member_client.get("/api/v1/device-models/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    assert set(item.keys()) == {"id", "name", "specs"}
    assert item["specs"] == {"form_factor": "ring"}
    assert "unit_cost" not in item


@pytest.mark.asyncio
async def test_tenant_owner_get_by_id_minimal_fields(app_client, db_session):
    """Direct GET /{id} for tenant owner also returns minimal DTO."""
    model = await _seed_model(db_session, name="Limited")
    resp = await app_client.get(
        f"/api/v1/device-models/{model.id}", headers=AUTH
    )
    assert resp.status_code == 200
    item = resp.json()
    assert set(item.keys()) == {"id", "name", "specs"}
    assert "unit_cost" not in item


@pytest.mark.asyncio
async def test_tenant_owner_no_form_factor(app_client, db_session):
    """If specs has no form_factor, the tenant-user DTO's specs is {} (the
    dropdown will show it under no group)."""
    await _seed_model(db_session, name="NoFormFactor", specs={"weight": 10})
    resp = await app_client.get("/api/v1/device-models/", headers=AUTH)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["specs"] == {}


@pytest.mark.asyncio
async def test_unit_cost_must_be_nonnegative(super_admin_client):
    """unit_cost non-negativity is enforced in the service layer (BizError
    → 400, not 422), because Pydantic's ge=0 surfaces the raw Decimal in
    the 422 error detail which starlette can't JSON-serialize."""
    resp = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "Neg", "unit_cost": "-1.00"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unit_cost_required_on_create(super_admin_client):
    """unit_cost is NOT NULL in the DB + required in Create schema."""
    resp = await super_admin_client.post(
        "/api/v1/device-models/",
        json={"name": "NoCost"},
        headers=AUTH,
    )
    assert resp.status_code == 422
