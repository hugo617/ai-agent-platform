"""HTTP client for the agenthub CLI.

A thin wrapper over ``httpx.Client`` that injects the Bearer token and maps
non-2xx responses to the CLI's typed exceptions (and thus exit codes). SSE
responses are NOT handled here — the chat command (next task) consumes the raw
stream directly.
"""

from __future__ import annotations

from typing import Any

import httpx

from cli.config import Credentials, require_credentials
from cli.errors import ApiError, AuthError, ForbiddenError


class Client:
    """An authenticated HTTP client targeting one platform base URL."""

    def __init__(self, creds: Credentials, *, timeout: float = 30.0) -> None:
        self.creds = creds
        self._client = httpx.Client(
            base_url=creds.base_url,
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @classmethod
    def from_stored_credentials(cls) -> Client:
        """Build a client from stored/env credentials or raise NotLoggedInError."""
        return cls(require_credentials())

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send a request and map errors to typed CLI exceptions.

        Returns the raw ``httpx.Response`` — callers decide whether to parse
        JSON. Raises ``AuthError`` (401), ``ForbiddenError`` (403), or
        ``ApiError`` (other non-2xx); network failures raise ``ApiError`` too.
        """
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise ApiError(f"网络错误：{e}") from e
        if resp.status_code == 401:
            raise AuthError("token 无效或已过期，请重新 `agenthub login`。")
        if resp.status_code == 403:
            raise ForbiddenError("权限不足：当前 token 的角色无权执行此操作。")
        if resp.status_code >= 400:
            detail = _safe_detail(resp)
            raise ApiError(f"API 错误 ({resp.status_code})：{detail}", exit_code=1)
        return resp

    def get_json(self, path: str, **kwargs: Any) -> Any:
        """GET a JSON path and return the parsed body."""
        return self.request("GET", path, **kwargs).json()


def _safe_detail(resp: httpx.Response) -> str:
    """Extract a human-readable detail from an error response, best-effort."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 - non-JSON error body
        text = resp.text.strip()
        return text[:200] if text else resp.reason_phrase
    if isinstance(body, dict):
        return str(body.get("detail") or body)
    return str(body)[:200]
