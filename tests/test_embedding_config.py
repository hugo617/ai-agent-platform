"""Embedding config service tests (priority 57).

Mirrors the LLM config test pattern: the service is the sole place "one active
row per scope" is enforced (no DB constraint), and get_effective walks the
tenant > platform > env chain. We exercise the real service against the in-memory
SQLite DB and assert masking / fallback behaviour.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


@pytest.mark.asyncio
async def test_get_effective_falls_back_to_env_when_no_rows(db_session):
    """No platform or tenant row → env defaults (embedding_* settings)."""
    from app.services.embedding_config_service import embedding_config_service

    cfg = await embedding_config_service.get_effective(db_session, "tnt-x")
    assert cfg.api_key  # the env placeholder
    assert cfg.model == "text-embedding-3-small"
    assert cfg.dimension == 1536


@pytest.mark.asyncio
async def test_get_effective_uses_platform_when_no_tenant(db_session):
    from app.core import crypto
    from app.models.embedding_config import EmbeddingConfig
    from app.services.embedding_config_service import embedding_config_service

    db_session.add(
        EmbeddingConfig(
            tenant_id=None,
            api_key_encrypted=crypto.encrypt("sk-platform"),
            api_key_hint=crypto.mask_api_key("sk-platform"),
            base_url="https://api.openai.com",
            model="text-embedding-3-small",
        )
    )
    await db_session.commit()

    cfg = await embedding_config_service.get_effective(db_session, "tnt-x")
    assert cfg.api_key == "sk-platform"
    assert cfg.base_url == "https://api.openai.com"


@pytest.mark.asyncio
async def test_get_effective_prefers_tenant_over_platform(db_session):
    from app.core import crypto
    from app.models.embedding_config import EmbeddingConfig
    from app.services.embedding_config_service import embedding_config_service

    db_session.add(
        EmbeddingConfig(
            tenant_id=None,
            api_key_encrypted=crypto.encrypt("sk-platform"),
            api_key_hint=crypto.mask_api_key("sk-platform"),
            base_url="https://api.openai.com",
            model="text-embedding-3-small",
        )
    )
    db_session.add(
        EmbeddingConfig(
            tenant_id="tnt-1",
            api_key_encrypted=crypto.encrypt("sk-tenant"),
            api_key_hint=crypto.mask_api_key("sk-tenant"),
            base_url="https://custom.embed.local",
            model="bge-m3",
        )
    )
    await db_session.commit()

    cfg = await embedding_config_service.get_effective(db_session, "tnt-1")
    assert cfg.api_key == "sk-tenant"
    assert cfg.model == "bge-m3"


@pytest.mark.asyncio
async def test_upsert_platform_then_update_keeps_key_when_empty(db_session):
    from app.schemas.embedding_config import EmbeddingConfigUpdate
    from app.services.embedding_config_service import embedding_config_service

    created = await embedding_config_service.upsert_platform(
        db_session,
        EmbeddingConfigUpdate(
            api_key="sk-first", base_url="https://a.test", model="m1"
        ),
    )
    assert created.api_key_hint  # masked hint present
    # Update with empty api_key → key unchanged, model updated.
    updated = await embedding_config_service.upsert_platform(
        db_session,
        EmbeddingConfigUpdate(api_key=None, model="m2"),
    )
    assert updated.api_key_hint == created.api_key_hint
    assert updated.model == "m2"


@pytest.mark.asyncio
async def test_read_never_exposes_plaintext_key(db_session):
    from app.core import crypto
    from app.models.embedding_config import EmbeddingConfig
    from app.services.embedding_config_service import embedding_config_service

    db_session.add(
        EmbeddingConfig(
            tenant_id=None,
            api_key_encrypted=crypto.encrypt("sk-secret"),
            api_key_hint=crypto.mask_api_key("sk-secret"),
            base_url="https://a.test",
            model="m",
        )
    )
    await db_session.commit()

    read = await embedding_config_service.get_platform(db_session)
    assert read is not None
    assert "sk-secret" not in read.model_dump_json()
    assert read.api_key_hint  # masked
