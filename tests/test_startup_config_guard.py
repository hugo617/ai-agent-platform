"""Startup config guards (config-startup-guard slice 01).

Three same-domain guards, one file:

① AND-gated conditional registration of the three dev endpoints
   (/oidc/jwks, /dev/token, /dev/bootstrap): registered only when
   DEV_AUTH_ENABLED=true AND APP_ENV=development. Default: the routes (and
   their OpenAPI entries) do not exist at all. Open-state cases must build
   their own ``create_app()`` AFTER monkeypatching the settings singleton —
   conftest's app/client fixtures instantiate create_app at fixture setup,
   before the test body runs (plan §4.8).
② ``_secrets_not_default`` validator extension: outside development/testing
   a placeholder OPENAI_API_KEY is rejected, and a placeholder
   EMBEDDING_API_KEY is rejected unless EMBEDDING_BASE_URL targets a local
   (loopback) provider. Constructor kwargs are used for every
   validator-relevant field so the cases are deterministic against env vars
   set by conftest (JWT_SECRET=test-key, OPENAI_API_KEY=test-key, ...).
③ ``init_scheduler`` emits a WARNING (naming SCHEDULER_ENABLED + both jobs)
   when disabled outside testing; stays debug-silent in testing.
"""

import logging

import httpx
import jwt as pyjwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app

DEV_PATHS = ("/oidc/jwks", "/dev/token", "/dev/bootstrap")


def _guarded_settings(**overrides) -> Settings:
    """Deterministic Settings kwargs base for validator tests.

    Every field the ``_secrets_not_default`` validator reads is passed
    explicitly so conftest/env values can never leak in (init kwargs beat
    env vars and .env in pydantic-settings priority).
    """
    base: dict = dict(
        app_env="production",
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="real-jwt-secret",
        field_encryption_key="Z2VuZXJhdGVkLWZlcm5ldC1rZXktbm90LWRlZmF1bHQ=",
        openai_api_key="sk-real-key",
        embedding_api_key="sk-real-key",
        embedding_base_url="http://localhost:11434/v1",
    )
    base.update(overrides)
    return Settings(**base)


# --------------------------------------------------------------------- ①
def _openapi_paths(app) -> set:
    return set(app.openapi()["paths"])


def _patch_dev_gate(monkeypatch, *, dev_auth_enabled: bool, app_env: str) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "dev_auth_enabled", dev_auth_enabled)
    monkeypatch.setattr(settings, "app_env", app_env)


def test_dev_endpoints_absent_when_gate_closed(monkeypatch):
    """Closed gate (dev_auth_enabled=False, the code default; pinned
    explicitly so a developer's .env DEV_AUTH_ENABLED=true can't leak in):
    the three dev endpoints are not registered."""
    _patch_dev_gate(monkeypatch, dev_auth_enabled=False, app_env="production")
    app = create_app()
    paths = _openapi_paths(app)
    for path in DEV_PATHS:
        assert path not in paths


async def test_dev_token_404_when_gate_closed():
    """Default-off app: POST /dev/token falls through to the router 404."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/dev/token", json={})
    assert resp.status_code == 404


def test_dev_endpoints_registered_when_enabled_and_development(monkeypatch):
    _patch_dev_gate(monkeypatch, dev_auth_enabled=True, app_env="development")
    app = create_app()
    paths = _openapi_paths(app)
    for path in DEV_PATHS:
        assert path in paths, f"{path} should be registered when the gate is open"


async def test_dev_token_mints_jwt_with_platform_role_claim(monkeypatch):
    _patch_dev_gate(monkeypatch, dev_auth_enabled=True, app_env="development")
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/dev/token", json={"sub": "dev-user", "platform_role": "super_admin"}
        )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    from app.core.config import settings as app_settings
    from app.core.dev_keys import get_dev_keys

    claims = pyjwt.decode(
        token,
        get_dev_keys().public_pem,
        algorithms=["RS256"],
        audience=app_settings.logto_audience,
    )
    assert claims["platform_role"] == "super_admin"
    assert claims["sub"] == "dev-user"


async def test_jwks_serves_jwks_when_gate_open(monkeypatch):
    _patch_dev_gate(monkeypatch, dev_auth_enabled=True, app_env="development")
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/oidc/jwks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["keys"][0]["kty"] == "RSA"
    assert body["keys"][0]["kid"] == "aap-dev-key"


def test_switch_alone_does_not_open_in_production(monkeypatch):
    """AND semantics: DEV_AUTH_ENABLED=true is not enough outside development."""
    _patch_dev_gate(monkeypatch, dev_auth_enabled=True, app_env="production")
    app = create_app()
    paths = _openapi_paths(app)
    for path in DEV_PATHS:
        assert path not in paths


def test_development_alone_does_not_open_the_gate(monkeypatch):
    """Reverse side of the AND: APP_ENV=development alone stays closed."""
    _patch_dev_gate(monkeypatch, dev_auth_enabled=False, app_env="development")
    app = create_app()
    paths = _openapi_paths(app)
    for path in DEV_PATHS:
        assert path not in paths


# --------------------------------------------------------------------- ②
def test_production_with_default_jwt_secret_rejected():
    """Existing jwt branch (was previously untested) — first error wins."""
    with pytest.raises(ValidationError) as exc_info:
        _guarded_settings(jwt_secret="change-me-in-production")
    assert "JWT_SECRET" in str(exc_info.value)


def test_production_with_placeholder_openai_key_rejected():
    with pytest.raises(ValidationError) as exc_info:
        _guarded_settings(openai_api_key="sk-replace-me")
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_production_local_embedding_base_url_exempt_from_key_check():
    """Local Ollama (loopback) has no auth — placeholder key is fine."""
    settings = _guarded_settings(
        embedding_api_key="sk-replace-me",
        embedding_base_url="http://localhost:11434/v1",
    )
    assert settings.embedding_api_key == "sk-replace-me"


def test_production_remote_embedding_base_url_requires_real_key():
    with pytest.raises(ValidationError) as exc_info:
        _guarded_settings(
            embedding_api_key="sk-replace-me",
            embedding_base_url="https://api.openai.com/v1",
        )
    assert "EMBEDDING_API_KEY" in str(exc_info.value)


def test_dev_and_testing_whitelisted_with_all_placeholders():
    for env in ("development", "testing"):
        settings = _guarded_settings(
            app_env=env,
            jwt_secret="change-me-in-production",
            field_encryption_key="UxCQS2ohSvdIRjZfiNyCi5uWoy8FLLiIXonkf28M4r8=",
            openai_api_key="sk-replace-me",
            embedding_api_key="sk-replace-me",
            embedding_base_url="https://api.openai.com/v1",
        )
        assert settings.app_env == env


# --------------------------------------------------------------------- ③
def test_init_scheduler_warns_when_disabled_outside_testing(
    monkeypatch, caplog
):
    from app.core import scheduler as scheduler_mod
    from app.core.config import settings

    monkeypatch.setattr(scheduler_mod, "_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "app_env", "production")

    with caplog.at_level(
        logging.WARNING, logger="app.core.scheduler"
    ):
        scheduler_mod.init_scheduler()

    warnings = [
        r for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "SCHEDULER_ENABLED" in msg
    assert "scan_balance_warnings" in msg
    assert "reconcile_billing" in msg


def test_init_scheduler_stays_silent_in_testing(monkeypatch, caplog):
    from app.core import scheduler as scheduler_mod
    from app.core.config import settings

    monkeypatch.setattr(scheduler_mod, "_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "app_env", "testing")

    with caplog.at_level(
        logging.DEBUG, logger="app.core.scheduler"
    ):
        scheduler_mod.init_scheduler()

    assert not [
        r for r in caplog.records if r.levelno >= logging.WARNING
    ]
