"""Local auth (username/password login) API tests.

Two fixture modes:
  - ``app_client``          — decode_token mocked; for login-success/failure
                              assertions where we don't need real JWT verification.
  - ``app_client_real_auth`` — decode_token NOT mocked; for the /me and
                              /sessions round-trip that proves a real minted
                              token flows through get_current_user unchanged.
"""

import uuid

import pytest

from app.core.password import hash_password
from app.models.tenant import User, UserTenant

AUTH = {"Authorization": "Bearer fake"}


async def _seed_loginable_user(app_client, username="loginuser", password="Pass1234!"):
    resp = await app_client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "role": "member",
            "status": "active",
        },
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _seed_user_via_db(db_session, tenant_id, username="realmember"):
    """Create a loginable user + tenant membership directly in the DB.

    Also mirrors the user's role into the (file-backed) casbin enforcer — the
    production ``UserService.create`` does this, but we bypass the CRUD endpoint
    here (its bearer is mocked). Without it, ``/me`` would report an empty role.
    """
    from app.core import casbin_enforcer as casbin_mod

    uid = uuid.uuid4().hex
    db_session.add(
        User(
            id=uid,
            username=username,
            email=f"{username}@example.com",
            password=hash_password("Pass1234!"),
            status="active",
        )
    )
    db_session.add(UserTenant(user_id=uid, tenant_id=tenant_id, role="member"))
    await db_session.commit()

    e = casbin_mod.get_enforcer()
    e.add_role_for_user_in_domain(uid, "member", tenant_id)
    # Seed the member policies for this tenant if missing.
    for obj, act in [
        ("agents", "read"), ("conversations", "read"),
        ("conversations", "create"), ("conversations", "chat"),
    ]:
        if not e.has_policy("member", tenant_id, obj, act):
            e.add_policy("member", tenant_id, obj, act)
    return uid


@pytest.mark.asyncio
async def test_login_success_returns_token(app_client):
    await _seed_loginable_user(app_client)
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={"username": "loginuser", "password": "Pass1234!"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_token_works_against_me(app_client_real_auth, db_session, tenant_owner):
    """End-to-end: real token → /me returns the right identity."""
    uid = await _seed_user_via_db(db_session, tenant_owner["tenant_id"])
    resp = await app_client_real_auth.post(
        "/api/v1/auth/login",
        json={"username": "realmember", "password": "Pass1234!"},
    )
    assert resp.status_code == 200, resp.text
    tok = resp.json()["access_token"]

    resp = await app_client_real_auth.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == uid
    assert body["tenant_id"] == tenant_owner["tenant_id"]
    assert "member" in body["roles"]


@pytest.mark.asyncio
async def test_login_wrong_password(app_client):
    await _seed_loginable_user(app_client)
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={"username": "loginuser", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_login_unknown_user(app_client):
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "whatever"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_email_identifier(app_client):
    await _seed_loginable_user(app_client)
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@example.com", "password": "Pass1234!"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_locked_account(app_client):
    uid = await _seed_loginable_user(app_client)
    await app_client.patch(
        f"/api/v1/users/{uid}/status", json={"status": "locked"}, headers=AUTH
    )
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={"username": "loginuser", "password": "Pass1234!"},
    )
    assert resp.status_code == 401
    assert "locked" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_sessions_listed_after_login(app_client_real_auth, db_session, tenant_owner):
    """End-to-end: after login, /sessions lists the new session."""
    await _seed_user_via_db(db_session, tenant_owner["tenant_id"])
    tok = (
        await app_client_real_auth.post(
            "/api/v1/auth/login",
            json={"username": "realmember", "password": "Pass1234!"},
        )
    ).json()["access_token"]
    resp = await app_client_real_auth.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_logout_deactivates_session(
    app_client_real_auth, db_session, tenant_owner
):
    """End-to-end: logout marks the session inactive AND revokes the token.

    The calling token now fails subsequent requests (``get_current_user``
    rejects the deactivated session) — session revocation is enforced, not
    just recorded. We use the owner token (no jti, no session row) to read the
    sessions table and confirm the row was flipped to inactive.
    """
    uid = await _seed_user_via_db(db_session, tenant_owner["tenant_id"])
    tok = (
        await app_client_real_auth.post(
            "/api/v1/auth/login",
            json={"username": "realmember", "password": "Pass1234!"},
        )
    ).json()["access_token"]
    jti = _decode_jti(tok)

    resp = await app_client_real_auth.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 204

    # The logged-out token is now rejected (session deactivated → 401).
    resp = await app_client_real_auth.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 401

    # Confirm the session row itself was flipped to inactive, using the shared
    # test session (same in-memory DB) to inspect the row directly.
    from app.repositories.security import SessionRepository

    row = await SessionRepository(db_session).get_by_session_id(jti)
    assert row is not None
    assert row.is_active is False
    assert row.user_id == uid


def _decode_jti(token: str) -> str:
    import jwt

    return str(jwt.decode(token, options={"verify_signature": False})["jti"])
