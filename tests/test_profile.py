"""Self-service profile + password tests (PUT /auth/me, PUT /auth/me/password).

The profile-edit tests use the mocked-bearer ``app_client`` / ``member_client``
(identity comes from the seeded row, which is what matters). The password-change
tests use ``app_client_real_auth`` so we can prove the new password logs in
end-to-end — the mocked bearer resolves to the owner, who has no local password,
so a real local-login token is required to exercise the bcrypt verify branch.
"""

import uuid

import pytest

from app.core.password import hash_password
from app.models.tenant import User, UserTenant

AUTH = {"Authorization": "Bearer fake"}


async def _seed_password_user(
    db_session,
    tenant_id: str,
    *,
    username: str = "profileuser",
    password: str = "Pass1234!",
    role: str = "member",
) -> str:
    """Create a user WITH a bcrypt password + tenant membership directly in the DB.

    Mirrors the seeding in test_auth_local._seed_user_via_db (duplicated rather
    than cross-imported — test helpers are fragile across modules). Also mirrors
    the role into casbin so /me reports it.
    """
    from app.core import casbin_enforcer as casbin_mod

    uid = uuid.uuid4().hex
    db_session.add(
        User(
            id=uid,
            username=username,
            email=f"{username}@example.com",
            password=hash_password(password),
            status="active",
        )
    )
    db_session.add(UserTenant(user_id=uid, tenant_id=tenant_id, role=role))
    await db_session.commit()

    e = casbin_mod.get_enforcer()
    e.add_role_for_user_in_domain(uid, role, tenant_id)
    for obj, act in [
        ("agents", "read"),
        ("conversations", "read"),
        ("conversations", "create"),
        ("conversations", "chat"),
    ]:
        if not e.has_policy(role, tenant_id, obj, act):
            e.add_policy(role, tenant_id, obj, act)
    return uid


# --------------------------------------------------------------- PUT /auth/me


@pytest.mark.asyncio
async def test_update_me_changes_profile(app_client, tenant_owner, db_session):
    resp = await app_client.put(
        "/api/v1/auth/me",
        json={
            "display_name": "我的昵称",
            "real_name": "张三",
            "phone": "13800000000",
        },
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Identity is still the owner (token user_id is authoritative).
    assert body["user_id"] == tenant_owner["user_id"]
    assert body["tenant_id"] == tenant_owner["tenant_id"]

    # Persisted: read back directly from the shared in-memory DB.
    user = await db_session.get(User, tenant_owner["user_id"])
    assert user is not None
    assert user.display_name == "我的昵称"
    assert user.real_name == "张三"
    assert user.phone == "13800000000"


@pytest.mark.asyncio
async def test_update_me_cannot_change_platform_role_or_status(
    app_client, tenant_owner, db_session
):
    """platform_role/status are not on the ProfileUpdate schema; even if the
    client smuggles them in the body, pydantic ignores them (extra="ignore")."""
    resp = await app_client.put(
        "/api/v1/auth/me",
        json={
            "platform_role": "super_admin",
            "status": "locked",
            "display_name": "x",
        },
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text

    # No privilege escalation: platform_role unchanged, account still active.
    user = await db_session.get(User, tenant_owner["user_id"])
    assert user is not None
    assert user.platform_role is None
    assert user.status == "active"
    # Still able to reach /me (account not locked).
    me = (await app_client.get("/api/v1/auth/me", headers=AUTH)).json()
    assert me["user_id"] == tenant_owner["user_id"]


@pytest.mark.asyncio
async def test_update_me_requires_auth(app_client):
    resp = await app_client.put(
        "/api/v1/auth/me", json={"display_name": "x"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_me_token_user_id_is_authoritative(
    member_client, tenant_owner, db_session
):
    """A member editing their own profile only affects themselves — the token's
    user_id is the only target. There is no user_id in the body to honor, so
    cross-user editing is structurally impossible."""
    member_id = (
        await member_client.get("/api/v1/auth/me", headers=AUTH)
    ).json()["user_id"]
    assert member_id != tenant_owner["user_id"]

    resp = await member_client.put(
        "/api/v1/auth/me", json={"display_name": "成员昵称"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == member_id

    # Landed on the member, never the owner.
    member = await db_session.get(User, member_id)
    owner = await db_session.get(User, tenant_owner["user_id"])
    assert member is not None and owner is not None
    assert member.display_name == "成员昵称"
    assert owner.display_name is None


# --------------------------------------------------------- PUT /auth/me/password


@pytest.mark.asyncio
async def test_change_password_wrong_old_returns_400(
    app_client_real_auth, db_session, tenant_owner
):
    """End-to-end wrong-old-password: seed a password user, present a real token,
    submit a wrong old password → 400. Proves the bcrypt verify branch."""
    await _seed_password_user(db_session, tenant_owner["tenant_id"])
    tok = (
        await app_client_real_auth.post(
            "/api/v1/auth/login",
            json={"username": "profileuser", "password": "Pass1234!"},
        )
    ).json()["access_token"]

    resp = await app_client_real_auth.put(
        "/api/v1/auth/me/password",
        json={"old_password": "wrong-old", "new_password": "NewPass123!"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 400, resp.text
    assert "旧密码" in resp.json()["detail"]

    # Old password still works (unchanged).
    again = await app_client_real_auth.post(
        "/api/v1/auth/login",
        json={"username": "profileuser", "password": "Pass1234!"},
    )
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_change_password_success_real_auth(
    app_client_real_auth, db_session, tenant_owner
):
    """End-to-end happy path: correct old password → new password works for
    login, old password no longer does."""
    await _seed_password_user(db_session, tenant_owner["tenant_id"])
    tok = (
        await app_client_real_auth.post(
            "/api/v1/auth/login",
            json={"username": "profileuser", "password": "Pass1234!"},
        )
    ).json()["access_token"]

    resp = await app_client_real_auth.put(
        "/api/v1/auth/me/password",
        json={"old_password": "Pass1234!", "new_password": "BrandNew123!"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 204, resp.text

    # New password logs in.
    new_login = await app_client_real_auth.post(
        "/api/v1/auth/login",
        json={"username": "profileuser", "password": "BrandNew123!"},
    )
    assert new_login.status_code == 200, new_login.text

    # Old password is rejected.
    old_login = await app_client_real_auth.post(
        "/api/v1/auth/login",
        json={"username": "profileuser", "password": "Pass1234!"},
    )
    assert old_login.status_code == 401


@pytest.mark.asyncio
async def test_change_password_too_short_rejected(app_client):
    """new_password shorter than the 8-char minimum → 422 (pydantic)."""
    resp = await app_client.put(
        "/api/v1/auth/me/password",
        json={"old_password": "Pass1234!", "new_password": "short"},
        headers=AUTH,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_requires_auth(app_client):
    resp = await app_client.put(
        "/api/v1/auth/me/password",
        json={"old_password": "a", "new_password": "bbbbbbbb"},
    )
    assert resp.status_code == 401
