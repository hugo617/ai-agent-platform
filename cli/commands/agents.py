"""``agenthub agents`` — read-only agent listing and detail.

Usage::

    agenthub agents list [--json]
    agenthub agents get <id> [--json]

A typer sub-app. Default output uses rich tables (human-friendly); ``--json``
emits the raw API payload. Read-only, so naturally idempotent (Agent-Ready
trait #4).
"""

from __future__ import annotations

import json
from typing import Any

import typer

from cli.client import Client
from cli.context import GlobalOptions
from cli.handlers import handle_errors

app = typer.Typer(help="智能体管理（只读）。", no_args_is_help=True)


@app.command("list")
@handle_errors
def list_agents(ctx: typer.Context) -> None:
    """列出当前租户的智能体。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)
    with Client.from_stored_credentials() as client:
        agents = client.get_json("/api/v1/agents/")

    if opts.json_output:
        typer.echo(json.dumps(agents, ensure_ascii=False))
    else:
        _print_agents_table(agents)


@app.command("get")
@handle_errors
def get_agent(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="智能体 ID。"),
) -> None:
    """查看某个智能体的详情。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)
    with Client.from_stored_credentials() as client:
        agent = client.get_json(f"/api/v1/agents/{agent_id}")

    if opts.json_output:
        typer.echo(json.dumps(agent, ensure_ascii=False))
    else:
        _print_agent_detail(agent)


def _print_agents_table(agents: list[dict[str, Any]]) -> None:
    if not agents:
        typer.echo("（暂无智能体）")
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="智能体列表")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("名称", style="white")
        table.add_column("模型", style="green")
        for a in agents:
            table.add_row(str(a.get("id", "")), str(a.get("name", "")), str(a.get("model", "")))
        Console().print(table)
    except ImportError:
        # rich not available — fall back to plain text.
        for a in agents:
            typer.echo(f"{a.get('id')}\t{a.get('name')}\t{a.get('model')}")


def _print_agent_detail(agent: dict[str, Any]) -> None:
    typer.echo(
        f"id:           {agent.get('id')}\n"
        f"name:         {agent.get('name')}\n"
        f"model:        {agent.get('model')}\n"
        f"system_prompt:\n  {(agent.get('system_prompt') or '').replace(chr(10), chr(10) + '  ')}"
    )
