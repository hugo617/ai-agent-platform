"""API token (PAT) auth tests — issue, verify (bypass), list (masked), revoke.

Covers the AtoA auth surface end to end: a token issued for the owner can call
existing APIs via the ``ahp_`` bypass (no JWT involved), the bypass doesn't
disturb the JWT path (regression), and tokens enforce active/expiry/revocation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

AUTH = {"Authorization": "Bearer fake"}


async def _issue(client, name: str = "my-agent", **body) -> dict:
    """Issue a token via the API and return the one-time plaintext response."""
    resp = await client.post("/api/v1/api-tokens", json={"name": name, **body}, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _make_agent(client, name: str = "helper") -> dict:
    resp = await client.post(
        "/api/v1/agents/", json={"name": name, "system_prompt": "", "model": "deepseek-chat"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Issue + masked listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_returns_plaintext_once(app_client):
    """Issue returns the plaintext token + a masked prefix, exactly once."""
    body = await _issue(app_client, name="cursor-agent")
    assert body["token"].startswith("ahp_")
    assert body["token_id"]
    assert body["name"] == "cursor-agent"
    # prefix is the short indexed slice, not the full token
    assert body["token_prefix"].startswith("ahp_")
    assert len(body["token_prefix"]) < len(body["token"])


@pytest.mark.asyncio
async def test_list_returns_masked_no_plaintext(app_client):
    """GET list shows the masked prefix but never the plaintext or ciphertext."""
    issued = await _issue(app_client, name="ci-bot")
    resp = await app_client.get("/api/v1/api-tokens", headers=AUTH)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    matching = [r for r in rows if r["id"] == issued["token_id"]]
    assert matching, "issued token should appear in the listing"
    row = matching[0]
    assert row["token_prefix"] == issued["token_prefix"]
    assert row["name"] == "ci-bot"
    # The response model carries no secret field at all.
    assert "token" not in row
    assert "token_hash" not in row


# ---------------------------------------------------------------------------
# Auth bypass — the heart of AtoA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issued_token_accesses_existing_api(app_client):
    """The core value: an ahp_ token can call existing /agents via the bypass.

    app_client mocks decode_token for JWTs, but the ahp_ prefix routes to the
    token bypass BEFORE decode_token is ever called — so this exercises the
    real ApiTokenService.verify path against the seeded DB.
    """
    agent = await _make_agent(app_client)
    issued = await _issue(app_client, name="external-agent")

    # Use the plaintext token as a Bearer credential.
    resp = await app_client.get(
        "/api/v1/agents/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200, resp.text
    ids = [a["id"] for a in resp.json()]
    assert agent["id"] in ids


@pytest.mark.asyncio
async def test_bypass_does_not_touch_jwt_path(app_client):
    """An ahp_ token must NOT reach decode_token (proves the bypass isolates)."""
    await _issue(app_client, name="probe")
    # Re-mock decode_token to RAISE — if the bypass leaks into the JWT path at
    # all, this token request fails. The ahp_ path returns before decode_token.
    with patch(
        "app.api.deps.decode_token",
        new=AsyncMock(side_effect=AssertionError("ahp_ token must not reach decode_token")),
    ):
        resp = await app_client.get(
            "/api/v1/api-tokens/verify",
            headers={"Authorization": "Bearer ahp_nonexistent_but_prefixd"},
        )
    # Unknown token → 401 from the bypass, NOT the AssertionError.
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_path_still_works(app_client):
    """Regression: a non-ahp_ token still flows through the JWT path normally."""
    resp = await app_client.get("/api/v1/agents/", headers=AUTH)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_verify_endpoint_echoes_identity(app_client):
    """/api-tokens/verify returns the resolved principal (CLI whoami)."""
    issued = await _issue(app_client, name="whoami-check")
    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["user_id"]
    assert body["tenant_id"]


# ---------------------------------------------------------------------------
# Revocation + expiry enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_blocks_future_use(app_client):
    """After DELETE, the token is rejected (401) on the next request."""
    issued = await _issue(app_client, name="to-revoke")
    # Token works before revocation.
    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200

    resp = await app_client.delete(
        f"/api/v1/api-tokens/{issued['token_id']}", headers=AUTH
    )
    assert resp.status_code == 204

    # ...and is rejected after.
    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_revoke_nonexistent_returns_404(app_client):
    resp = await app_client.delete(
        f"/api/v1/api-tokens/{uuid.uuid4().hex}", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoked_token_absent_from_listing(app_client):
    """Revoked tokens disappear from the masked listing."""
    issued = await _issue(app_client, name="gone-soon")
    await app_client.delete(f"/api/v1/api-tokens/{issued['token_id']}", headers=AUTH)
    resp = await app_client.get("/api/v1/api-tokens", headers=AUTH)
    assert all(r["id"] != issued["token_id"] for r in resp.json())


@pytest.mark.asyncio
async def test_expired_token_rejected(app_client, db_session, tenant_owner):
    """A token past its expires_at is rejected even though its row is active."""
    from app.core import crypto
    from app.models.api_token import ApiToken

    plaintext = "ahp_" + uuid.uuid4().hex + "expiredtokenbody"
    row = ApiToken(
        tenant_id=tenant_owner["tenant_id"],
        created_by_user_id=tenant_owner["user_id"],
        name="already-expired",
        token_type="pat",
        token_hash=crypto.encrypt(plaintext),
        token_prefix=plaintext[:16],
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(row)
    await db_session.commit()

    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Permission boundary + cross-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_cannot_issue(member_client):
    """Members lack api_tokens:manage and get 403."""
    resp = await member_client.post(
        "/api/v1/api-tokens", json={"name": "forbidden"}, headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_list(member_client):
    resp = await member_client.get("/api/v1/api-tokens", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_token_inherits_issuer_role(app_client, db_session, test_env):
    """A token issued by the owner inherits owner permissions (agents:create).

    The owner creates an agent through the API-token-authenticated request —
    that requires agents:create, which only owner/admin have. If the bypass
    failed to bind the issuer's role, this would 403.
    """
    issued = await _issue(app_client, name="creator")
    resp = await app_client.post(
        "/api/v1/agents/",
        json={"name": "via-token", "system_prompt": "", "model": "deepseek-chat"},
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_token_isolated_to_its_tenant(app_client, db_session, tenant_owner):
    """A token's tenant_id is fixed: it cannot read another tenant's data.

    Even if the issuer user existed in another tenant, the token bypass binds
    tenant_id from the token row, so the agents repo filters to this tenant
    only. We seed an agent in another tenant and confirm it's invisible.
    """
    from app.models.agent import Agent
    from app.models.tenant import Tenant

    other_tenant = "tnt-other-token-wall"
    db_session.add(Tenant(id=other_tenant, name="Other"))
    db_session.add(
        Agent(tenant_id=other_tenant, name="secret-agent", system_prompt="", model="deepseek-chat")
    )
    await db_session.commit()

    issued = await _issue(app_client, name="scoped")
    resp = await app_client.get(
        "/api/v1/agents/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "secret-agent" not in names


@pytest.mark.asyncio
async def test_token_voided_when_user_disabled(app_client, db_session, test_env):
    """Disabling the issuer account voids the token (re-validation on auth)."""
    from app.models.tenant import User

    issued = await _issue(app_client, name="will-be-disabled")

    user = await db_session.get(User, test_env.owner_user)
    assert user is not None
    user.status = "disabled"
    await db_session.commit()

    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 401
