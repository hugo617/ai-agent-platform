"""Local auth (username/password login) API tests.

Two fixture modes:
  - ``app_client``          — decode_token mocked; for login-success/failure
                              assertions where we don't need real JWT verification.
  - ``app_client_real_auth`` — decode_token NOT mocked; for the /me and
                              /sessions round-trip that proves a real minted
                              token flows through get_current_user unchanged.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.password import hash_password
from app.models.tenant import User, UserTenant

pytestmark = pytest.mark.smoke

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


# ---------------------------------------------------------------------------
# Login lockout (rate-limit-login-lockout slice 01): 5 consecutive failed
# logins lock the account for 15 minutes (DB-persisted, auto-unlock). The
# temporary lock is independent of the administrator's status="locked"
# permanent lock; OIDC-only accounts are never counted; failures inside an
# open lock window neither count nor renew it.
# ---------------------------------------------------------------------------

LOCKOUT_DETAIL = "account temporarily locked, try again later"


async def _login(app_client, username, password):
    return await app_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


async def _get_user(db_session, user_id) -> User:
    # expire_all: app requests committed via their own sessions on the shared
    # connection, so cached instances here would be stale.
    db_session.expire_all()
    return await db_session.get(User, user_id)


def _as_utc(value: datetime) -> datetime:
    # SQLite reads DateTime(timezone=True) back tz-naive (offset dropped);
    # normalize before comparing against now(UTC).
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _write_lock_state(
    db_session, user_id, *, failed_attempts: int, locked_until: datetime | None
):
    """Direct row write — set lock timestamps via the DB, not clock mocks."""
    user = await db_session.get(User, user_id)
    user.failed_attempts = failed_attempts
    user.locked_until = locked_until
    await db_session.commit()


async def _seed_oidc_only_user(db_session, tenant_id, username="oidcuser") -> str:
    """An OIDC-only account: no local password, Logto is its login path."""
    uid = uuid.uuid4().hex
    db_session.add(
        User(
            id=uid,
            username=username,
            email=f"{username}@example.com",
            password=None,
            status="active",
        )
    )
    db_session.add(UserTenant(user_id=uid, tenant_id=tenant_id, role="member"))
    await db_session.commit()
    return uid


@pytest.mark.asyncio
async def test_lockout_after_five_failures(app_client, db_session):
    uid = await _seed_loginable_user(app_client)
    for _ in range(5):
        resp = await _login(app_client, "loginuser", "wrong-password")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid credentials"

    # 6th attempt with the CORRECT password is still rejected inside the window.
    resp = await _login(app_client, "loginuser", "Pass1234!")
    assert resp.status_code == 401
    assert resp.json()["detail"] == LOCKOUT_DETAIL

    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0  # counter reset when the lock triggered
    assert user.locked_until is not None
    assert (
        datetime.now(UTC) + timedelta(minutes=14)
        < _as_utc(user.locked_until)
        <= datetime.now(UTC) + timedelta(minutes=15)
    )

    # The lock trigger writes exactly one audit row.
    from sqlalchemy import select

    from app.models.log import SystemLog

    logs = (
        (
            await db_session.execute(
                select(SystemLog).where(
                    SystemLog.action == "login_locked",
                    SystemLog.module == "auth",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].user_id == uid


@pytest.mark.asyncio
async def test_lockout_expires_then_login_succeeds(app_client, db_session):
    uid = await _seed_loginable_user(app_client)
    # Simulate an elapsed lock: the deadline is already in the past.
    await _write_lock_state(
        db_session,
        uid,
        failed_attempts=0,
        locked_until=datetime.now(UTC) - timedelta(minutes=1),
    )
    resp = await _login(app_client, "loginuser", "Pass1234!")
    assert resp.status_code == 200, resp.text
    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0
    assert user.locked_until is None  # success cleared the residual lock


@pytest.mark.asyncio
async def test_failures_inside_lock_neither_count_nor_renew(app_client, db_session):
    uid = await _seed_loginable_user(app_client)
    until = datetime.now(UTC) + timedelta(minutes=10)
    await _write_lock_state(db_session, uid, failed_attempts=0, locked_until=until)

    resp = await _login(app_client, "loginuser", "wrong-password")
    assert resp.status_code == 401
    assert resp.json()["detail"] == LOCKOUT_DETAIL

    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0  # not counted
    assert _as_utc(user.locked_until) == until  # not renewed


@pytest.mark.asyncio
async def test_success_resets_counter(app_client, db_session):
    uid = await _seed_loginable_user(app_client)
    for _ in range(4):
        resp = await _login(app_client, "loginuser", "wrong-password")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid credentials"
    resp = await _login(app_client, "loginuser", "Pass1234!")
    assert resp.status_code == 200, resp.text
    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0
    assert user.locked_until is None

    # 4 more failures stay below the threshold; the correct password still works.
    for _ in range(4):
        resp = await _login(app_client, "loginuser", "wrong-password")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid credentials"
    resp = await _login(app_client, "loginuser", "Pass1234!")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_admin_status_lock_never_counted(app_client, db_session):
    """status="locked" (administrator permanent lock) rejects BEFORE the
    password verdict, so it never touches the lockout counter — the two lock
    systems are independent."""
    uid = await _seed_loginable_user(app_client)
    await app_client.patch(
        f"/api/v1/users/{uid}/status", json={"status": "locked"}, headers=AUTH
    )
    resp = await _login(app_client, "loginuser", "wrong-password")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "account is locked; contact an administrator"
    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_unknown_user_ten_failures_no_side_effect(app_client):
    """Non-existent accounts have no row to count — 10 attempts must keep
    returning plain invalid-credentials (that path is IP rate limiting's job,
    slice 02)."""
    for _ in range(10):
        resp = await _login(app_client, "ghost", "whatever")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_oidc_only_account_never_locked(app_client, db_session, tenant_owner):
    """password=None accounts are excluded from counting: a local lock cannot
    reach their real (Logto) login path, so counting them would be a pure
    denial-of-service surface."""
    uid = await _seed_oidc_only_user(db_session, tenant_owner["tenant_id"])
    for _ in range(6):
        resp = await _login(app_client, "oidcuser", "wrong-password")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid credentials"
    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_lockout_repo_atomic_increment(db_session, tenant_owner):
    """Direct repository test: record_failed_attempt is a single-statement
    UPDATE — two calls land on exactly 1 then 2, never a lost increment."""
    from app.repositories.tenant import UserRepository

    uid = uuid.uuid4().hex
    db_session.add(
        User(
            id=uid,
            username="counteruser",
            email="counter@example.com",
            password=hash_password("Pass1234!"),
            status="active",
        )
    )
    await db_session.commit()

    repo = UserRepository(db_session)
    assert await repo.record_failed_attempt(uid) == 1
    assert await repo.record_failed_attempt(uid) == 2
    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 2

    until = datetime.now(UTC) + timedelta(minutes=15)
    await repo.set_locked_until(uid, until)
    user = await _get_user(db_session, uid)
    assert _as_utc(user.locked_until) == until
    assert user.failed_attempts == 2  # set_locked_until leaves the counter alone

    await repo.reset_failed_attempts(uid)
    user = await _get_user(db_session, uid)
    assert user.failed_attempts == 0
    assert user.locked_until is None


# ---------------------------------------------------------------------------
# Token TTL (rate-limit-login-lockout slice 03): newly minted tokens expire
# after 8 hours (access_token_ttl_minutes 10080 → 480) and the UserSession
# row aligns (session_ttl_hours 168 → 8). Existing tokens are NOT revoked —
# they expire naturally.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_token_ttl_is_eight_hours(app_client):
    """Login reports expires_in == 480*60 (8h, down from the 7-day default)."""
    await _seed_loginable_user(app_client)
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={"username": "loginuser", "password": "Pass1234!"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["expires_in"] == 480 * 60


@pytest.mark.asyncio
async def test_login_session_row_expires_eight_hours(
    app_client_real_auth, db_session, tenant_owner
):
    """The UserSession row persisted at login expires ≈ now + 8h."""
    from app.repositories.security import SessionRepository

    uid = await _seed_user_via_db(db_session, tenant_owner["tenant_id"])
    tok = (
        await app_client_real_auth.post(
            "/api/v1/auth/login",
            json={"username": "realmember", "password": "Pass1234!"},
        )
    ).json()["access_token"]
    row = await SessionRepository(db_session).get_by_session_id(_decode_jti(tok))
    assert row is not None
    assert row.user_id == uid
    delta = _as_utc(row.expires_at) - datetime.now(UTC)
    assert timedelta(hours=7, minutes=59) < delta <= timedelta(hours=8)
