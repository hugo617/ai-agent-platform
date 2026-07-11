"""Error-handling decorator for CLI commands.

Wraps a typer command so that ``CliError`` raised inside it is converted to a
``typer.Exit(code=...)`` with the error's mapped exit code, and the message is
echoed to stderr. This is the one reliable way to map custom exit codes across
typer's command/group invocation (typer's ClickException propagation is
inconsistent in CliRunner and standalone mode alike).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

import typer

from cli.errors import CliError


def handle_errors(fn: Callable) -> Callable:
    """Catch CliError and map it to typer.Exit with the right exit code."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except CliError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=e.exit_code) from e

    return wrapper
