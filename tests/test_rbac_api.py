"""Roles + organizations API tests."""

import pytest

AUTH = {"Authorization": "Bearer fake"}


@pytest.mark.asyncio
async def test_role_labels_empty_by_default(app_client):
    """Without tenant seeding (tests bypass create_tenant), no roles exist."""
    resp = await app_client.get("/api/v1/roles/label", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_list_role(app_client):
    resp = await app_client.post(
        "/api/v1/roles/",
        json={"name": "Editor", "code": "editor", "description": "can edit"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    assert role["code"] == "editor"
    assert role["is_system"] is False

    resp = await app_client.get("/api/v1/roles/", headers=AUTH)
    assert resp.status_code == 200
    assert any(r["code"] == "editor" for r in resp.json())

    resp = await app_client.get("/api/v1/roles/label", headers=AUTH)
    assert any(r["code"] == "editor" for r in resp.json())


@pytest.mark.asyncio
async def test_duplicate_role_code_rejected(app_client):
    payload = {"name": "Editor", "code": "editor_x"}
    resp = await app_client.post("/api/v1/roles/", json=payload, headers=AUTH)
    assert resp.status_code == 201
    resp = await app_client.post("/api/v1/roles/", json=payload, headers=AUTH)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_and_delete_role(app_client):
    rid = (
        await app_client.post(
            "/api/v1/roles/",
            json={"name": "Temp", "code": "temp_role"},
            headers=AUTH,
        )
    ).json()["id"]

    resp = await app_client.put(
        f"/api/v1/roles/{rid}", json={"name": "Temp Renamed"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Temp Renamed"

    resp = await app_client.delete(f"/api/v1/roles/{rid}", headers=AUTH)
    assert resp.status_code == 204

    resp = await app_client.get("/api/v1/roles/", headers=AUTH)
    assert rid not in [r["id"] for r in resp.json()]


@pytest.mark.asyncio
async def test_org_tree_crud(app_client):
    # create root
    root = (
        await app_client.post(
            "/api/v1/organizations/",
            json={"name": "Engineering", "code": "eng"},
            headers=AUTH,
        )
    ).json()
    assert root["name"] == "Engineering"

    # create child
    child = (
        await app_client.post(
            "/api/v1/organizations/",
            json={"name": "Backend", "code": "be", "parent_id": root["id"]},
            headers=AUTH,
        )
    ).json()

    # tree shows child nested under root
    resp = await app_client.get("/api/v1/organizations/tree", headers=AUTH)
    assert resp.status_code == 200
    tree = resp.json()
    assert any(n["id"] == root["id"] for n in tree)
    root_node = next(n for n in tree if n["id"] == root["id"])
    assert any(c["id"] == child["id"] for c in root_node["children"])

    # delete root: child gets reparented to root level
    await app_client.delete(f"/api/v1/organizations/{root['id']}", headers=AUTH)
    resp = await app_client.get("/api/v1/organizations/tree", headers=AUTH)
    flat_ids = [n["id"] for n in resp.json()]
    assert child["id"] in flat_ids  # reparented
    assert root["id"] not in flat_ids
