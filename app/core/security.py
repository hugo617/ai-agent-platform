"""JWT verification for tokens issued by Logto.

Logto is an OIDC provider. Our API only *verifies* access tokens:
  1. Fetch the signing keys (JWKS) from the Logto issuer.
  2. Validate signature + audience + issuer.
  3. Return the decoded claims.

No login UI lives here — the frontend redirects users to Logto directly.
"""

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings


class TokenError(Exception):
    """Raised when a token is missing, malformed, or invalid."""


_jwks_client: PyJWKClient | None = None
_jwks_fetched_at: float = 0
_JWKS_TTL = 600  # refresh keys at most every 10 minutes


def _jwks_uri() -> str:
    """JWKS endpoint to fetch signing keys from.

    In production this is ``{LOGTO_ISSUER}/jwks``. In development, when the
    issuer points at our own backend (``LOGTO_ISSUER=http://localhost:8000/oidc``),
    we serve the dev key pair at ``/oidc/jwks`` — so the *same* verification
    code path validates both Logto-issued and dev tokens.
    """
    return f"{settings.logto_issuer}/jwks"


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_fetched_at
    now = time.time()
    if _jwks_client is None or now - _jwks_fetched_at > _JWKS_TTL:
        _jwks_client = PyJWKClient(_jwks_uri())
        _jwks_fetched_at = now
    return _jwks_client


async def decode_token(token: str) -> dict[str, Any]:
    """Verify and decode an access token (Logto-issued or dev-minted).

    Returns the JWT claims payload. Raises ``TokenError`` on any failure.
    """
    if not token:
        raise TokenError("missing token")

    # In dev mode the issuer points at our own backend; fetching JWKS over HTTP
    # would deadlock a single-worker uvicorn, so we use the in-memory dev key.
    if settings.app_env == "development" and settings.logto_issuer.startswith("http://localhost:8000"):
        return _verify_with_dev_key(token)

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.logto_audience,
            issuer=settings.logto_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError(f"invalid token: {e}") from e
    except httpx.HTTPError as e:
        raise TokenError(f"cannot reach issuer: {e}") from e


def _verify_with_dev_key(token: str) -> dict[str, Any]:
    """Validate a dev token using the in-memory RSA key pair (no HTTP call)."""
    from app.core.dev_keys import get_dev_keys

    keys = get_dev_keys()
    try:
        payload = jwt.decode(
            token,
            keys.public_pem,
            algorithms=["RS256"],
            audience=settings.logto_audience,
            issuer=settings.logto_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError(f"invalid token: {e}") from e


def extract_subject(claims: dict[str, Any]) -> str:
    """Return the user subject (sub) from claims."""
    sub = claims.get("sub")
    if not sub:
        raise TokenError("token has no subject (sub)")
    return str(sub)


def extract_tenant(claims: dict[str, Any]) -> str | None:
    """Return the tenant id from a custom Logto claim, if present.

    Logto lets you attach custom JWT claims via "Custom JWT" configuration.
    We expect either ``tenant_id`` (custom) or fall back to None, meaning
    the tenant must be resolved from the user→tenant mapping table.
    """
    tenant_id = claims.get("tenant_id")
    return str(tenant_id) if tenant_id else None
