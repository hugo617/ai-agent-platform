"""agenthub CLI entry point.

Builds the top-level ``typer`` app, wires global options (``--json``,
``--no-interactive``), and registers the subcommand groups (``login``,
``whoami``, ``agents``). Installed as the ``agenthub`` console script via
``[project.scripts]`` in pyproject.toml.

Agent-Ready traits implemented here:
  - ``--json``      structured output (Agent trait #1)
  - ``--no-interactive``  skip all prompts (Agent trait #2)
  - pipe detection  when stdout is not a TTY, default to JSON (trait #5)
  - exit codes      each command is wrapped in ``@handle_errors``
    (cli/handlers.py), which catches ``CliError`` and maps its exit_code
    to a ``typer.Exit`` (trait #6)
"""

from __future__ import annotations

import sys

import typer

from cli import commands
from cli.context import GlobalOptions

app = typer.Typer(
    name="agenthub",
    help="agenthub 平台 CLI —— 让 AI Agent 通过命令行操作平台。",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="输出 JSON（结构化，便于 Agent / 管道解析）。",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="非交互模式，跳过所有确认提示（Agent 默认场景）。",
    ),
) -> None:
    """agenthub 平台 CLI。"""
    # Pipe detection (Agent-Ready trait #5): when stdout is not a TTY the human
    # formatting is useless, so default to JSON unless explicitly overridden.
    use_json = json_output or (not sys.stdout.isatty())
    ctx.obj = GlobalOptions(json_output=use_json, no_interactive=no_interactive)


# Register subcommand groups.
app.add_typer(commands.agents.app, name="agents", help="智能体管理。")
# Single-command modules expose a ``register`` helper to add their command.
commands.login.register(app)
commands.whoami.register(app)


def run() -> None:
    """Console-script entry point.

    Each subcommand is wrapped in ``@handle_errors`` (cli/handlers.py), which
    catches ``CliError`` and raises ``typer.Exit(code=...)`` — so this is a thin
    wrapper and custom exit codes (0/1/2/3) propagate reliably.
    """
    app()
