"""Password hashing with bcrypt.

We use the ``bcrypt`` library directly (not passlib — passlib's bcrypt backend is
deprecated and passlib itself is unmaintained). All local-account passwords go
through ``hash_password`` on write and ``verify_password`` on login.
"""

from __future__ import annotations

import bcrypt

from app.core.config import settings


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain`` (includes salt + cost)."""
    salt = bcrypt.gensalt(rounds=settings.salt_rounds)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    """Constant-time check of ``plain`` against ``hashed``.

    Returns ``False`` on any failure (wrong password, malformed hash, or
    ``hashed is None``) instead of raising — callers treat both as "denied".
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
