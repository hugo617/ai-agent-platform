"""Field-level encryption for secrets stored in the DB (e.g. LLM API keys).

Uses Fernet (symmetric, authenticated) so ciphertexts are tamper-evident. The
key comes from ``settings.field_encryption_key`` — generated once per deploy
(see ``.env.example``) and never rotated without re-encrypting stored values.

Kept deliberately tiny: ``encrypt`` / ``decrypt`` / ``mask_api_key`` are the
only operations. Nothing here touches the network or the DB.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(settings.field_encryption_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return a Fernet token as a string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token produced by :func:`encrypt`.

    Raises ``cryptography.fernet.InvalidToken`` if the key changed or the
    ciphertext was tampered with — callers should treat that as a data error.
    """
    return _fernet().decrypt(ciphertext.encode()).decode()


def mask_api_key(key: str) -> str:
    """Return a masked hint suitable for echoing back to the UI.

    ``sk-abcd1234wxyz`` → ``sk-***wxyz``. Shows only the leading segment (up to
    the first ``-``) and the last 4 characters; the middle is always hidden.
    Keys without a ``-`` separator or shorter than 5 chars are fully masked.
    """
    if len(key) <= 4:
        return "***"
    tail = key[-4:]
    if "-" in key:
        prefix = key.split("-", 1)[0]
        return f"{prefix}-***{tail}"
    return f"***{tail}"
