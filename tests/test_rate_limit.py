"""Global API rate-limiting tests (rate-limit-login-lockout slice 02).

The module-level limiter singleton is DISABLED suite-wide (conftest sets
RATE_LIMIT_ENABLED=false before any app import); the ``rate_limit_on``
fixture below re-enables it for a single test and resets its counters around
each one, so no state leaks into the rest of the suite (or between these
tests — they all share the same 127.0.0.1 test client IP).

The default-tier quota is "3/minute" for the whole session (also set in
conftest, because the singleton resolves its default_limits callable once at
first import). The login strict tier stays at its real default "5/minute" —
that is the value under test.
"""

import time
import uuid

import jwt as pyjwt
import pytest
from sqlalchemy import select
from starlette.requests import Request

from app.core.local_auth import create_access_token
from app.core.password import hash_password
from app.core.rate_limit import limiter
from app.models.tenant import User, UserTenant

LOGIN = "/api/v1/auth/login"
AUTH = {"Authorization": "Bearer fake"}


@pytest.fixture
def rate_limit_on():
    """Enable the module-level limiter for one test, isolating its counters."""
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.reset()
    limiter.enabled = False


@pytest.fixture
def rate_limit_off():
    """Pin the limiter OFF (the suite default) and isolate counters."""
    limiter.reset()
    limiter.enabled = False
    yield
    limiter.reset()


# ---------------------------------------------------------------------------
# Strict tier: POST /auth/login, 5/min per IP
# ---------------------------------------------------------------------------


async def test_login_strict_tier_sixth_attempt_429(app_client, rate_limit_on):
    """Six login attempts in a minute: first five pass the limiter (401 for a
    nonexistent user), the sixth is rejected with 429 + Retry-After +
    project-shaped ``{"detail"}`` body."""
    payload = {"username": "ghost-user", "password": "Pass1234!"}
    for _ in range(5):
        resp = await app_client.post(LOGIN, json=payload)
        assert resp.status_code == 401, resp.text

    resp = await app_client.post(LOGIN, json=payload)
    assert resp.status_code == 429, resp.text
    assert "detail" in resp.json()
    assert resp.headers.get("retry-after"), "429 must carry a Retry-After header"


async def test_disabled_limiter_never_429(app_client, rate_limit_off):
    """RATE_LIMIT_ENABLED=false: the whole stack (strict tier included) is
    inert — ten rapid logins never produce a 429."""
    payload = {"username": "ghost-user", "password": "Pass1234!"}
    for _ in range(10):
        resp = await app_client.post(LOGIN, json=payload)
        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Default tier: every non-exempt, undecorated route (3/minute in this session)
# ---------------------------------------------------------------------------


async def test_default_tier_small_quota_429(app_client, rate_limit_on):
    """Business endpoints count against the default tier. With the session's
    3/minute quota the 4th request gets 429 + Retry-After (the strict login
    tier is NOT consumed — different bucket)."""
    for _ in range(3):
        resp = await app_client.get("/api/v1/agents/", headers=AUTH)
        assert resp.status_code == 200, resp.text

    resp = await app_client.get("/api/v1/agents/", headers=AUTH)
    assert resp.status_code == 429, resp.text
    assert "detail" in resp.json()
    assert resp.headers.get("retry-after")

    # Login bucket is independent of the business-endpoint bucket: after 4
    # business hits, a login request still goes through the limiter on its own
    # strict quota (first hit → allowed → reaches the endpoint → 401).
    resp = await app_client.post(
        LOGIN, json={"username": "ghost-user", "password": "Pass1234!"}
    )
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Exempt paths: probes + docs never enter the limiter
# ---------------------------------------------------------------------------


async def test_exempt_paths_unlimited(app_client, rate_limit_on):
    """/health is exempt: 20 rapid hits, all 200 — no 429 despite the tiny
    default quota active everywhere else."""
    for _ in range(20):
        resp = await app_client.get("/health")
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# key_func: four branches, direct invocation
# ---------------------------------------------------------------------------


def _request(headers: dict[str, str] | None = None, client_ip: str = "203.0.113.9"):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": (client_ip, 51000),
    }
    return Request(scope)


def _key(headers: dict[str, str] | None = None) -> str:
    from app.core.rate_limit import rate_limit_key

    return rate_limit_key(_request(headers))


def test_keyfunc_valid_local_token_yields_user_key():
    """A genuinely valid local HS256 token → ``user:{sub}`` bucket."""
    token, _jti = create_access_token(user_id="key-user-1", tenant_id="tnt-1")
    assert _key({"Authorization": f"Bearer {token}"}) == "user:key-user-1"


def test_keyfunc_forged_subject_token_falls_to_ip():
    """THE anti-bypass case: a token signed with the WRONG key but carrying a
    forged ``sub`` must NOT produce a user bucket — verification (not a bare
    payload decode) decides the key, so attackers cannot rotate forged subs
    to spread their quota across user buckets. Falls to the IP bucket."""
    now = int(time.time())
    forged = pyjwt.encode(
        {
            "iss": "local",
            "sub": "i-am-actually-anonymous",
            "tenant_id": "tnt-1",
            "email": None,
            "iat": now,
            "exp": now + 600,
        },
        "not-the-real-secret",
        algorithm="HS256",
    )
    assert _key({"Authorization": f"Bearer {forged}"}) == "203.0.113.9"


def test_keyfunc_garbage_token_falls_to_ip():
    assert _key({"Authorization": "Bearer not-a-jwt"}) == "203.0.113.9"


def test_keyfunc_no_token_falls_to_ip():
    assert _key() == "203.0.113.9"
    assert _key({"Authorization": ""}) == "203.0.113.9"


def test_keyfunc_pat_falls_to_ip():
    """``ahp_`` API tokens are IP-keyed by design (they resolve through a
    separate DB-backed bypass; no DB lookup per request here)."""
    assert _key({"Authorization": "Bearer ahp_wxyz1234567890"}) == "203.0.113.9"


# ---------------------------------------------------------------------------
# Coexistence with slice-01 login lockout (two independent layers)
# ---------------------------------------------------------------------------


async def _seed_password_user(db_session, tenant_id: str, username: str) -> str:
    uid = f"u-{uuid.uuid4().hex}"
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
    return uid


async def test_lockout_and_rate_limit_coexist(
    app_client, db_session, tenant_owner, rate_limit_on
):
    """Both protection layers fire independently under the same enabled app.

    Five wrong-password logins (exactly the strict-tier quota of 5/min, so all
    five pass the limiter) drive the slice-01 lockout: ``locked_until`` is set
    in the DB while the limiter is on. The 6th attempt — with the CORRECT
    password — is answered 429 by the limiter before the endpoint runs,
    proving both layers are simultaneously active without one masking the
    other's state.
    """
    username = f"coexist-{uuid.uuid4().hex[:8]}"
    await _seed_password_user(db_session, tenant_owner["tenant_id"], username)

    wrong = {"username": username, "password": "WrongPass1!"}
    for _ in range(5):
        resp = await app_client.post(LOGIN, json=wrong)
        assert resp.status_code == 401, resp.text

    # Layer 1 (slice 01): the account is locked even though the limiter is on.
    row = (await db_session.execute(select(User).where(User.username == username))).scalar_one()
    assert row.locked_until is not None

    # Layer 2 (slice 02): the 6th hit — correct password — is 429'd by the
    # limiter before the (locked) endpoint logic is ever reached.
    resp = await app_client.post(
        LOGIN, json={"username": username, "password": "Pass1234!"}
    )
    assert resp.status_code == 429, resp.text
    assert "detail" in resp.json()
