"""``agenthub whoami`` — show the resolved token identity.

Calls ``GET /api/v1/api-tokens/verify`` and prints who the current token
authenticates as. Default output is human-friendly; ``--json`` prints the raw
identity. Used by Agents to confirm a credential works before other commands.
"""

from __future__ import annotations

import json

import typer

from cli.client import Client
from cli.context import GlobalOptions
from cli.handlers import handle_errors


def register(parent: typer.Typer) -> None:
    @parent.command("whoami")
    @handle_errors
    def whoami(ctx: typer.Context) -> None:
        """显示当前登录身份。"""
        opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)
        with Client.from_stored_credentials() as client:
            body = client.get_json("/api/v1/api-tokens/verify")

        if opts.json_output:
            typer.echo(json.dumps(body, ensure_ascii=False))
        else:
            typer.echo(
                f"user_id:  {body.get('user_id')}\n"
                f"tenant:   {body.get('tenant_id')}\n"
                f"valid:    {body.get('valid')}"
            )
