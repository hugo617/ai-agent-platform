"""Dev-only RSA key pair for signing test JWTs.

This module generates (once, lazily) an RSA key pair and exposes:
  - ``PRIVATE_KEY_PEM`` / ``PUBLIC_KEY_PEM`` for signing/verifying dev tokens.
  - ``PUBLIC_JWK`` for exposing via a tiny JWKS endpoint so the app's own
    JWT verifier (which fetches JWKS from an issuer) can validate dev tokens
    without Logto.

The keys live in memory only — they are regenerated on every process start,
so dev tokens are short-lived and never persist. This is strictly a developer
convenience and is gated behind ``APP_ENV == development``.
"""

import base64
import json
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@dataclass
class DevKeys:
    private_pem: bytes
    public_pem: bytes
    public_jwk: dict
    kid: str


def _b64url_uint(n: int) -> str:
    byte_len = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).rstrip(b"=").decode()


def generate_dev_keys() -> DevKeys:
    """Generate a fresh RSA-2048 key pair + JWK for dev token signing."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()

    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    nums = public.public_numbers()
    kid = "aap-dev-key"
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url_uint(nums.n),
        "e": _b64url_uint(nums.e),
    }
    return DevKeys(
        private_pem=private_pem, public_pem=public_pem, public_jwk=jwk, kid=kid
    )


# Singleton — generated on first import use.
_keys: DevKeys | None = None


def get_dev_keys() -> DevKeys:
    global _keys
    if _keys is None:
        _keys = generate_dev_keys()
    return _keys


def jwks_json() -> str:
    """JWKS document exposing the dev public key, mimicking an OIDC issuer."""
    return json.dumps({"keys": [get_dev_keys().public_jwk]})
