"""CLI exceptions and exit-code mapping.

Agent-Ready CLI trait: meaningful exit codes so the calling Agent can branch.
  - 0  success
  - 1  generic error (network, unexpected)
  - 2  auth failure (401 — token invalid/expired, or not logged in)
  - 3  permission failure (403)

``CliError`` extends ``click.ClickException`` (for typer/click integration).
Exit-code mapping is done by the ``@handle_errors`` decorator in
``cli/handlers.py``, which catches ``CliError`` and raises
``typer.Exit(code=exit_code)`` — typer's own ClickException exit-code
propagation proved inconsistent under ``CliRunner``.
"""

from __future__ import annotations

import click


class CliError(click.ClickException):
    """Base for CLI errors that map to a specific exit code.

    ``exit_code`` is honoured by click's exception handling (it reads
    ``self.exit_code`` when rendering the error).
    """

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class NotLoggedInError(CliError):
    """No credentials stored and no AGENTHUB_TOKEN env var."""

    def __init__(self, message: str = "未登录。") -> None:
        super().__init__(message, exit_code=2)


class AuthError(CliError):
    """The server rejected the token (HTTP 401)."""

    def __init__(self, message: str = "认证失败。") -> None:
        super().__init__(message, exit_code=2)


class ForbiddenError(CliError):
    """The token's role lacks the required permission (HTTP 403)."""

    def __init__(self, message: str = "权限不足。") -> None:
        super().__init__(message, exit_code=3)


class ApiError(CliError):
    """A non-auth API error returned by the server (4xx/5xx other than 401/403)."""
