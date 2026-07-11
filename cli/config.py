"""Credential storage for the agenthub CLI.

Credentials live in ``~/.agenthub/credentials`` as a small JSON file with mode
0600 (owner read/write only). Two environment variables override the file, so
CI/containers can authenticate without a credentials file:

  - ``AGENTHUB_TOKEN``     — the ``ahp_…`` API token
  - ``AGENTHUB_BASE_URL``  — the platform API root (default http://localhost:8000)

Env vars win over the file when both are present (file is for interactive
``agenthub login``; env is for automation).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:8000"
_TOKEN_ENV = "AGENTHUB_TOKEN"
_BASE_URL_ENV = "AGENTHUB_BASE_URL"


@dataclass
class Credentials:
    """Resolved credentials (env vars take precedence over the file)."""

    token: str
    base_url: str

    @property
    def token_prefix(self) -> str:
        """Short masked hint for display (e.g. ``ahp_wxyz…``).

        Reserved for the future ``logout`` / ``tokens list`` commands; not yet
        read by any current command.
        """
        if len(self.token) <= 10:
            return self.token[:4] + "***"
        return self.token[:9] + "…"


def credentials_path() -> Path:
    """``~/.agenthub/credentials`` (directory created on first save)."""
    return Path.home() / ".agenthub" / "credentials"


def load_credentials() -> Credentials | None:
    """Resolve credentials, preferring env vars over the file.

    Returns None if neither env nor file provides a token.
    """
    token = os.environ.get(_TOKEN_ENV)
    base_url = os.environ.get(_BASE_URL_ENV)
    if token:
        return Credentials(token=token, base_url=base_url or DEFAULT_BASE_URL)

    path = credentials_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    token = data.get("token")
    if not token:
        return None
    return Credentials(token=token, base_url=data.get("base_url") or DEFAULT_BASE_URL)


def save_credentials(token: str, base_url: str) -> None:
    """Persist credentials to disk with mode 0600 (owner-only)."""
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write then chmod: create the file restricted even on filesystems that
    # ignore the open mode bits.
    path.write_text(
        json.dumps({"token": token, "base_url": base_url}, indent=2),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def clear_credentials() -> bool:
    """Remove the credentials file. Returns True if something was removed.

    Reserved for the future ``agenthub logout`` command; no current command
    calls it.
    """
    path = credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def require_credentials() -> Credentials:
    """Load credentials or raise NotLoggedInError with a helpful message."""
    from cli.errors import NotLoggedInError

    creds = load_credentials()
    if creds is None:
        raise NotLoggedInError(
            "未登录。请先运行 `agenthub login <token>`，"
            "或设置 AGENTHUB_TOKEN 环境变量。"
        )
    return creds
