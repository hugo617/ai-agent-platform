"""Audit-log API tests — ``GET /logs``.

Covers:
- Store owner with ``logs:read`` sees only their tenant's rows.
- Multi-tenant isolation: store A cannot see store B's logs.
- super_admin / hq_staff cross-tenant viewers see all-platform rows.
- Filters: operator (user_id), action, resource_type, date range.
- Pagination (limit/offset) returns the right slice + total.
- member (no ``logs:read``) → 403.
- Store user passing a foreign ``tenant_id`` cannot escape their own tenant.

Logs are seeded via direct SystemLog inserts (not via LoggingService) because
the audit endpoint is read-only and the LoggingService wrapper just adds an
insert inside a savepoint — direct rows are simpler and deterministic.
"""

from datetime import UTC, datetime, timedelta

import pytest

AUTH = {"Authorization": "Bearer fake"}


async def _seed_log(
    db_session,
    *,
    tenant_id,
    action="create",
    resource_type="users",
    resource_id="r-1",
    user_id=None,
    message="did something",
    created_at=None,
):
    """Insert one SystemLog row directly and commit."""
    from app.models.log import SystemLog

    db_session.add(
        SystemLog(
            level="info",
            action=action,
            module="users",
            message=message,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            tenant_id=tenant_id,
            created_at=created_at or datetime.now(UTC),
        )
    )
    await db_session.commit()


# ----------------------------------------------------- list / scoping


@pytest.mark.asyncio
async def test_list_logs_store_owner_sees_own_tenant(app_client, db_session, test_env):
    """Owner with logs:read sees their tenant's audit rows."""
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="update")

    resp = await app_client.get("/api/v1/logs/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert {item["action"] for item in body["items"]} == {"create", "update"}


@pytest.mark.asyncio
async def test_list_logs_tenant_isolation(app_client, db_session, test_env):
    """A store user cannot see another tenant's logs."""
    other = "tnt-logs-other"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    await _seed_log(db_session, tenant_id=other, action="delete", message="secret")

    resp = await app_client.get("/api/v1/logs/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["tenant_id"] == test_env.tenant_id
    assert body["items"][0]["action"] == "create"


@pytest.mark.asyncio
async def test_list_logs_store_cannot_escape_with_tenant_param(
    app_client, db_session, test_env
):
    """Passing ?tenant_id=<other> as a store user is ignored — still own-scoped."""
    other = "tnt-logs-escape"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    await _seed_log(db_session, tenant_id=other, action="delete", message="no leak")

    resp = await app_client.get(
        "/api/v1/logs/", params={"tenant_id": other}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["tenant_id"] == test_env.tenant_id


@pytest.mark.asyncio
async def test_list_logs_super_admin_cross_tenant(
    super_admin_client, db_session, test_env
):
    """super_admin sees logs across ALL tenants."""
    other = "tnt-logs-sa"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    await _seed_log(db_session, tenant_id=other, action="delete")

    resp = await super_admin_client.get("/api/v1/logs/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_list_logs_super_admin_can_filter_by_tenant(
    super_admin_client, db_session, test_env
):
    """super_admin ?tenant_id narrows to one tenant."""
    other = "tnt-logs-sa-filter"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    await _seed_log(db_session, tenant_id=other, action="delete")

    resp = await super_admin_client.get(
        "/api/v1/logs/", params={"tenant_id": other}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["tenant_id"] == other


@pytest.mark.asyncio
async def test_list_logs_member_forbidden(member_client, db_session, test_env):
    """member has no logs:read → 403."""
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    resp = await member_client.get("/api/v1/logs/", headers=AUTH)
    assert resp.status_code == 403


# ----------------------------------------------------- filters


@pytest.mark.asyncio
async def test_list_logs_filter_by_action(app_client, db_session, test_env):
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="update")
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")

    resp = await app_client.get(
        "/api/v1/logs/", params={"action": "create"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert all(item["action"] == "create" for item in body["items"])


@pytest.mark.asyncio
async def test_list_logs_filter_by_resource_type(app_client, db_session, test_env):
    await _seed_log(
        db_session, tenant_id=test_env.tenant_id, resource_type="users"
    )
    await _seed_log(
        db_session, tenant_id=test_env.tenant_id, resource_type="agents"
    )

    resp = await app_client.get(
        "/api/v1/logs/", params={"resource_type": "users"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["resource_type"] == "users"


@pytest.mark.asyncio
async def test_list_logs_filter_by_user_id(app_client, db_session, test_env):
    await _seed_log(db_session, tenant_id=test_env.tenant_id, user_id="alice")
    await _seed_log(db_session, tenant_id=test_env.tenant_id, user_id="bob")

    resp = await app_client.get(
        "/api/v1/logs/", params={"user_id": "alice"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["user_id"] == "alice"


@pytest.mark.asyncio
async def test_list_logs_filter_by_date_range(app_client, db_session, test_env):
    now = datetime.now(UTC)
    await _seed_log(
        db_session,
        tenant_id=test_env.tenant_id,
        created_at=now - timedelta(days=10),
    )
    recent = now - timedelta(days=1)
    await _seed_log(
        db_session, tenant_id=test_env.tenant_id, created_at=recent
    )

    # Only rows in the last 5 days.
    since = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    resp = await app_client.get(
        "/api/v1/logs/", params={"date_from": since}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_list_logs_bad_date_returns_400(app_client):
    resp = await app_client.get(
        "/api/v1/logs/", params={"date_from": "not-a-date"}, headers=AUTH
    )
    assert resp.status_code == 400


# ----------------------------------------------------- pagination


@pytest.mark.asyncio
async def test_list_logs_pagination(app_client, db_session, test_env):
    for _ in range(5):
        await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create")

    # Page 1 (limit 2): total 5, returns 2 newest.
    resp = await app_client.get(
        "/api/v1/logs/", params={"limit": 2, "offset": 0}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2

    # Page 3 (offset 4): only 1 left.
    resp2 = await app_client.get(
        "/api/v1/logs/", params={"limit": 2, "offset": 4}, headers=AUTH
    )
    body2 = resp2.json()
    assert body2["total"] == 5
    assert len(body2["items"]) == 1


@pytest.mark.asyncio
async def test_list_logs_newest_first(app_client, db_session, test_env):
    base = datetime.now(UTC) - timedelta(hours=3)
    await _seed_log(
        db_session,
        tenant_id=test_env.tenant_id,
        created_at=base,
        message="old",
    )
    await _seed_log(
        db_session,
        tenant_id=test_env.tenant_id,
        created_at=base + timedelta(hours=1),
        message="new",
    )

    resp = await app_client.get("/api/v1/logs/", headers=AUTH)
    body = resp.json()
    assert body["items"][0]["message"] == "new"
    assert body["items"][1]["message"] == "old"


# ----------------------------------------------------- field shape


@pytest.mark.asyncio
async def test_list_logs_exposes_before_after_values(
    app_client, db_session, test_env
):
    """update operations carry old_values/new_values (JSONB) in the response."""
    from app.models.log import SystemLog

    db_session.add(
        SystemLog(
            level="info",
            action="update",
            module="users",
            message="renamed",
            resource_type="users",
            resource_id="u-1",
            tenant_id=test_env.tenant_id,
            old_values={"name": "Alice"},
            new_values={"name": "Alicia"},
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/logs/", headers=AUTH)
    body = resp.json()
    item = body["items"][0]
    assert item["old_values"] == {"name": "Alice"}
    assert item["new_values"] == {"name": "Alicia"}
