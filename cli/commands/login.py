"""``agenthub login`` — store credentials and verify the token.

Usage::

    agenthub login <token> [--base-url http://localhost:8000]

Stores the token to ``~/.agenthub/credentials`` (mode 0600) and calls
``/api/v1/api-tokens/verify`` to confirm it works before declaring success.
"""

from __future__ import annotations

import json

import httpx
import typer

from cli.config import DEFAULT_BASE_URL, save_credentials
from cli.context import GlobalOptions
from cli.errors import CliError
from cli.handlers import handle_errors


def register(parent: typer.Typer) -> None:
    @parent.command("login")
    @handle_errors
    def login(
        ctx: typer.Context,
        token: str = typer.Argument(..., help="API token（ahp_ 前缀）"),
        base_url: str = typer.Option(
            DEFAULT_BASE_URL, "--base-url", help="平台 API 地址。"
        ),
    ) -> None:
        """登录并保存凭证。"""
        opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)

        # Verify before persisting so a bad token isn't saved. We can't reuse
        # from_stored_credentials (nothing saved yet), so hit verify directly.
        verify_url = f"{base_url.rstrip('/')}/api/v1/api-tokens/verify"
        try:
            resp = httpx.get(
                verify_url, headers={"Authorization": f"Bearer {token}"}, timeout=15.0
            )
        except httpx.HTTPError as e:
            raise CliError(f"无法连接平台：{e}") from e

        if resp.status_code == 401:
            raise CliError("token 无效或已过期，登录失败。", exit_code=2)
        if resp.status_code >= 400:
            raise CliError(f"验证失败 ({resp.status_code})。", exit_code=1)

        body = resp.json()
        save_credentials(token, base_url)

        result = {
            "logged_in": True,
            "user_id": body.get("user_id"),
            "tenant_id": body.get("tenant_id"),
            "base_url": base_url,
        }
        if opts.json_output:
            typer.echo(json.dumps(result, ensure_ascii=False))
        else:
            typer.echo(
                f"✓ 已登录（user_id={result['user_id']}，tenant={result['tenant_id']}）\n"
                f"  凭证已保存到 ~/.agenthub/credentials"
            )
