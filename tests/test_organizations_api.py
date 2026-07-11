"""Organization service tests — create/update/delete + cycle detection + tree.

Existing ``test_org_tree_crud`` (in test_rbac_api.py) covers the happy path
(root + child create, tree, delete-with-reparent). These tests fill the gaps:
update (rename/status), move subtree (parent_id change), cycle rejection
(self-parent + descendant), 404 mapping, and the pure path helpers.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


async def _create_org(client, name: str, code: str, parent_id: str | None = None) -> dict:
    payload = {"name": name, "code": code}
    if parent_id:
        payload["parent_id"] = parent_id
    resp = await client.post("/api/v1/organizations/", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------- create


@pytest.mark.asyncio
async def test_create_root_org_has_null_path(app_client):
    """A root org (no parent) has path = None."""
    org = await _create_org(app_client, "HQ", "hq")
    assert org["parent_id"] is None
    assert org["path"] is None


@pytest.mark.asyncio
async def test_create_child_org_inherits_parent_path(app_client):
    """A child's path is built from its parent's path + parent id."""
    root = await _create_org(app_client, "Engineering", "eng")
    child = await _create_org(app_client, "Backend", "be", parent_id=root["id"])
    assert child["parent_id"] == root["id"]
    assert child["path"] == f"/{root['id']}"

    grandchild = await _create_org(app_client, "API Team", "api", parent_id=child["id"])
    assert grandchild["path"] == f"/{root['id']}/{child['id']}"


@pytest.mark.asyncio
async def test_create_org_with_nonexistent_parent_400(app_client):
    """Creating an org under a nonexistent parent raises ValueError → 400."""
    resp = await app_client.post(
        "/api/v1/organizations/",
        json={"name": "Orphan", "code": "orp", "parent_id": "no-such-id"},
        headers=AUTH,
    )
    assert resp.status_code == 400
    assert "parent" in resp.json()["detail"].lower()


# --------------------------------------------------------------- update


@pytest.mark.asyncio
async def test_update_org_rename(app_client):
    """PUT can rename an org (name field)."""
    org = await _create_org(app_client, "Old Name", "old")
    resp = await app_client.put(
        f"/api/v1/organizations/{org['id']}",
        json={"name": "New Name"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "New Name"
    assert resp.json()["code"] == "old"  # unchanged


@pytest.mark.asyncio
async def test_update_org_status_and_sort(app_client):
    """PUT can update status + sort_order fields."""
    org = await _create_org(app_client, "Active Dept", "ad")
    resp = await app_client.put(
        f"/api/v1/organizations/{org['id']}",
        json={"status": "inactive", "sort_order": 5},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "inactive"
    assert body["sort_order"] == 5


@pytest.mark.asyncio
async def test_update_org_not_found_404(app_client):
    """Updating a nonexistent org returns 404 (not 400)."""
    resp = await app_client.put(
        "/api/v1/organizations/no-such-id",
        json={"name": "X"},
        headers=AUTH,
    )
    assert resp.status_code == 404


# --------------------------------------------------------------- move subtree


@pytest.mark.asyncio
async def test_move_org_to_new_parent_recomputes_path(app_client):
    """Moving a node recalculates its path (and subtree paths)."""
    root_a = await _create_org(app_client, "Division A", "diva")
    root_b = await _create_org(app_client, "Division B", "divb")
    child = await _create_org(app_client, "Team", "tm", parent_id=root_a["id"])
    assert child["path"] == f"/{root_a['id']}"

    # Move child from A → B.
    resp = await app_client.put(
        f"/api/v1/organizations/{child['id']}",
        json={"parent_id": root_b["id"]},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["path"] == f"/{root_b['id']}"
    assert resp.json()["parent_id"] == root_b["id"]


@pytest.mark.asyncio
async def test_move_org_to_root(app_client):
    """Moving a node to root (parent_id = "" / null) clears path."""
    root = await _create_org(app_client, "Top", "top")
    child = await _create_org(app_client, "Sub", "sub", parent_id=root["id"])

    resp = await app_client.put(
        f"/api/v1/organizations/{child['id']}",
        json={"parent_id": ""},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_id"] is None
    assert resp.json()["path"] is None


@pytest.mark.asyncio
async def test_move_subtree_recomputes_descendant_paths(app_client):
    """Moving a parent recomputes paths for all its descendants."""
    root_a = await _create_org(app_client, "A", "a")
    root_b = await _create_org(app_client, "B", "b")
    mid = await _create_org(app_client, "Mid", "m", parent_id=root_a["id"])
    leaf = await _create_org(app_client, "Leaf", "l", parent_id=mid["id"])
    assert leaf["path"] == f"/{root_a['id']}/{mid['id']}"

    # Move mid (with leaf beneath) from A → B.
    resp = await app_client.put(
        f"/api/v1/organizations/{mid['id']}",
        json={"parent_id": root_b["id"]},
        headers=AUTH,
    )
    assert resp.status_code == 200

    # Verify leaf's path was recomputed via the tree (full list).
    resp = await app_client.get("/api/v1/organizations/", headers=AUTH)
    orgs = {o["id"]: o for o in resp.json()}
    assert orgs[leaf["id"]]["path"] == f"/{root_b['id']}/{mid['id']}"


# --------------------------------------------------------------- cycle rejection


@pytest.mark.asyncio
async def test_org_cannot_be_own_parent(app_client):
    """An org cannot be moved under itself (400)."""
    org = await _create_org(app_client, "Self", "sf")
    resp = await app_client.put(
        f"/api/v1/organizations/{org['id']}",
        json={"parent_id": org["id"]},
        headers=AUTH,
    )
    assert resp.status_code == 400
    assert "own parent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_org_cannot_move_under_descendant(app_client):
    """An org cannot be moved beneath its own descendant (cycle, 400)."""
    root = await _create_org(app_client, "Root", "rt")
    child = await _create_org(app_client, "Child", "ch", parent_id=root["id"])
    grandchild = await _create_org(app_client, "Grandchild", "gc", parent_id=child["id"])

    # Try to move root under grandchild → would create a cycle.
    resp = await app_client.put(
        f"/api/v1/organizations/{root['id']}",
        json={"parent_id": grandchild["id"]},
        headers=AUTH,
    )
    assert resp.status_code == 400
    assert "descendant" in resp.json()["detail"].lower()


# --------------------------------------------------------------- delete


@pytest.mark.asyncio
async def test_delete_org_not_found_404(app_client):
    """Deleting a nonexistent org returns 404."""
    resp = await app_client.delete("/api/v1/organizations/no-such-id", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_org_reparents_children_with_correct_path(app_client):
    """Deleting a mid-level node reparents children to grandparent, fixing paths."""
    root = await _create_org(app_client, "Root", "rt")
    mid = await _create_org(app_client, "Mid", "md", parent_id=root["id"])
    leaf = await _create_org(app_client, "Leaf", "lf", parent_id=mid["id"])

    resp = await app_client.delete(f"/api/v1/organizations/{mid['id']}", headers=AUTH)
    assert resp.status_code == 204

    # Leaf should now be under root, path = /root_id.
    resp = await app_client.get("/api/v1/organizations/", headers=AUTH)
    orgs = {o["id"]: o for o in resp.json()}
    assert mid["id"] not in orgs  # deleted
    assert orgs[leaf["id"]]["parent_id"] == root["id"]
    assert orgs[leaf["id"]]["path"] == f"/{root['id']}"


# --------------------------------------------------------------- permission


@pytest.mark.asyncio
async def test_member_cannot_create_org(member_client):
    """A plain member lacks organizations:create → 403."""
    resp = await member_client.post(
        "/api/v1/organizations/",
        json={"name": "X", "code": "x"},
        headers=AUTH,
    )
    assert resp.status_code == 403
