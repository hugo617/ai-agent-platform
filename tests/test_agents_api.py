"""Agent CRUD API tests."""

import pytest


@pytest.mark.asyncio
async def test_create_and_get_agent(app_client):
    payload = {"name": "Support Bot", "system_prompt": "Be helpful.", "model": "gpt-4o-mini"}
    resp = await app_client.post(
        "/api/v1/agents/", json=payload, headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Support Bot"
    agent_id = body["id"]

    resp = await app_client.get(
        f"/api/v1/agents/{agent_id}", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == agent_id


@pytest.mark.asyncio
async def test_list_agents(app_client):
    await app_client.post(
        "/api/v1/agents/",
        json={"name": "A1"},
        headers={"Authorization": "Bearer fake"},
    )
    await app_client.post(
        "/api/v1/agents/",
        json={"name": "A2"},
        headers={"Authorization": "Bearer fake"},
    )
    resp = await app_client.get(
        "/api/v1/agents/", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_update_agent(app_client):
    create = await app_client.post(
        "/api/v1/agents/",
        json={"name": "Old"},
        headers={"Authorization": "Bearer fake"},
    )
    agent_id = create.json()["id"]

    resp = await app_client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"name": "New", "model": "gpt-4o"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New"
    assert body["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_delete_agent(app_client):
    create = await app_client.post(
        "/api/v1/agents/",
        json={"name": "Doomed"},
        headers={"Authorization": "Bearer fake"},
    )
    agent_id = create.json()["id"]

    resp = await app_client.delete(
        f"/api/v1/agents/{agent_id}", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 204

    resp = await app_client.get(
        f"/api/v1/agents/{agent_id}", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_returns_404(app_client):
    resp = await app_client.get(
        "/api/v1/agents/nonexistent", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 404
