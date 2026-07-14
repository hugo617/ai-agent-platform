"""Tenant branding config (white-label) API tests.

Covers:
  - GET returns the config or None when no row exists
  - PUT upserts: creates a row, then updates it
  - permission: owner/admin can PUT; member → 403
  - GET is open to any authenticated member (branding applies to everyone)
  - cross-tenant isolation: tenant B's config is invisible from tenant A
  - theme_color validation: bad format → 422
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


@pytest.mark.asyncio
async def test_get_returns_none_when_no_config(app_client):
    """No row yet → GET returns None (frontend falls back to defaults)."""
    got = await app_client.get("/api/v1/tenant-config", headers=AUTH)
    assert got.status_code == 200
    assert got.json() is None


@pytest.mark.asyncio
async def test_put_then_get_roundtrip(app_client):
    """Owner PUT creates the row; a subsequent GET returns it."""
    put = await app_client.put(
        "/api/v1/tenant-config",
        json={
            "display_name": "我的门店",
            "logo_url": "https://cdn.example.com/logo.png",
            "theme_color": "#3b82f6",
            "login_text": "欢迎使用本系统",
        },
        headers=AUTH,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["display_name"] == "我的门店"
    assert body["logo_url"] == "https://cdn.example.com/logo.png"
    assert body["theme_color"] == "#3b82f6"
    assert body["login_text"] == "欢迎使用本系统"
    assert body["tenant_id"] is not None

    got = await app_client.get("/api/v1/tenant-config", headers=AUTH)
    assert got.status_code == 200
    assert got.json()["display_name"] == "我的门店"


@pytest.mark.asyncio
async def test_put_upserts_existing_row(app_client):
    """A second PUT updates the existing row (no second row created)."""
    await app_client.put(
        "/api/v1/tenant-config",
        json={"display_name": "旧名称", "theme_color": "#111111"},
        headers=AUTH,
    )
    put2 = await app_client.put(
        "/api/v1/tenant-config",
        json={"display_name": "新名称", "theme_color": "#222222"},
        headers=AUTH,
    )
    assert put2.status_code == 200
    body = put2.json()
    assert body["display_name"] == "新名称"
    assert body["theme_color"] == "#222222"

    # Still exactly one row for this tenant (GET returns the latest state).
    got = await app_client.get("/api/v1/tenant-config", headers=AUTH)
    assert got.json()["display_name"] == "新名称"


@pytest.mark.asyncio
async def test_admin_can_update_tenant_config(tenant_admin_client):
    """admin (has settings:update) can PUT the config."""
    put = await tenant_admin_client.put(
        "/api/v1/tenant-config",
        json={"display_name": "Admin Brand"},
        headers=AUTH,
    )
    assert put.status_code == 200, put.text
    assert put.json()["display_name"] == "Admin Brand"


@pytest.mark.asyncio
async def test_member_cannot_update_tenant_config(member_client):
    """member lacks settings:update → 403 on PUT."""
    put = await member_client.put(
        "/api/v1/tenant-config",
        json={"display_name": "Member Brand"},
        headers=AUTH,
    )
    assert put.status_code == 403


@pytest.mark.asyncio
async def test_member_can_read_tenant_config(member_client, db_session):
    """GET is open to any authenticated member (branding applies to everyone).

    Seeds a config in the shared in-memory tenant (db_session and member_client
    back onto the same engine), then a member of that tenant reads it.
    """
    from app.models.tenant_config import TenantConfig

    tenant_id = (
        await member_client.get("/api/v1/auth/me", headers=AUTH)
    ).json()["tenant_id"]
    db_session.add(
        TenantConfig(tenant_id=tenant_id, display_name="Shared Brand")
    )
    await db_session.commit()

    got = await member_client.get("/api/v1/tenant-config", headers=AUTH)
    assert got.status_code == 200
    assert got.json()["display_name"] == "Shared Brand"


@pytest.mark.asyncio
async def test_cross_tenant_isolation(app_client, db_session):
    """A config in tenant B is invisible from the caller's tenant."""
    from app.models.tenant_config import TenantConfig

    db_session.add(
        TenantConfig(
            tenant_id="tnt-other-secret",
            display_name="Other Store",
            theme_color="#999999",
        )
    )
    await db_session.commit()

    # The caller's tenant has no row → GET returns None.
    got = await app_client.get("/api/v1/tenant-config", headers=AUTH)
    assert got.status_code == 200
    assert got.json() is None


@pytest.mark.asyncio
async def test_theme_color_validation(app_client):
    """A malformed theme_color is rejected with 422 (#RRGGBB enforced)."""
    put = await app_client.put(
        "/api/v1/tenant-config",
        json={"theme_color": "not-a-color"},
        headers=AUTH,
    )
    assert put.status_code == 422

    # #RGB (shorthand) is also rejected — only #RRGGBB is accepted.
    put_short = await app_client.put(
        "/api/v1/tenant-config",
        json={"theme_color": "#abc"},
        headers=AUTH,
    )
    assert put_short.status_code == 422

    # A valid #RRGGBB is accepted.
    put_ok = await app_client.put(
        "/api/v1/tenant-config",
        json={"theme_color": "#A1B2C3"},
        headers=AUTH,
    )
    assert put_ok.status_code == 200
    assert put_ok.json()["theme_color"] == "#A1B2C3"
