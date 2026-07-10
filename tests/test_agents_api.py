"""Agent CRUD API tests."""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# --------------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_create_and_get_agent(app_client):
    payload = {"name": "Support Bot", "system_prompt": "Be helpful.", "model": "gpt-4o-mini"}
    resp = await app_client.post(
        "/api/v1/agents/", json=payload, headers=AUTH
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Support Bot"
    agent_id = body["id"]

    resp = await app_client.get(f"/api/v1/agents/{agent_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["id"] == agent_id


@pytest.mark.asyncio
async def test_list_agents(app_client):
    await app_client.post(
        "/api/v1/agents/", json={"name": "A1"}, headers=AUTH
    )
    await app_client.post(
        "/api/v1/agents/", json={"name": "A2"}, headers=AUTH
    )
    resp = await app_client.get("/api/v1/agents/", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_update_agent(app_client):
    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Old"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    resp = await app_client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"name": "New", "model": "gpt-4o"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New"
    assert body["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_delete_agent(app_client):
    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Doomed"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    resp = await app_client.delete(f"/api/v1/agents/{agent_id}", headers=AUTH)
    assert resp.status_code == 204

    resp = await app_client.get(f"/api/v1/agents/{agent_id}", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_returns_404(app_client):
    resp = await app_client.get(
        "/api/v1/agents/nonexistent", headers=AUTH
    )
    assert resp.status_code == 404


# ------------------------------------------------------- permission boundary


@pytest.mark.asyncio
async def test_member_can_read_agents(member_client):
    """member has agents:read → 200 (can see, cannot modify)."""
    resp = await member_client.get("/api/v1/agents/", headers=AUTH)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_member_cannot_create_agent(member_client):
    """member has no agents:create → 403 (guard fires before the body runs)."""
    resp = await member_client.post(
        "/api/v1/agents/",
        json={"name": "Forbidden Bot"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_update_agent(member_client):
    """member has no agents:update → 403 (guard fires before lookup)."""
    resp = await member_client.patch(
        "/api/v1/agents/any-id",
        json={"name": "Hijacked"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_delete_agent(member_client):
    """member has no agents:delete → 403 (guard fires before lookup)."""
    resp = await member_client.delete("/api/v1/agents/any-id", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_delete_agent(app_client, tenant_admin_client):
    """admin has no agents:delete → 403 (admin can create/update, not delete)."""
    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Admin Target"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    resp = await tenant_admin_client.delete(f"/api/v1/agents/{agent_id}", headers=AUTH)
    assert resp.status_code == 403


# --------------------------------------------------------- multi-tenant wall


@pytest.mark.asyncio
async def test_cross_tenant_agent_not_visible(app_client, db_session, tenant_owner):
    """An agent created in tenant B cannot be read from tenant A.

    Tenant isolation is enforced in the repository layer (tenant_id filter),
    so a cross-tenant agent_id is reported as 404 (not found *for this
    tenant*) rather than leaking its existence.
    """
    from app.models.agent import Agent

    other_tenant_id = "tnt-other-cross-wall"
    agent = Agent(
        id="agent-other-tenant",
        tenant_id=other_tenant_id,
        name="Other Tenant's Bot",
    )
    db_session.add(agent)
    await db_session.commit()

    resp = await app_client.get(
        f"/api/v1/agents/{agent.id}", headers=AUTH
    )
    assert resp.status_code == 404

    # The cross-tenant agent never appears in this tenant's list either.
    resp = await app_client.get("/api/v1/agents/", headers=AUTH)
    assert all(a["id"] != agent.id for a in resp.json())


# ------------------------------------------------------ soft/hard delete list


@pytest.mark.asyncio
async def test_deleted_agent_absent_from_list(app_client):
    """After deletion the agent no longer shows in the list (not just get 404)."""
    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Ephemeral"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    await app_client.delete(f"/api/v1/agents/{agent_id}", headers=AUTH)

    resp = await app_client.get("/api/v1/agents/", headers=AUTH)
    assert all(a["id"] != agent_id for a in resp.json())


# -------------------------------------------------------------- 404 mapping


@pytest.mark.asyncio
async def test_update_nonexistent_agent_returns_404(app_client):
    """NotFoundError → 404 (typed exception, not a blanket ValueError→404)."""
    resp = await app_client.patch(
        "/api/v1/agents/nonexistent-id",
        json={"name": "Ghost"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_agent_returns_404(app_client):
    resp = await app_client.delete("/api/v1/agents/nonexistent-id", headers=AUTH)
    assert resp.status_code == 404
