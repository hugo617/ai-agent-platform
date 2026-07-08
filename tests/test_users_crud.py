"""User CRUD API tests — paginated list, create, update, delete, status, reset."""

import pytest

AUTH = {"Authorization": "Bearer fake"}


def _create_payload(suffix: str) -> dict:
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "Secret123!",
        "real_name": f"Real {suffix}",
        "phone": "13800000000",
        "role": "member",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_create_and_list_user(app_client):
    resp = await app_client.post(
        "/api/v1/users/", json=_create_payload("one"), headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["username"] == "user_one"
    assert created["email"] == "user_one@example.com"
    assert "password" not in created  # never serialized out
    assert created["role"]["code"] == "member"

    resp = await app_client.get("/api/v1/users/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(u["username"] == "user_one" for u in body["items"])
    assert body["page"] == 1
    assert body["total_pages"] >= 1


@pytest.mark.asyncio
async def test_search_and_filter(app_client):
    await app_client.post("/api/v1/users/", json=_create_payload("alpha"), headers=AUTH)
    await app_client.post("/api/v1/users/", json=_create_payload("beta"), headers=AUTH)

    # search by username fragment
    resp = await app_client.get("/api/v1/users/?search=alpha", headers=AUTH)
    assert resp.status_code == 200
    names = [u["username"] for u in resp.json()["items"]]
    assert "user_alpha" in names
    assert "user_beta" not in names

    # status filter
    resp = await app_client.get("/api/v1/users/?status=active", headers=AUTH)
    assert resp.status_code == 200
    assert all(u["status"] == "active" for u in resp.json()["items"])


@pytest.mark.asyncio
async def test_sorting(app_client):
    await app_client.post("/api/v1/users/", json=_create_payload("aaa"), headers=AUTH)
    await app_client.post("/api/v1/users/", json=_create_payload("zzz"), headers=AUTH)

    resp = await app_client.get(
        "/api/v1/users/?sort_by=username&sort_order=asc", headers=AUTH
    )
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()["items"] if u["username"]]
    assert usernames == sorted(usernames)


@pytest.mark.asyncio
async def test_update_user(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("upd"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.put(
        f"/api/v1/users/{uid}",
        json={"real_name": "Updated Name", "role": "admin"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["real_name"] == "Updated Name"
    assert body["role"]["code"] == "admin"


@pytest.mark.asyncio
async def test_change_status(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("lock"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.patch(
        f"/api/v1/users/{uid}/status", json={"status": "locked"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "locked"


@pytest.mark.asyncio
async def test_reset_password(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("pw"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.post(
        f"/api/v1/users/{uid}/reset-password",
        json={"new_password": "BrandNew456!"},
        headers=AUTH,
    )
    assert resp.status_code == 204, resp.text

    # the new password now works against /auth/login (login by username)
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={
            "username": "user_pw",
            "password": "BrandNew456!",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_delete_user_soft_deletes(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("del"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.delete(f"/api/v1/users/{uid}", headers=AUTH)
    assert resp.status_code == 204

    # not in list anymore
    resp = await app_client.get("/api/v1/users/", headers=AUTH)
    assert uid not in [u["id"] for u in resp.json()["items"]]

    # 404 on direct get
    resp = await app_client.get(f"/api/v1/users/{uid}", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_self(app_client, tenant_owner):
    resp = await app_client.delete(
        f"/api/v1/users/{tenant_owner['user_id']}", headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_username_rejected(app_client):
    resp = await app_client.post("/api/v1/users/", json=_create_payload("dup"), headers=AUTH)
    assert resp.status_code == 201
    resp = await app_client.post("/api/v1/users/", json=_create_payload("dup"), headers=AUTH)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_db_enforces_username_uniqueness(db_session):
    """The partial unique index must reject a duplicate at the DB layer too.

    The application's check-then-insert is racy under concurrency; the index is
    the real guarantee. Drive a raw insert to confirm IntegrityError fires
    (without relying on UserService's pre-check).
    """
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.models.tenant import User

    async def _add(name: str):
        db_session.add(
            User(id=uuid.uuid4().hex, username=name, email=f"{name}@x.com", status="active")
        )
        await db_session.flush()

    await _add("uniq_user")
    with pytest.raises(IntegrityError):
        await _add("uniq_user")  # same username, different id -> blocked by index
    await db_session.rollback()


@pytest.mark.asyncio
async def test_soft_deleted_username_can_be_reused(app_client):
    """The unique index is PARTIAL (is_deleted=false), so once a user is
    soft-deleted their username is free for a new account — matching the
    is_deleted filter every lookup already applies."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("reuse"), headers=AUTH)
    ).json()
    await app_client.delete(f"/api/v1/users/{created['id']}", headers=AUTH)

    # Recreating the same username must now succeed (not 400 duplicate).
    resp = await app_client.post("/api/v1/users/", json=_create_payload("reuse"), headers=AUTH)
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_statistics(app_client):
    await app_client.post("/api/v1/users/", json=_create_payload("stat1"), headers=AUTH)
    await app_client.post("/api/v1/users/", json=_create_payload("stat2"), headers=AUTH)
    resp = await app_client.get("/api/v1/users/statistics", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert body["active"] >= 2
    assert body["new_this_month"] >= 2
