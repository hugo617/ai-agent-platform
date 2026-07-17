"""API token fine-grained scope tests (api-token-fine-grained-scopes).

Covers the scope convergence + gate:

  * ``issue`` intersects requested scopes with the grantor's CURRENT perms
    (super_admin special case: full catalogue, since casbin has no policy).
  * ``permission_service.check`` enforces the restricted-scope gate BEFORE the
    super_admin / hq_staff bypass, reading ``current_token_ctx`` (set by the
    ``ahp_`` auth bypass). Writes/chat/export imply read on the same object.
  * Legacy tokens are backfilled to ``scope_mode="full"`` (behaviour-equivalent).

The contextvar propagation across the StreamingResponse task boundary is
already covered by the spike; these tests focus on the scope algebra itself.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


async def _issue(client, name: str, **body) -> dict:
    """Issue a token via the API and return the one-time plaintext response."""
    resp = await client.post("/api/v1/api-tokens", json={"name": name, **body}, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _issue_restricted(client, name: str, scopes: list[str]) -> dict:
    return await _issue(client, name, scope_mode="restricted", scopes=scopes)


async def _make_agent(client, name: str = "helper") -> dict:
    resp = await client.post(
        "/api/v1/agents/",
        json={"name": name, "system_prompt": "", "model": "deepseek-chat"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Issue-time convergence (the ∩ grantor perms algebra)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restricted_issue_intersects_with_grantor_perms(app_client):
    """A restricted token keeps only the scopes the grantor actually has.

    The owner has ``agents:read`` + ``agents:create`` (and more). Requesting a
    scope the owner DOESN'T have (``users:delete`` is owner-granted, so use
    ``billing:update`` which owner lacks) drops it silently from the stored
    scopes. The response echoes the converged (smaller) scope set.
    """
    # owner has billing:read but NOT billing:update.
    issued = await _issue_restricted(
        app_client,
        "conv",
        scopes=["agents:read", "billing:update", "billing:read"],
    )
    # billing:update was dropped (owner doesn't have it); the other two kept.
    assert "agents:read" in issued["scopes"]
    assert "billing:read" in issued["scopes"]
    assert "billing:update" not in issued["scopes"]
    assert issued["scope_mode"] == "restricted"


@pytest.mark.asyncio
async def test_restricted_issue_with_empty_intersection_returns_422(app_client):
    """Restricted + scopes that ALL miss the grantor's perms → ScopeError 422.

    The token would be useless, so refuse rather than silently create a dead
    token.
    """
    # owner has no wallet:update... actually owner DOES have wallet:update. Use
    # a scope that doesn't exist at all to guarantee empty intersection.
    resp = await app_client.post(
        "/api/v1/api-tokens",
        json={
            "name": "dead",
            "scope_mode": "restricted",
            "scopes": ["nonexistent:read", "alsobogus:create"],
        },
        headers=AUTH,
    )
    assert resp.status_code == 422, resp.text
    assert "收敛后无可用 scope" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_restricted_issue_with_empty_scopes_returns_422(app_client):
    """Restricted + no scopes selected → 422 (intersection of [] with anything is [])."""
    resp = await app_client.post(
        "/api/v1/api-tokens",
        json={"name": "empty", "scope_mode": "restricted", "scopes": []},
        headers=AUTH,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_full_issue_keeps_scopes_verbatim(app_client):
    """Full mode stores the requested scopes as-is (informational; check ignores them)."""
    issued = await _issue(
        app_client,
        "full-info",
        scope_mode="full",
        scopes=["agents:read", "nonexistent:bogus"],
    )
    # Full mode doesn't converge — bogus scope is kept (check never reads it).
    assert issued["scope_mode"] == "full"
    assert "agents:read" in issued["scopes"]
    assert "nonexistent:bogus" in issued["scopes"]


# ---------------------------------------------------------------------------
# Super-admin convergence special case (hard constraint #1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_super_admin_restricted_issue_does_not_collapse_to_empty(super_admin_client):
    """super_admin has NO casbin policy (bypasses via platform_role), so a naive
    intersection would yield []. The service substitutes the full catalogue —
    the requested scopes survive.
    """
    issued = await _issue_restricted(
        super_admin_client,
        "sa-scoped",
        scopes=["agents:read", "menu:tenants"],
    )
    # Both survive because _all_known_scope_codes() includes them.
    assert "agents:read" in issued["scopes"]
    assert "menu:tenants" in issued["scopes"], (
        "menu:tenants must be in _all_known_scope_codes() — hard constraint #4"
    )


@pytest.mark.asyncio
async def test_all_known_scope_codes_includes_menu_tenants():
    """Unit test for the helper: menu:tenants (super_admin-only menu) must be present."""
    from app.services.api_token_service import _all_known_scope_codes

    codes = _all_known_scope_codes()
    assert "menu:tenants" in codes
    # And the regular owner perms.
    assert "customers:export" in codes
    assert "conversations:chat" in codes


# ---------------------------------------------------------------------------
# Restricted-scope gate at check time (hard constraints #3 and #5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restricted_token_denied_outside_scope(app_client):
    """A restricted token scoped to agents:read CANNOT call conversations:list.

    The gate runs before the casbin lookup, so even though the issuer (owner)
    has conversations:read, the token's restricted scope denies it.
    """
    issued = await _issue_restricted(app_client, "ro-agents", scopes=["agents:read"])
    # conversations:list requires conversations:read — not in scope.
    resp = await app_client.get(
        "/api/v1/conversations/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_restricted_token_allows_in_scope(app_client):
    """The same token CAN call agents:list (in scope)."""
    issued = await _issue_restricted(app_client, "ro-agents-2", scopes=["agents:read"])
    resp = await app_client.get(
        "/api/v1/agents/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_restricted_token_write_implies_read():
    """Hard constraint #5: customers:update implies customers:read.

    A token scoped to ``customers:update`` must satisfy a customers:read check
    (the gate adds ``<obj>:read`` to the required set when the action is a
    write). We pass ``platform_role="super_admin"`` so that if the gate
    passes, the bypass returns True — making the scope gate the ONLY variable
    (if the gate rejected, it would return False before reaching the bypass).
    """
    from app.api.token_context import TokenCtx, current_token_ctx
    from app.services.permission_service import permission_service

    token_ctx = TokenCtx(
        token_id="t",
        scopes=["customers:update"],
        scope_mode="restricted",
    )
    token_ctx_set = current_token_ctx.set(token_ctx)
    try:
        # Gate must pass (update implies read) → reaches bypass → True.
        allowed = await permission_service.check(
            "u", "t", "customers", "read", platform_role="super_admin"
        )
        assert allowed is True, "customers:update should imply customers:read"
    finally:
        current_token_ctx.reset(token_ctx_set)


@pytest.mark.asyncio
async def test_restricted_token_chat_implies_read():
    """Hard constraint #5: conversations:chat implies conversations:read."""
    from app.api.token_context import TokenCtx, current_token_ctx
    from app.services.permission_service import permission_service

    token_ctx = TokenCtx(
        token_id="t",
        scopes=["conversations:chat"],
        scope_mode="restricted",
    )
    token_ctx_set = current_token_ctx.set(token_ctx)
    try:
        allowed = await permission_service.check(
            "u", "t", "conversations", "read", platform_role="super_admin"
        )
        assert allowed is True
    finally:
        current_token_ctx.reset(token_ctx_set)


@pytest.mark.asyncio
async def test_restricted_token_export_implies_read():
    """Hard constraint #5: customers:export implies customers:read."""
    from app.api.token_context import TokenCtx, current_token_ctx
    from app.services.permission_service import permission_service

    token_ctx = TokenCtx(
        token_id="t",
        scopes=["customers:export"],
        scope_mode="restricted",
    )
    token_ctx_set = current_token_ctx.set(token_ctx)
    try:
        allowed = await permission_service.check(
            "u", "t", "customers", "read", platform_role="super_admin"
        )
        assert allowed is True
    finally:
        current_token_ctx.reset(token_ctx_set)


@pytest.mark.asyncio
async def test_super_admin_restricted_token_is_bounded_by_scope(super_admin_client):
    """Hard constraint #3: scope gate runs BEFORE super_admin bypass.

    A super_admin-issued restricted token scoped to agents:read ONLY must NOT
    be able to call conversations:list, even though the issuer is super_admin.
    Without the gate-before-bypass ordering, super_admin would short-circuit
    True and the scope would be ignored.
    """
    issued = await _issue_restricted(
        super_admin_client, "sa-strict", scopes=["agents:read"]
    )
    resp = await super_admin_client.get(
        "/api/v1/conversations/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 403, (
        "super_admin restricted token must be bounded by its scopes — "
        "if this passes, the scope gate isn't running before the bypass"
    )


@pytest.mark.asyncio
async def test_super_admin_restricted_token_allows_in_scope(super_admin_client):
    """The same super_admin restricted token CAN call agents:list (in scope)."""
    issued = await _issue_restricted(
        super_admin_client, "sa-strict-2", scopes=["agents:read"]
    )
    resp = await super_admin_client.get(
        "/api/v1/agents/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Full mode + JWT path zero-regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_mode_token_bypasses_scope_gate(app_client):
    """A full-mode token is NOT bounded by its (informational) scopes.

    Issue a full-mode token with scopes=[] and it should still work like a
    legacy token — inheriting the grantor's current perms (the gate is skipped
    for full mode).
    """
    issued = await _issue(app_client, "full-empty", scope_mode="full", scopes=[])
    # conversations:list works because the gate is skipped for full mode.
    resp = await app_client.get(
        "/api/v1/conversations/",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_jwt_path_contextvar_is_none():
    """JWT path (no ahp_ token) must not set the contextvar — zero regression.

    check() reads current_token_ctx.get(); if it's None the scope gate is
    skipped entirely. This is the default-state guarantee for every non-ahp_
    request.
    """
    from app.api.token_context import current_token_ctx

    assert current_token_ctx.get() is None


@pytest.mark.asyncio
async def test_jwt_super_admin_bypass_unchanged(super_admin_client):
    """Existing super_admin bypass (JWT path) must still work — regression guard."""
    # No ahp_ token, just the mocked JWT with platform_role=super_admin.
    resp = await super_admin_client.get(
        "/api/v1/conversations/",
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# verify endpoint echoes scope context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_endpoint_echoes_scopes(app_client):
    """/api-tokens/verify returns the token's scope context (for introspection)."""
    issued = await _issue_restricted(
        app_client, "introspect", scopes=["agents:read", "agents:create"]
    )
    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers={"Authorization": f"Bearer {issued['token']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["scope_mode"] == "restricted"
    assert set(body["scopes"]) == {"agents:read", "agents:create"}


@pytest.mark.asyncio
async def test_verify_endpoint_jwt_path_scopes_null(app_client):
    """JWT path verify returns scopes/scope_mode = null (no token context)."""
    resp = await app_client.get(
        "/api/v1/api-tokens/verify",
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scopes"] is None
    assert body["scope_mode"] is None
