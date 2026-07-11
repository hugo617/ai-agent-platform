"""User CRUD API tests — paginated list, create, update, delete, status, reset."""

import pytest

AUTH = {"Authorization": "Bearer fake"}


def _create_payload(suffix: str) -> dict:
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "Secret123!",
        "real_name": f"Real {suffix}",
        "phone": "13800000000",
        "role": "member",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_create_and_list_user(app_client):
    resp = await app_client.post(
        "/api/v1/users/", json=_create_payload("one"), headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["username"] == "user_one"
    assert created["email"] == "user_one@example.com"
    assert "password" not in created  # never serialized out
    assert created["role"]["code"] == "member"

    resp = await app_client.get("/api/v1/users/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(u["username"] == "user_one" for u in body["items"])
    assert body["page"] == 1
    assert body["total_pages"] >= 1


@pytest.mark.asyncio
async def test_search_and_filter(app_client):
    await app_client.post("/api/v1/users/", json=_create_payload("alpha"), headers=AUTH)
    await app_client.post("/api/v1/users/", json=_create_payload("beta"), headers=AUTH)

    # search by username fragment
    resp = await app_client.get("/api/v1/users/?search=alpha", headers=AUTH)
    assert resp.status_code == 200
    names = [u["username"] for u in resp.json()["items"]]
    assert "user_alpha" in names
    assert "user_beta" not in names

    # status filter
    resp = await app_client.get("/api/v1/users/?status=active", headers=AUTH)
    assert resp.status_code == 200
    assert all(u["status"] == "active" for u in resp.json()["items"])


@pytest.mark.asyncio
async def test_filtered_total_matches_actual_rows(app_client):
    """The pagination total must equal the number of matching rows, not a
    cartesian-product inflation. Regression for the count() bug where filters
    were applied on the outer query instead of inside the subquery."""
    for i in range(3):
        await app_client.post(
            "/api/v1/users/", json=_create_payload(f"act{i}"), headers=AUTH
        )
    for i in range(2):
        body = _create_payload(f"lok{i}")
        body["status"] = "locked"
        await app_client.post("/api/v1/users/", json=body, headers=AUTH)

    for s in ("active", "locked"):
        resp = await app_client.get(
            f"/api/v1/users/?status={s}&limit=100", headers=AUTH
        )
        body = resp.json()
        assert body["total"] == len(body["items"]), (
            f"status={s}: total={body['total']} but only {len(body['items'])} rows"
        )


@pytest.mark.asyncio
async def test_sorting(app_client):
    await app_client.post("/api/v1/users/", json=_create_payload("aaa"), headers=AUTH)
    await app_client.post("/api/v1/users/", json=_create_payload("zzz"), headers=AUTH)

    resp = await app_client.get(
        "/api/v1/users/?sort_by=username&sort_order=asc", headers=AUTH
    )
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()["items"] if u["username"]]
    assert usernames == sorted(usernames)


@pytest.mark.asyncio
async def test_update_user(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("upd"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.put(
        f"/api/v1/users/{uid}",
        json={"real_name": "Updated Name", "role": "admin"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["real_name"] == "Updated Name"
    assert body["role"]["code"] == "admin"


@pytest.mark.asyncio
async def test_change_status(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("lock"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.patch(
        f"/api/v1/users/{uid}/status", json={"status": "locked"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "locked"


@pytest.mark.asyncio
async def test_reset_password(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("pw"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.post(
        f"/api/v1/users/{uid}/reset-password",
        json={"new_password": "BrandNew456!"},
        headers=AUTH,
    )
    assert resp.status_code == 204, resp.text

    # the new password now works against /auth/login (login by username)
    resp = await app_client.post(
        "/api/v1/auth/login",
        json={
            "username": "user_pw",
            "password": "BrandNew456!",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_delete_user_soft_deletes(app_client):
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("del"), headers=AUTH)
    ).json()
    uid = created["id"]

    resp = await app_client.delete(f"/api/v1/users/{uid}", headers=AUTH)
    assert resp.status_code == 204

    # not in list anymore
    resp = await app_client.get("/api/v1/users/", headers=AUTH)
    assert uid not in [u["id"] for u in resp.json()["items"]]

    # 404 on direct get
    resp = await app_client.get(f"/api/v1/users/{uid}", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_self(app_client, tenant_owner):
    resp = await app_client.delete(
        f"/api/v1/users/{tenant_owner['user_id']}", headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_username_rejected(app_client):
    resp = await app_client.post("/api/v1/users/", json=_create_payload("dup"), headers=AUTH)
    assert resp.status_code == 201
    resp = await app_client.post("/api/v1/users/", json=_create_payload("dup"), headers=AUTH)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_db_enforces_username_uniqueness(db_session):
    """The partial unique index must reject a duplicate at the DB layer too.

    The application's check-then-insert is racy under concurrency; the index is
    the real guarantee. Drive a raw insert to confirm IntegrityError fires
    (without relying on UserService's pre-check).
    """
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.models.tenant import User

    async def _add(name: str):
        db_session.add(
            User(id=uuid.uuid4().hex, username=name, email=f"{name}@x.com", status="active")
        )
        await db_session.flush()

    await _add("uniq_user")
    with pytest.raises(IntegrityError):
        await _add("uniq_user")  # same username, different id -> blocked by index
    await db_session.rollback()


@pytest.mark.asyncio
async def test_soft_deleted_username_can_be_reused(app_client):
    """The unique index is PARTIAL (is_deleted=false), so once a user is
    soft-deleted their username is free for a new account — matching the
    is_deleted filter every lookup already applies."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("reuse"), headers=AUTH)
    ).json()
    await app_client.delete(f"/api/v1/users/{created['id']}", headers=AUTH)

    # Recreating the same username must now succeed (not 400 duplicate).
    resp = await app_client.post("/api/v1/users/", json=_create_payload("reuse"), headers=AUTH)
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_statistics(app_client):
    await app_client.post("/api/v1/users/", json=_create_payload("stat1"), headers=AUTH)
    await app_client.post("/api/v1/users/", json=_create_payload("stat2"), headers=AUTH)
    resp = await app_client.get("/api/v1/users/statistics", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert body["active"] >= 2
    assert body["new_this_month"] >= 2


# ===================== super admin cross-tenant tests =====================

SA_AUTH = {"Authorization": "Bearer fake"}


@pytest.mark.asyncio
async def test_super_admin_sees_all_users_across_tenants(super_admin_client):
    """Super admin should see users from ALL tenants, not just their own."""
    resp = await super_admin_client.get("/api/v1/users/?limit=20", headers=SA_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    # Should see the owner (main tenant) + cross-user (other tenant).
    emails = {u["email"] for u in body["items"]}
    assert "owner@example.com" in emails
    assert "cross@example.com" in emails
    # Each user should carry tenant fields; cross-tenant users resolve a name.
    by_email = {u["email"]: u for u in body["items"]}
    assert by_email["owner@example.com"]["tenant_name"] == "Test Tenant"
    assert by_email["cross@example.com"]["tenant_name"] == "Other Tenant"


@pytest.mark.asyncio
async def test_super_admin_get_user_other_tenant(super_admin_client):
    """Super admin can GET a user who belongs to a different tenant."""
    resp = await super_admin_client.get("/api/v1/users/cross-user", headers=SA_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "cross@example.com"
    assert body["tenant_name"] == "Other Tenant"


@pytest.mark.asyncio
async def test_super_admin_delete_cross_tenant_user(super_admin_client):
    """Super admin can soft-delete a user from another tenant (global delete).

    This exercises the full cross-tenant write path: the super admin sits in
    "Test Tenant" but deletes "cross-user" who belongs to "Other Tenant".
    """
    resp = await super_admin_client.delete(
        "/api/v1/users/cross-user", headers=SA_AUTH
    )
    assert resp.status_code == 204, resp.text

    # Globally soft-deleted: gone from the super-admin list view...
    lst = await super_admin_client.get("/api/v1/users/?limit=20", headers=SA_AUTH)
    emails = {u["email"] for u in lst.json()["items"]}
    assert "cross@example.com" not in emails

    # ...and a direct GET now 404s.
    get = await super_admin_client.get("/api/v1/users/cross-user", headers=SA_AUTH)
    assert get.status_code == 404


@pytest.mark.asyncio
async def test_super_admin_update_cross_tenant_user(super_admin_client):
    """Super admin can update a user's profile across tenants.

    The super admin edits real_name on "cross-user" (Other Tenant). Role change
    is intentionally ignored for super admins (cross-tenant membership is
    managed via the members page).
    """
    resp = await super_admin_client.put(
        "/api/v1/users/cross-user",
        json={"real_name": "Edited By Super Admin", "role": "admin"},
        headers=SA_AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["real_name"] == "Edited By Super Admin"
    assert body["email"] == "cross@example.com"
    assert body["tenant_name"] == "Other Tenant"


@pytest.mark.asyncio
async def test_super_admin_change_status_cross_tenant(super_admin_client):
    """Super admin can lock a user in another tenant."""
    resp = await super_admin_client.patch(
        "/api/v1/users/cross-user/status",
        json={"status": "locked"},
        headers=SA_AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "locked"


@pytest.mark.asyncio
async def test_regular_user_does_not_see_other_tenant(app_client, db_session, test_env):
    """A non-super-admin user must only see users in their own tenant.

    Seed a second tenant with a user, then verify the regular app_client
    (scoped to the first tenant) cannot see that user.
    """
    from app.models.tenant import Tenant, User, UserTenant

    async with test_env.factory() as session:
        other_tid = "tnt-hidden"
        session.add(Tenant(id=other_tid, name="Hidden Tenant"))
        session.add(User(id="hidden-user", email="hidden@example.com", status="active"))
        session.add(UserTenant(user_id="hidden-user", tenant_id=other_tid, role="member"))
        await session.commit()

    resp = await app_client.get("/api/v1/users/?limit=20", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    ids = {u["id"] for u in body["items"]}
    assert "hidden-user" not in ids, "Regular user must not see users from other tenants"


@pytest.mark.asyncio
async def test_super_admin_me_returns_platform_role(super_admin_client):
    """The /auth/me endpoint should reflect super_admin platform_role."""
    resp = await super_admin_client.get("/api/v1/auth/me", headers=SA_AUTH)
    assert resp.status_code == 200
    assert resp.json()["platform_role"] == "super_admin"


@pytest.mark.asyncio
async def test_super_admin_statistics_match_list(super_admin_client):
    """Super admin stat cards must count users across ALL tenants, and the
    statistics total must equal the list pagination total (same data source).

    Before the fix, statistics() ignored platform_role and counted only the
    caller's tenant, so the cards showed a smaller number than the list.
    """
    stats = (await super_admin_client.get(
        "/api/v1/users/statistics", headers=SA_AUTH
    )).json()
    lst = (await super_admin_client.get(
        "/api/v1/users/?limit=50", headers=SA_AUTH
    )).json()

    # The cross-tenant user must be counted (proves statistics is cross-tenant).
    emails = {u["email"] for u in lst["items"]}
    assert "cross@example.com" in emails
    assert stats["total"] == lst["total"]
    # status breakdowns should sum to the total (active + inactive + locked).
    assert stats["active"] + stats["inactive"] + stats["locked"] == stats["total"]


# ----------------------------------------------------------- update branches


@pytest.mark.asyncio
async def test_update_user_email(app_client):
    """PUT can change a user's email (unique-check branch)."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("emailupd"), headers=AUTH)
    ).json()
    resp = await app_client.put(
        f"/api/v1/users/{created['id']}",
        json={"email": "new_email@example.com"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "new_email@example.com"


@pytest.mark.asyncio
async def test_update_user_duplicate_email_rejected(app_client):
    """Updating to an email that already exists → 400."""
    await app_client.post("/api/v1/users/", json=_create_payload("emailA"), headers=AUTH)
    created_b = (
        await app_client.post("/api/v1/users/", json=_create_payload("emailB"), headers=AUTH)
    ).json()
    resp = await app_client.put(
        f"/api/v1/users/{created_b['id']}",
        json={"email": "user_emailA@example.com"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_user_username(app_client):
    """PUT can change a user's username (unique-check branch)."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("unameupd"), headers=AUTH)
    ).json()
    resp = await app_client.put(
        f"/api/v1/users/{created['id']}",
        json={"username": "user_renamed"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "user_renamed"


@pytest.mark.asyncio
async def test_update_user_not_found_404(app_client):
    """Updating a nonexistent user → 404."""
    resp = await app_client.put(
        "/api/v1/users/nonexistent-id",
        json={"real_name": "X"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_user_invalid_status_400(app_client):
    """Updating status to an invalid value → 400 (BizError)."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("badstatus"), headers=AUTH)
    ).json()
    resp = await app_client.put(
        f"/api/v1/users/{created['id']}",
        json={"status": "bogus"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_user_display_name_and_phone(app_client):
    """PUT can update display_name + phone + avatar fields."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("fields"), headers=AUTH)
    ).json()
    resp = await app_client.put(
        f"/api/v1/users/{created['id']}",
        json={"display_name": "Display X", "phone": "13900001111", "avatar": "/avatars/x.png"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Display X"
    assert body["phone"] == "13900001111"


# ------------------------------------------------------- create validation


@pytest.mark.asyncio
async def test_create_user_with_organization_ids(app_client):
    """Creating a user with valid organization_ids links them."""
    # First create an org to link.
    org = (
        await app_client.post(
            "/api/v1/organizations/",
            json={"name": "Eng", "code": "eng"},
            headers=AUTH,
        )
    ).json()
    payload = _create_payload("orguser")
    payload["organization_ids"] = [org["id"]]
    resp = await app_client.post("/api/v1/users/", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    org_ids = [o["id"] for o in resp.json().get("organizations", [])]
    assert org["id"] in org_ids


@pytest.mark.asyncio
async def test_create_user_with_invalid_org_ids_400(app_client):
    """Creating a user with nonexistent organization_ids → 400 (BizError)."""
    payload = _create_payload("badorg")
    payload["organization_ids"] = ["nonexistent-org-id"]
    resp = await app_client.post("/api/v1/users/", json=payload, headers=AUTH)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_user_invalid_status_400(app_client):
    """Creating a user with an invalid status → 400 (BizError)."""
    payload = _create_payload("invalid")
    payload["status"] = "bogus"
    resp = await app_client.post("/api/v1/users/", json=payload, headers=AUTH)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_user_duplicate_email_rejected(app_client):
    """Two users with the same email → second is 400."""
    payload_a = _create_payload("dupemailA")
    payload_a["email"] = "shared@example.com"
    resp = await app_client.post("/api/v1/users/", json=payload_a, headers=AUTH)
    assert resp.status_code == 201
    payload_b = _create_payload("dupemailB")
    payload_b["email"] = "shared@example.com"
    resp = await app_client.post("/api/v1/users/", json=payload_b, headers=AUTH)
    assert resp.status_code == 400


# ------------------------------------------------------- status / password


@pytest.mark.asyncio
async def test_change_status_not_found_404(app_client):
    """Changing status of a nonexistent user → 404."""
    resp = await app_client.patch(
        "/api/v1/users/nonexistent-id/status",
        json={"status": "locked"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_change_status_invalid_400(app_client):
    """Changing to an invalid status → 400."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("statbad"), headers=AUTH)
    ).json()
    resp = await app_client.patch(
        f"/api/v1/users/{created['id']}/status",
        json={"status": "bogus"},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_not_found_404(app_client):
    """Resetting password for a nonexistent user → 404."""
    resp = await app_client.post(
        "/api/v1/users/nonexistent-id/reset-password",
        json={"new_password": "NewPass789!"},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_change_status_to_inactive(app_client):
    """Changing status to 'inactive' is a valid transition."""
    created = (
        await app_client.post("/api/v1/users/", json=_create_payload("inact"), headers=AUTH)
    ).json()
    resp = await app_client.patch(
        f"/api/v1/users/{created['id']}/status",
        json={"status": "inactive"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_super_admin_reset_password_cross_tenant(super_admin_client):
    """Super admin can reset a cross-tenant user's password (454-477 branch)."""
    resp = await super_admin_client.post(
        "/api/v1/users/cross-user/reset-password",
        json={"new_password": "SuperReset123!"},
        headers=SA_AUTH,
    )
    assert resp.status_code == 204, resp.text
