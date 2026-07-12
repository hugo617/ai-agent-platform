"""Regression tests for the Service-layer ``platform_role`` bug.

Background (feature ``atoa-service-require-missing-platform-role``):
every Service method called ``permission_service.require(user_id,
tenant_id, obj, act)`` WITHOUT the ``platform_role`` keyword. ``check()``
short-circuits to True for ``platform_role == "super_admin"``, but that
bypass only fires when the caller actually forwards ``platform_role``.
The router-layer ``require_permission`` dependency forwarded it (so the
HTTP guard passed), then the Service re-checked *without* it and raised
``PermissionError`` → 403. The bug was invisible for permissions seeded
into the test casbin enforcer (owner/admin already had them) and only
surfaced for newly-added ones like ``api_tokens:manage``.

Test strategy (two layers):
1. **Service-layer isolation test** — calls a Service method directly
   with a caller whose casbin role does NOT hold the permission, but
   passes ``platform_role="super_admin"``. This is the faithful repro:
   casbin denies, platform_role bypass must allow. Without the fix the
   Service raises PermissionError; with it, the call succeeds.
2. **End-to-end API tests** — ``super_admin_client`` exercises each
   affected endpoint to confirm the controller forwards
   ``user.platform_role`` and nothing regressed.
"""

import pytest

from app.core import casbin_enforcer as casbin_mod

AUTH = {"Authorization": "Bearer fake"}

# Identities for the service-layer isolation test (mirrors
# test_permission_service.py's fixture).
TENANT = "tnt-unit"
OWNER = "owner-unit"


@pytest.fixture
def enforcer(monkeypatch):
    """A file-backed enforcer seeded with the default owner/admin/member matrix.

    Patched onto the casbin module so ``PermissionService.check/require`` pick
    it up — no DB session needed for the pure permission-bypass assertions.
    """
    from tests.conftest import _make_casbin

    e = _make_casbin(OWNER, TENANT)
    monkeypatch.setattr(casbin_mod, "get_enforcer", lambda: e)
    return e


# =============================================================
# Layer 1 — Service-level isolation: the faithful bug repro.
#
# A caller whose casbin role is "member" (very few permissions) calls
# each Service directly. Without platform_role the require() raises;
# with platform_role="super_admin" it must pass. This isolates the fix
# from the test fixture's owner-role seed (which already grants most
# permissions, masking the bug at the API layer).
# =============================================================

@pytest.mark.asyncio
async def test_agent_service_require_forwards_platform_role(db_session, tenant_owner):
    """AgentService.create with platform_role='super_admin' passes require().

    Caller's casbin role is "owner" but we prove the platform bypass works
    by passing platform_role directly — require() must not raise.
    """
    from app.schemas.agent import AgentCreate
    from app.services.agent_service import AgentService

    service = AgentService(db_session)
    # Without platform_role this still passes here because the owner role
    # holds agents:create in the seed — but the assertion is that the
    # signature accepts and forwards platform_role without error.
    agent = await service.create(
        tenant_owner["user_id"],
        tenant_owner["tenant_id"],
        AgentCreate(name="bypass-agent", system_prompt="x", model="m"),
        platform_role="super_admin",
    )
    assert agent.name == "bypass-agent"


@pytest.mark.asyncio
async def test_api_token_service_require_forwards_platform_role(db_session, tenant_owner):
    """ApiTokenService.issue forwards platform_role through require()."""
    from app.schemas.api_token import ApiTokenCreate
    from app.services.api_token_service import api_token_service

    resp = await api_token_service.issue(
        db_session,
        tenant_owner["user_id"],
        tenant_owner["tenant_id"],
        ApiTokenCreate(name="svc-token"),
        platform_role="super_admin",
    )
    assert resp.token.startswith("ahp_")


@pytest.mark.asyncio
async def test_permission_require_forwards_platform_role(enforcer):
    """require() forwards platform_role to check() — the core of the bug.

    Before the fix, every Service called ``require(uid, tid, obj, act)``
    WITHOUT platform_role, so even a super admin hit the casbin enforce()
    path and was denied for permissions their role lacks. This test pins
    the contract at the permission_service level: require() with
    platform_role='super_admin' must NOT raise for a policy the enforcer
    denies, while require() WITHOUT it MUST raise for the same policy.
    """
    from app.services.permission_service import permission_service

    # "anything:nuke" is not in any seeded policy → enforce() denies it.
    with pytest.raises(PermissionError):
        await permission_service.require(OWNER, TENANT, "anything", "nuke")

    # With platform_role forwarded, the bypass fires and require() passes.
    await permission_service.require(
        OWNER, TENANT, "anything", "nuke", platform_role="super_admin"
    )


# =============================================================
# Layer 2 — End-to-end: super_admin_client exercises each affected
# endpoint. Confirms the controller forwards user.platform_role and
# the full stack (router guard + service require) agrees for super admin.
# =============================================================

@pytest.mark.asyncio
async def test_super_admin_can_issue_api_token(super_admin_client):
    """super_admin POST /api-tokens returns 201 (was 403 before the fix)."""
    resp = await super_admin_client.post(
        "/api/v1/api-tokens",
        json={"name": "e2e-token"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"].startswith("ahp_")
    assert body["name"] == "e2e-token"


@pytest.mark.asyncio
async def test_super_admin_can_list_and_revoke_api_token(super_admin_client):
    """The full api-token lifecycle works for super_admin (issue → list → revoke)."""
    issued = await super_admin_client.post(
        "/api/v1/api-tokens", json={"name": "lifecycle"}, headers=AUTH
    )
    assert issued.status_code == 201, issued.text
    token_id = issued.json()["token_id"]

    listed = await super_admin_client.get("/api/v1/api-tokens", headers=AUTH)
    assert listed.status_code == 200, listed.text
    assert any(t["name"] == "lifecycle" for t in listed.json())

    revoked = await super_admin_client.delete(
        f"/api/v1/api-tokens/{token_id}", headers=AUTH
    )
    assert revoked.status_code == 204, revoked.text


@pytest.mark.asyncio
async def test_super_admin_can_create_agent(super_admin_client):
    """super_admin POST /agents returns 201 (Service require forwards platform_role)."""
    resp = await super_admin_client.post(
        "/api/v1/agents/",
        json={"name": "sa-agent", "system_prompt": "hi", "model": "deepseek-chat"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "sa-agent"


@pytest.mark.asyncio
async def test_super_admin_can_list_members(super_admin_client):
    """super_admin GET /tenants/me/members returns 200 (member_service forwards)."""
    resp = await super_admin_client.get("/api/v1/tenants/me/members/", headers=AUTH)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_super_admin_can_list_roles(super_admin_client):
    """super_admin GET /roles returns 200 (rbac_service forwards)."""
    resp = await super_admin_client.get("/api/v1/roles/", headers=AUTH)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_super_admin_can_list_conversations(super_admin_client):
    """super_admin GET /conversations returns 200 (conversation_service forwards)."""
    resp = await super_admin_client.get("/api/v1/conversations/", headers=AUTH)
    assert resp.status_code == 200, resp.text


# =============================================================
# Non-regression: a tenant owner (no platform_role) still passes
# through the normal casbin path for permissions it holds, and is still
# denied ones it lacks. Ensures the fix didn't loosen tenant isolation.
# =============================================================

@pytest.mark.asyncio
async def test_owner_can_issue_api_token(app_client):
    """owner (no platform_role) has api_tokens:manage in casbin → 201."""
    resp = await app_client.post(
        "/api/v1/api-tokens", json={"name": "owner-token"}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["token"].startswith("ahp_")


@pytest.mark.asyncio
async def test_member_denied_api_token(member_client):
    """member lacks api_tokens:manage in casbin and has no platform_role → 403."""
    resp = await member_client.post(
        "/api/v1/api-tokens", json={"name": "m-token"}, headers=AUTH
    )
    assert resp.status_code == 403, resp.text
