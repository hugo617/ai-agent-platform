"""LLM config (settings) API + crypto tests.

Covers:
  - crypto round-trip + mask format (pure-function unit tests)
  - platform-level config: super_admin writes/reads; non-super-admin → 403
  - tenant-level config: owner/admin write/read; member → 403
  - get_effective fallback chain (tenant > platform > env) via direct DB rows
  - API key never leaks: GET returns only the masked hint, never plaintext/cipher
  - PUT with empty api_key keeps the stored key
  - cross-tenant isolation: tenant A cannot read tenant B's config
  - GET /settings/models returns the effective available_models list
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# --------------------------------------------------------------- crypto unit


def test_crypto_roundtrip():
    from app.core import crypto

    for plaintext in ["sk-test-123", "a", ""]:
        ct = crypto.encrypt(plaintext)
        assert ct != plaintext  # actually encrypted
        assert crypto.decrypt(ct) == plaintext


def test_mask_api_key_format():
    from app.core.crypto import mask_api_key

    assert mask_api_key("sk-abcd1234wxyz") == "sk-***wxyz"
    assert mask_api_key("abcd1234wxyz") == "***wxyz"  # no separator
    # Short keys hide everything.
    assert mask_api_key("ab") == "***"


# --------------------------------------------------- platform-level (super admin)


@pytest.mark.asyncio
async def test_super_admin_can_write_and_read_platform_config(super_admin_client):
    """super_admin PUT then GET platform config; key comes back masked."""
    put = await super_admin_client.put(
        "/api/v1/settings/llm/platform",
        json={
            "api_key": "sk-platform-secret-9999",
            "base_url": "https://api.deepseek.com",
            "default_model": "deepseek-chat",
            "available_models": ["deepseek-chat", "deepseek-reasoner"],
        },
        headers=AUTH,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["default_model"] == "deepseek-chat"
    assert body["available_models"] == ["deepseek-chat", "deepseek-reasoner"]
    assert body["tenant_id"] is None
    # Masked hint, never the plaintext or ciphertext.
    assert body["api_key_hint"].endswith("9999")
    assert "sk-platform-secret-9999" not in put.text

    got = await super_admin_client.get("/api/v1/settings/llm/platform", headers=AUTH)
    assert got.status_code == 200
    assert got.json()["api_key_hint"].endswith("9999")


@pytest.mark.asyncio
async def test_non_super_admin_cannot_access_platform_config(app_client):
    """A plain tenant owner (no platform_role) → 403 on platform endpoints."""
    put = await app_client.put(
        "/api/v1/settings/llm/platform",
        json={"api_key": "sk-x", "base_url": "u", "default_model": "m"},
        headers=AUTH,
    )
    assert put.status_code == 403

    got = await app_client.get("/api/v1/settings/llm/platform", headers=AUTH)
    assert got.status_code == 403


# --------------------------------------------------- tenant-level (owner/admin)


@pytest.mark.asyncio
async def test_owner_can_write_and_read_tenant_config(app_client):
    put = await app_client.put(
        "/api/v1/settings/llm/tenant",
        json={
            "api_key": "sk-tenant-secret-abcd",
            "base_url": "https://api.deepseek.com",
            "default_model": "deepseek-reasoner",
            "available_models": ["deepseek-chat", "deepseek-reasoner"],
        },
        headers=AUTH,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["default_model"] == "deepseek-reasoner"
    assert body["tenant_id"] is not None
    assert body["api_key_hint"].endswith("abcd")

    got = await app_client.get("/api/v1/settings/llm/tenant", headers=AUTH)
    assert got.status_code == 200
    assert got.json()["default_model"] == "deepseek-reasoner"


@pytest.mark.asyncio
async def test_member_cannot_write_tenant_config(member_client):
    """member lacks settings:update → 403."""
    put = await member_client.put(
        "/api/v1/settings/llm/tenant",
        json={"api_key": "sk-x", "base_url": "u", "default_model": "m"},
        headers=AUTH,
    )
    assert put.status_code == 403


@pytest.mark.asyncio
async def test_put_empty_api_key_keeps_stored_key(app_client):
    """A second PUT with no api_key must not wipe the stored key."""
    await app_client.put(
        "/api/v1/settings/llm/tenant",
        json={"api_key": "sk-keep-me-1234", "base_url": "https://a", "default_model": "m1"},
        headers=AUTH,
    )
    first_hint = (
        await app_client.get("/api/v1/settings/llm/tenant", headers=AUTH)
    ).json()["api_key_hint"]
    assert first_hint.endswith("1234")

    # Edit only the model, omit api_key entirely.
    put2 = await app_client.put(
        "/api/v1/settings/llm/tenant",
        json={"default_model": "m2"},
        headers=AUTH,
    )
    assert put2.status_code == 200
    body2 = put2.json()
    assert body2["default_model"] == "m2"
    # Hint unchanged → the stored key was preserved.
    assert body2["api_key_hint"].endswith("1234")


# --------------------------------------------------- get_effective fallback


@pytest.mark.asyncio
async def test_effective_uses_tenant_over_platform(app_client, db_session):
    """When both tenant and platform rows exist, tenant wins."""
    from app.core import crypto
    from app.models.llm_config import LlmConfig

    # Platform row.
    db_session.add(
        LlmConfig(
            tenant_id=None,
            api_key_encrypted=crypto.encrypt("sk-platform"),
            api_key_hint="sk-***form",
            base_url="https://platform.example",
            default_model="platform-model",
            available_models=["platform-model"],
        )
    )
    # Tenant row (for the test's tenant).
    tenant_id = (
        await app_client.get("/api/v1/auth/me", headers=AUTH)
    ).json()["tenant_id"]
    db_session.add(
        LlmConfig(
            tenant_id=tenant_id,
            api_key_encrypted=crypto.encrypt("sk-tenant"),
            api_key_hint="sk-***nant",
            base_url="https://tenant.example",
            default_model="tenant-model",
            available_models=["tenant-model"],
        )
    )
    await db_session.commit()

    from app.services.llm_config_service import llm_config_service

    eff = await llm_config_service.get_effective(db_session, tenant_id)
    assert eff.default_model == "tenant-model"
    assert eff.api_key == "sk-tenant"
    assert eff.base_url == "https://tenant.example"


@pytest.mark.asyncio
async def test_effective_falls_back_to_platform(db_session, tenant_owner):
    """No tenant row → platform row is used."""
    from app.core import crypto
    from app.models.llm_config import LlmConfig
    from app.services.llm_config_service import llm_config_service

    db_session.add(
        LlmConfig(
            tenant_id=None,
            api_key_encrypted=crypto.encrypt("sk-only-platform"),
            api_key_hint="sk-***form",
            base_url="https://platform.example",
            default_model="pmodel",
            available_models=["pmodel"],
        )
    )
    await db_session.commit()

    eff = await llm_config_service.get_effective(db_session, tenant_owner["tenant_id"])
    assert eff.api_key == "sk-only-platform"
    assert eff.default_model == "pmodel"


@pytest.mark.asyncio
async def test_effective_falls_back_to_env(db_session, tenant_owner):
    """No tenant and no platform row → env defaults."""
    from app.core.config import settings
    from app.services.llm_config_service import llm_config_service

    eff = await llm_config_service.get_effective(db_session, tenant_owner["tenant_id"])
    # The env-fallback branch reads settings (OPENAI_API_KEY/BASE_URL/MODEL).
    # Assert against settings.* — NOT a hardcoded model name — so the test
    # holds whether the operator configures deepseek-chat, deepseek-v4-flash,
    # or any other OpenAI-compatible model in their .env.
    assert eff.api_key == settings.openai_api_key
    assert eff.base_url == settings.openai_base_url
    assert eff.default_model == settings.openai_model
    assert eff.available_models == [settings.openai_model]


# --------------------------------------------------- cross-tenant isolation


@pytest.mark.asyncio
async def test_tenant_cannot_see_other_tenant_config(app_client, db_session):
    """A tenant-level config in tenant B is invisible from tenant A."""
    from app.models.llm_config import LlmConfig

    db_session.add(
        LlmConfig(
            tenant_id="tnt-other-secret",
            api_key_encrypted="enc",
            api_key_hint="sk-***xxxx",
            base_url="https://other.example",
            default_model="secret-model",
            available_models=["secret-model"],
        )
    )
    await db_session.commit()

    # The caller's tenant (owner) has no row → GET returns None.
    got = await app_client.get("/api/v1/settings/llm/tenant", headers=AUTH)
    assert got.status_code == 200
    assert got.json() is None


# --------------------------------------------------- model list endpoint


@pytest.mark.asyncio
async def test_models_endpoint_returns_effective_list(app_client):
    """GET /settings/models returns the effective available_models."""
    # Seed a tenant config so the list is deterministic.
    await app_client.put(
        "/api/v1/settings/llm/tenant",
        json={
            "api_key": "sk-m",
            "base_url": "https://api.deepseek.com",
            "default_model": "deepseek-chat",
            "available_models": ["deepseek-chat", "deepseek-reasoner"],
        },
        headers=AUTH,
    )
    resp = await app_client.get("/api/v1/settings/models", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == ["deepseek-chat", "deepseek-reasoner"]
