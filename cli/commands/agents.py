"""``agenthub agents`` — agent listing, detail, and CRUD.

Usage::

    # read-only (atoa-cli-core)
    agenthub agents list [--json]
    agenthub agents get <id> [--json]

    # write (this task)
    agenthub agents create --name "助手" [--model deepseek-chat] [--prompt "..."] [--json]
    agenthub agents update <id> [--name "..."] [--model "..."] [--prompt "..."] [--yes]
    agenthub agents delete <id> [--yes]

A typer sub-app. Default output uses rich tables (human-friendly); ``--json``
emits the raw API payload. Read-only commands are naturally idempotent; write
commands prompt for confirmation (``update``/``delete``) unless ``--yes`` is
passed, which ``--no-interactive`` implies automatically.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from cli.client import Client
from cli.context import GlobalOptions
from cli.handlers import handle_errors

app = typer.Typer(help="智能体管理。", no_args_is_help=True)


def _should_skip_confirm(opts: GlobalOptions, yes: bool) -> bool:
    """Return True if a destructive op should skip its confirmation prompt."""
    return yes or opts.no_interactive


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


@app.command("create")
@handle_errors
def create_agent(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="智能体名称。"),
    model: str | None = typer.Option(
        None, "--model", help="模型(如 deepseek-chat);不传则用平台默认。"
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", help="系统提示词(system_prompt)。"
    ),
) -> None:
    """创建一个新智能体(非破坏性,无需确认)。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)
    body: dict[str, Any] = {"name": name}
    if model is not None:
        body["model"] = model
    if prompt is not None:
        body["system_prompt"] = prompt

    with Client.from_stored_credentials() as client:
        agent = client.request("POST", "/api/v1/agents/", json=body).json()

    if opts.json_output:
        typer.echo(json.dumps(agent, ensure_ascii=False))
    else:
        typer.echo(
            f"✓ 已创建智能体 {agent.get('id')}（name={agent.get('name')}，"
            f"model={agent.get('model')}）"
        )


@app.command("update")
@handle_errors
def update_agent(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="智能体 ID。"),
    name: str | None = typer.Option(None, "--name", help="新名称。"),
    model: str | None = typer.Option(None, "--model", help="新模型。"),
    prompt: str | None = typer.Option(None, "--prompt", help="新系统提示词。"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示。"),
) -> None:
    """修改智能体配置(只传要改的字段,PATCH 语义)。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if model is not None:
        body["model"] = model
    if prompt is not None:
        body["system_prompt"] = prompt
    if not body:
        raise typer.BadParameter("至少指定 --name / --model / --prompt 中的一个。")

    if not _should_skip_confirm(opts, yes):
        fields = ", ".join(body.keys())
        if not typer.confirm(
            f"确定更新智能体 {agent_id}(字段: {fields})?", default=False
        ):
            raise typer.Exit(code=0)

    with Client.from_stored_credentials() as client:
        agent = client.request("PATCH", f"/api/v1/agents/{agent_id}", json=body).json()

    if opts.json_output:
        typer.echo(json.dumps(agent, ensure_ascii=False))
    else:
        typer.echo(f"✓ 已更新智能体 {agent.get('id')}")


@app.command("delete")
@handle_errors
def delete_agent(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="要删除的智能体 ID。"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示直接删除。"),
) -> None:
    """删除一个智能体。"""
    opts: GlobalOptions = ctx.obj or GlobalOptions(json_output=False, no_interactive=False)
    if not _should_skip_confirm(opts, yes):
        if not typer.confirm(f"确定删除智能体 {agent_id}?", default=False):
            raise typer.Exit(code=0)

    with Client.from_stored_credentials() as client:
        client.request("DELETE", f"/api/v1/agents/{agent_id}")

    if opts.json_output:
        typer.echo(
            json.dumps({"deleted": True, "agent_id": agent_id}, ensure_ascii=False)
        )
    else:
        typer.echo(f"✓ 已删除智能体 {agent_id}")


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
