"""``agenthub agents chat`` — SSE streaming chat against a platform agent.

Usage::

    agenthub agents chat --agent <id> "你好" [--conversation-id <id>] [--json]

This is the core AtoA capability: an external Agent drives the platform's
LLM+Agent ability from the command line. The reply is streamed as SSE:

  - ``{"delta": "chunk"}`` — incremental content
  - ``{"error": "msg"}``    — server-side failure
  - ``[DONE]``              — stream complete

Output routing (so the CLI stays pipe-friendly):
  - default (human) mode — each delta is written to **stderr** with flush,
    producing a terminal typewriter effect. stdout stays clean for piping.
  - ``--json`` mode — deltas are accumulated silently and, on ``[DONE]``, the
    full reply is printed to **stdout** as a single JSON object
    ``{"reply": "...", "agent_id": "...", "conversation_id": ...}``.

Note: the SSE frames do not carry the conversation id, so for newly-created
conversations ``conversation_id`` in the JSON output is ``null``. To continue a
conversation, first list conversations (``agenthub conversations list``), grab
the id, then pass ``--conversation-id``. (We deliberately don't change the
backend in this task.)
"""

from __future__ import annotations

import json
import sys

import typer

from cli.client import Client
from cli.context import GlobalOptions
from cli.errors import CliError
from cli.handlers import handle_errors


def register(parent: typer.Typer) -> None:
    @parent.command("chat")
    @handle_errors
    def chat(
        ctx: typer.Context,
        agent_id: str = typer.Option(..., "--agent", help="目标智能体 ID。"),
        message: str = typer.Argument(..., help="要发送的消息。"),
        conversation_id: str | None = typer.Option(
            None, "--conversation-id", help="续接已有会话;不传则后端自动新建。"
        ),
    ) -> None:
        """与智能体对话(SSE 流式输出)。"""
        opts: GlobalOptions = ctx.obj or GlobalOptions(
            json_output=False, no_interactive=False
        )

        body: dict[str, object] = {"agent_id": agent_id, "message": message}
        if conversation_id is not None:
            body["conversation_id"] = conversation_id

        deltas: list[str] = []
        with Client.from_stored_credentials() as client:
            for payload in client.stream_sse("/api/v1/chat/stream", body):
                if payload == "[DONE]":
                    break
                # Payload is a JSON object: {"delta": "..."} or {"error": "..."}.
                try:
                    frame = json.loads(payload)
                except json.JSONDecodeError:
                    # Skip a malformed frame rather than aborting the stream.
                    continue
                if "error" in frame:
                    raise CliError(f"对话出错:{frame['error']}", exit_code=1)
                delta = frame.get("delta")
                if delta is None:
                    continue
                deltas.append(delta)
                if not opts.json_output:
                    # Typewriter to stderr — keep stdout clean for pipes/Agents.
                    sys.stderr.write(delta)
                    sys.stderr.flush()

        reply = "".join(deltas)
        if not opts.json_output:
            # Trailing newline so the shell prompt doesn't hug the reply.
            if reply and not reply.endswith("\n"):
                sys.stderr.write("\n")
                sys.stderr.flush()
        else:
            typer.echo(
                json.dumps(
                    {
                        "reply": reply,
                        "agent_id": agent_id,
                        # SSE frames don't echo the conversation id back, so we
                        # can only report it when the caller already knew it.
                        "conversation_id": conversation_id,
                    },
                    ensure_ascii=False,
                )
            )
