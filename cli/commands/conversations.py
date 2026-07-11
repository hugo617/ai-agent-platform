"""``agenthub conversations`` — conversation history: list, messages, delete.

Usage::

    agenthub conversations list [--json]
    agenthub conversations messages <id> [--json]
    agenthub conversations delete <id> [--yes]

Read/write access to the caller's conversation history. ``list`` and
``messages`` are read-only (idempotent); ``delete`` is destructive and prompts
for confirmation unless ``--yes`` (or ``--no-interactive``, which implies
``--yes``) is given.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from cli.client import Client
from cli.context import GlobalOptions
from cli.handlers import handle_errors

app = typer.Typer(help="会话历史管理。", no_args_is_help=True)


def _should_skip_confirm(opts: GlobalOptions, yes: bool) -> bool:
    """Return True if a destructive op should skip its confirmation prompt."""
    return yes or opts.no_interactive


@app.command("list")
@handle_errors
def list_conversations(ctx: typer.Context) -> None:
    """列出当前用户的会话(按最近活跃排序)。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(
        json_output=False, no_interactive=False
    )
    with Client.from_stored_credentials() as client:
        conversations = client.get_json("/api/v1/conversations/")

    if opts.json_output:
        typer.echo(json.dumps(conversations, ensure_ascii=False))
    else:
        _print_conversations_table(conversations)


@app.command("messages")
@handle_errors
def list_messages(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(..., help="会话 ID。"),
) -> None:
    """查看某个会话的历史消息(按时间升序)。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(
        json_output=False, no_interactive=False
    )
    with Client.from_stored_credentials() as client:
        messages = client.get_json(
            f"/api/v1/conversations/{conversation_id}/messages"
        )

    if opts.json_output:
        typer.echo(json.dumps(messages, ensure_ascii=False))
    else:
        _print_messages_timeline(messages)


@app.command("delete")
@handle_errors
def delete_conversation(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(..., help="要删除的会话 ID。"),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="跳过确认提示直接删除。"
    ),
) -> None:
    """删除一个会话(硬删除,消息随之清除)。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(
        json_output=False, no_interactive=False
    )
    if not _should_skip_confirm(opts, yes):
        if not typer.confirm(f"确定删除会话 {conversation_id}?", default=False):
            raise typer.Exit(code=0)

    with Client.from_stored_credentials() as client:
        client.request("DELETE", f"/api/v1/conversations/{conversation_id}")

    if opts.json_output:
        typer.echo(
            json.dumps(
                {"deleted": True, "conversation_id": conversation_id},
                ensure_ascii=False,
            )
        )
    else:
        typer.echo(f"✓ 已删除会话 {conversation_id}")


def _print_conversations_table(conversations: list[dict[str, Any]]) -> None:
    if not conversations:
        typer.echo("（暂无会话）")
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="会话列表")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Agent", style="white")
        table.add_column("标题", style="white")
        table.add_column("更新时间", style="green")
        for c in conversations:
            table.add_row(
                str(c.get("id", "")),
                str(c.get("agent_id", "")),
                str(c.get("title") or "—"),
                str(c.get("updated_at", "")),
            )
        Console().print(table)
    except ImportError:
        # rich not available — fall back to plain text.
        for c in conversations:
            typer.echo(
                f"{c.get('id')}\t{c.get('agent_id')}\t{c.get('title') or '—'}\t"
                f"{c.get('updated_at')}"
            )


def _print_messages_timeline(messages: list[dict[str, Any]]) -> None:
    if not messages:
        typer.echo("（暂无消息）")
        return
    for m in messages:
        role = m.get("role", "?")
        content = str(m.get("content", ""))
        ts = m.get("created_at", "")
        label = {
            "user": "[user]",
            "assistant": "[assistant]",
        }.get(role, f"[{role}]")
        typer.echo(f"{label} {content}")
        if ts:
            typer.echo(f"       {ts}")
