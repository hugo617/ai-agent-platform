"""Booking-config API tests — slice 01 (booking_configs table + two-level API).

Chapter layout (matches plan-booking-schedule-grid.md slice 01 acceptance
criteria):

- P. platform scope CRUD — super_admin GET/PUT ``/bookings/config/platform``;
  non-super-admin → 403; platform seed row surfaces (when present).
- T. tenant scope CRUD — owner/admin PUT ``/bookings/config/tenant/{id}`` for
  their own tenant; super_admin writes any tenant; cross-tenant store role →
  403; member/customer (no ``settings:update``) → 403.
- E. effective three-level fallback — three DB states each exercised once:
  - E1 tenant override exists → ``source=tenant``
  - E2 no tenant row, platform row exists → ``source=platform``
  - E3 neither exists → ``source=default`` (hardcoded 45/08:00/22:00)
- X. effective cross-tenant guards — platform writer without ``tenant_id`` →
  403; store role carrying ``tenant_id`` → 403 (anti-forgery).
- V. duration is free-form Integer — 1 / 240 / any minute value accepted;
  non-positive (0, -5) → 422; malformed window → 422.
- A. audit — upsert calls ``LoggingService.record`` with ``module=booking_config``
  and non-empty ``old_values``/``new_values`` (mocker.spy).

Tests use ``create_all`` (not the migration), so the seeded platform default
row is absent unless a test inserts it directly — this is what makes the E3
"neither exists" state easy to reproduce.
"""

import uuid

import pytest

AUTH = {"Authorization": "Bearer fake"}

_VALID = {
    "default_duration_minutes": 45,
    "window_start": "08:00",
    "window_end": "22:00",
}


# --------------------------------------------------------------------- helpers


async def _seed_config_row(
    db_session,
    *,
    tenant_id: str | None,
    duration: int = 45,
    window_start: str = "08:00",
    window_end: str = "22:00",
):
    """Insert a BookingConfig row directly (platform default when tenant_id=None)."""
    from app.models.booking_config import BookingConfig

    row = BookingConfig(
        tenant_id=tenant_id,
        default_duration_minutes=duration,
        window_start=window_start,
        window_end=window_end,
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def _seed_other_tenant(db_session):
    """Insert a second tenant (for cross-tenant assertions). Returns its id."""
    from app.models.tenant import Tenant

    other_id = f"tnt-other-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=other_id, name="Other Tenant"))
    await db_session.commit()
    return other_id


# ---------------------------------------------------------- P. platform scope


@pytest.mark.asyncio
async def test_p_super_admin_can_get_platform_when_unset(super_admin_client):
    """super_admin GET /platform returns None when no platform row exists yet."""
    resp = await super_admin_client.get(
        "/api/v1/bookings/config/platform", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() is None


@pytest.mark.asyncio
async def test_p_super_admin_can_upsert_then_get_platform(
    super_admin_client, db_session
):
    """super_admin PUT then GET /platform round-trip; second PUT updates (upsert)."""
    resp = await super_admin_client.put(
        "/api/v1/bookings/config/platform",
        json={**_VALID, "default_duration_minutes": 60, "window_end": "21:00"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] is None
    assert body["default_duration_minutes"] == 60
    assert body["window_end"] == "21:00"
    row_id = body["id"]

    # second PUT updates the same row (upsert, no duplicate)
    resp = await super_admin_client.put(
        "/api/v1/bookings/config/platform",
        json={**_VALID, "default_duration_minutes": 90},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == row_id  # same row, patched
    assert resp.json()["default_duration_minutes"] == 90

    # GET now returns the platform row
    resp = await super_admin_client.get(
        "/api/v1/bookings/config/platform", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["default_duration_minutes"] == 90

    # cleanup so other tests see no platform row
    from sqlalchemy import text

    await db_session.execute(text("DELETE FROM booking_configs"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_p_non_super_admin_get_platform_forbidden(app_client, tenant_admin_client):
    """owner (store role) and admin both lack platform reach → 403 on /platform."""
    resp = await app_client.get("/api/v1/bookings/config/platform", headers=AUTH)
    assert resp.status_code == 403
    resp = await tenant_admin_client.get(
        "/api/v1/bookings/config/platform", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_p_non_super_admin_put_platform_forbidden(app_client):
    """owner PUT /platform → 403 (platform scope is super_admin-only)."""
    resp = await app_client.put(
        "/api/v1/bookings/config/platform", json=_VALID, headers=AUTH
    )
    assert resp.status_code == 403


# ----------------------------------------------------------- T. tenant scope


@pytest.mark.asyncio
async def test_t_owner_can_upsert_then_get_own_tenant(app_client, db_session, test_env):
    """owner PUT then GET /tenant/{own} round-trip; row carries the caller tenant."""
    tid = test_env.tenant_id
    resp = await app_client.put(
        f"/api/v1/bookings/config/tenant/{tid}",
        json={**_VALID, "default_duration_minutes": 60, "window_start": "09:00"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == tid
    assert body["default_duration_minutes"] == 60
    assert body["window_start"] == "09:00"

    resp = await app_client.get(
        f"/api/v1/bookings/config/tenant/{tid}", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["default_duration_minutes"] == 60


@pytest.mark.asyncio
async def test_t_admin_can_upsert_own_tenant(tenant_admin_client, test_env):
    """admin holds settings:update → PUT /tenant/{own} → 200."""
    tid = test_env.tenant_id
    resp = await tenant_admin_client.put(
        f"/api/v1/bookings/config/tenant/{tid}",
        json=_VALID,
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_t_member_forbidden_no_settings_update(member_client, test_env):
    """member lacks settings:update → PUT /tenant/{own} → 403."""
    tid = test_env.tenant_id
    resp = await member_client.put(
        f"/api/v1/bookings/config/tenant/{tid}",
        json=_VALID,
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_t_cross_tenant_store_role_forbidden(app_client, db_session, test_env):
    """owner of tenant A PUT /tenant/{B} → 403 (cross-tenant forgery)."""
    other_id = await _seed_other_tenant(db_session)
    resp = await app_client.put(
        f"/api/v1/bookings/config/tenant/{other_id}",
        json=_VALID,
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_t_super_admin_can_upsert_any_tenant(super_admin_client, db_session, test_env):
    """super_admin PUT /tenant/{any} → 200 (platform writer reaches any store)."""
    other_id = await _seed_other_tenant(db_session)
    resp = await super_admin_client.put(
        f"/api/v1/bookings/config/tenant/{other_id}",
        json={**_VALID, "default_duration_minutes": 30},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant_id"] == other_id


# ---------------------------------------------------- E. effective three-state


@pytest.mark.asyncio
async def test_e1_tenant_override_wins(app_client, db_session, test_env):
    """Tenant row present → source=tenant, tenant's values used."""
    tid = test_env.tenant_id
    await _seed_config_row(
        db_session, tenant_id=tid, duration=60, window_start="09:00", window_end="21:00"
    )
    await _seed_config_row(db_session, tenant_id=None)  # platform row should lose

    resp = await app_client.get(
        "/api/v1/bookings/config/effective", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "tenant"
    assert body["default_duration_minutes"] == 60
    assert body["window_start"] == "09:00"


@pytest.mark.asyncio
async def test_e2_platform_default_when_no_tenant_row(app_client, db_session, test_env):
    """No tenant row, platform row present → source=platform."""
    await _seed_config_row(
        db_session, tenant_id=None, duration=50, window_start="07:00", window_end="20:00"
    )

    resp = await app_client.get(
        "/api/v1/bookings/config/effective", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "platform"
    assert body["default_duration_minutes"] == 50
    assert body["window_start"] == "07:00"


@pytest.mark.asyncio
async def test_e3_hardcoded_default_when_neither_exists(app_client, test_env):
    """Neither tenant nor platform row → source=default, hardcoded 45/08:00/22:00."""
    resp = await app_client.get(
        "/api/v1/bookings/config/effective", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "default"
    assert body["default_duration_minutes"] == 45
    assert body["window_start"] == "08:00"
    assert body["window_end"] == "22:00"


# ------------------------------------------------- X. effective cross-tenant


@pytest.mark.asyncio
async def test_x_super_admin_effective_without_tenant_id_forbidden(super_admin_client):
    """Platform writer must name the target store → missing tenant_id → 403."""
    resp = await super_admin_client.get(
        "/api/v1/bookings/config/effective", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_x_store_role_effective_with_tenant_id_forbidden(app_client, test_env):
    """Store role carrying tenant_id is a forgery attempt → 403."""
    resp = await app_client.get(
        f"/api/v1/bookings/config/effective?tenant_id={test_env.tenant_id}",
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_x_super_admin_effective_with_target_works(
    super_admin_client, db_session, test_env
):
    """super_admin + target tenant_id → 200, resolves that tenant's effective."""
    resp = await super_admin_client.get(
        f"/api/v1/bookings/config/effective?tenant_id={test_env.tenant_id}",
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "default"


# ----------------------------------------------------------- V. validation


@pytest.mark.asyncio
async def test_v_duration_accepts_any_positive_integer(super_admin_client):
    """D3: duration is free-form Integer — 1 and 240 both accepted."""
    for minutes in (1, 15, 240):
        resp = await super_admin_client.put(
            "/api/v1/bookings/config/platform",
            json={**_VALID, "default_duration_minutes": minutes},
            headers=AUTH,
        )
        assert resp.status_code == 200, (minutes, resp.text)


@pytest.mark.asyncio
async def test_v_non_positive_duration_rejected(super_admin_client):
    """duration <= 0 → 422 (only positive integers allowed)."""
    for minutes in (0, -5):
        resp = await super_admin_client.put(
            "/api/v1/bookings/config/platform",
            json={**_VALID, "default_duration_minutes": minutes},
            headers=AUTH,
        )
        assert resp.status_code == 422, minutes


@pytest.mark.asyncio
async def test_v_malformed_window_rejected(super_admin_client):
    """window not HH:MM → 422."""
    resp = await super_admin_client.put(
        "/api/v1/bookings/config/platform",
        json={**_VALID, "window_start": "25:00"},  # hour out of range
        headers=AUTH,
    )
    assert resp.status_code == 422
    resp = await super_admin_client.put(
        "/api/v1/bookings/config/platform",
        json={**_VALID, "window_end": "8am"},  # not HH:MM
        headers=AUTH,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------- A. audit


@pytest.mark.asyncio
async def test_a_upsert_writes_audit_log(app_client, db_session, test_env):
    """PUT /tenant/{own} calls LoggingService.record with module=booking_config
    and non-empty old/new values (P2 测法: patch.object spy on the class method).

    Uses ``unittest.mock.patch.object`` (the project convention — no pytest-mock
    dependency) with a real method passthrough so the audit row still writes
    while we observe the call kwargs.
    """
    from unittest.mock import patch

    from app.services.logging_service import LoggingService

    tid = test_env.tenant_id
    with patch.object(LoggingService, "record", autospec=True) as spy:
        resp = await app_client.put(
            f"/api/v1/bookings/config/tenant/{tid}",
            json={**_VALID, "default_duration_minutes": 60},
            headers=AUTH,
        )
        assert resp.status_code == 200, resp.text

        spy.assert_called_once()
        kwargs = spy.call_args.kwargs
        assert kwargs["module"] == "booking_config"
        assert kwargs["action"] == "booking_config.create"  # first write = create
        assert kwargs["old_values"] is None  # nothing existed before
        assert kwargs["new_values"]["default_duration_minutes"] == 60
        assert kwargs["tenant_id"] == tid

        # second PUT on the same row records an update with old_values populated
        resp = await app_client.put(
            f"/api/v1/bookings/config/tenant/{tid}",
            json={**_VALID, "default_duration_minutes": 90},
            headers=AUTH,
        )
        assert resp.status_code == 200, resp.text
        assert spy.call_count == 2
        kwargs = spy.call_args.kwargs
        assert kwargs["action"] == "booking_config.update"
        assert kwargs["old_values"]["default_duration_minutes"] == 60
        assert kwargs["new_values"]["default_duration_minutes"] == 90
