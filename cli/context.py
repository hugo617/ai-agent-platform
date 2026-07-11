"""Shared CLI context type.

Lives in its own module (not ``cli.main``) to avoid a circular import:
``cli.main`` imports the command modules, which need ``GlobalOptions``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GlobalOptions:
    """Resolved global options, shared across subcommands via ``ctx.obj``."""

    json_output: bool
    no_interactive: bool
