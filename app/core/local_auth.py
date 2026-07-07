"""Local JWT minting for username/password login.

Tokens minted here use HS256 with ``iss == "local"`` and are verified by
``app.core.security._verify_local_token``. The claim shape mirrors Logto's
(``sub``, ``tenant_id``, ``email``) so the same ``get_current_user`` pipeline
handles both without branching.

Session persistence (``UserSession`` rows) is done in the auth endpoint, not
here — this module stays free of ORM imports so it can be unit-tested in
isolation and imported from anywhere (including migration bootstrap scripts).
"""

from __future__ import annotations

import time
import uuid

import jwt

from app.core.config import settings

LOCAL_ISSUER = "local"


def create_access_token(
    user_id: str, tenant_id: str, email: str | None = None
) -> tuple[str, str]:
    """Mint a short-lived HS256 access token for a local user.

    Returns ``(token, jti)`` where ``jti`` is the unique token id, also used as
    the ``session_id`` when persisting a ``UserSession`` row. TTL is
    ``ACCESS_TOKEN_TTL_MINUTES``.
    """
    now = int(time.time())
    ttl = settings.access_token_ttl_minutes * 60
    jti = uuid.uuid4().hex
    claims = {
        "iss": LOCAL_ISSUER,
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "iat": now,
        "exp": now + ttl,
        "jti": jti,
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti
