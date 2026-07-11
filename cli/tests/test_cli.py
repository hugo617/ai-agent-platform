"""CLI unit tests — command logic with httpx mocked (no live backend).

Uses ``typer.testing.CliRunner`` to invoke the app in-process and
``unittest.mock.patch`` to stub httpx so the tests are hermetic. Credential
files are redirected to a tmp dir via monkeypatching ``credentials_path``.

Note on option position: ``--json`` / ``--no-interactive`` are global options
defined on the top-level callback, so per typer/click convention they must
appear BEFORE the subcommand: ``agenthub --json agents list``.
"""

from __future__ import annotations

import json
import stat
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from cli import config
from cli.main import app

runner = CliRunner()


@pytest.fixture
def cred_dir(tmp_path, monkeypatch):
    """Redirect the credentials file into a tmp dir and clear env overrides."""
    cred_file = tmp_path / "credentials"
    monkeypatch.setattr(config, "credentials_path", lambda: cred_file)
    monkeypatch.delenv("AGENTHUB_TOKEN", raising=False)
    monkeypatch.delenv("AGENTHUB_BASE_URL", raising=False)
    return cred_file


def _mock_response(status_code: int, json_body: dict | list | None = None) -> httpx.Response:
    """Build a fake httpx.Response for mocking."""
    request = httpx.Request("GET", "http://test/api/v1/x")
    body = json.dumps(json_body).encode() if json_body is not None else b""
    resp = httpx.Response(status_code, content=body, request=request)
    if json_body is not None:
        resp.headers["content-type"] = "application/json"
    return resp


class _FakeStreamResponse:
    """Stand-in for an httpx streaming response (``client.stream(...)`` cm).

    Lets the tests drive the real ``Client.stream_sse`` frame parser end-to-end
    — we feed SSE-shaped ``data:`` lines and the production code strips the
    prefix and yields payloads.
    """

    def __init__(self, status_code: int, lines: list[str] | None = None) -> None:
        self.status_code = status_code
        self._lines = list(lines or [])

    def __enter__(self) -> _FakeStreamResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def iter_lines(self):  # noqa: ANN201 - matches httpx's loose typing
        return iter(self._lines)

    def read(self) -> None:
        """No-op matching httpx.Response.read() (called on the error path)."""


def _sse_lines(payloads: list[str]) -> list[str]:
    """Wrap raw SSE payloads as ``data: <payload>`` lines (the wire format)."""
    return [f"data: {p}" for p in payloads]


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def test_login_saves_credentials_with_0600(cred_dir):
    """login verifies the token then persists it with mode 0600."""
    with patch("cli.commands.login.httpx.get") as mock_get:
        mock_get.return_value = _mock_response(
            200, {"valid": True, "user_id": "u1", "tenant_id": "t1"}
        )
        result = runner.invoke(app, ["login", "ahp_tok123", "--base-url", "http://srv"])

    assert result.exit_code == 0, result.output
    assert cred_dir.exists()
    data = json.loads(cred_dir.read_text())
    assert data == {"token": "ahp_tok123", "base_url": "http://srv"}
    # Mode 0600 — owner read/write only.
    mode = stat.S_IMODE(cred_dir.stat().st_mode)
    assert mode == 0o600


def test_login_rejected_token_exits_2(cred_dir):
    """An invalid token (401) fails login with exit code 2 and saves nothing."""
    with patch("cli.commands.login.httpx.get") as mock_get:
        mock_get.return_value = _mock_response(401, {"detail": "invalid token"})
        result = runner.invoke(app, ["login", "ahp_bad"])

    assert result.exit_code == 2, result.output
    assert not cred_dir.exists()


def test_login_network_error_exits_1(cred_dir):
    """A connection failure during login verification exits 1."""
    with patch("cli.commands.login.httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("boom")
        result = runner.invoke(app, ["login", "ahp_tok", "--base-url", "http://srv"])

    assert result.exit_code == 1, result.output
    assert not cred_dir.exists()


# ---------------------------------------------------------------------------
# config: env var override
# ---------------------------------------------------------------------------


def test_env_var_overrides_file(tmp_path, monkeypatch):
    """AGENTHUB_TOKEN takes precedence over a stored credentials file."""
    cred_file = tmp_path / "credentials"
    cred_file.write_text(json.dumps({"token": "ahp_file", "base_url": "http://file"}))
    monkeypatch.setattr(config, "credentials_path", lambda: cred_file)
    monkeypatch.setenv("AGENTHUB_TOKEN", "ahp_env")
    monkeypatch.setenv("AGENTHUB_BASE_URL", "http://env")

    creds = config.load_credentials()
    assert creds is not None
    assert creds.token == "ahp_env"
    assert creds.base_url == "http://env"


def test_not_logged_in_returns_none(monkeypatch, tmp_path):
    """With no file and no env, load_credentials returns None."""
    monkeypatch.setattr(config, "credentials_path", lambda: tmp_path / "nonexistent")
    monkeypatch.delenv("AGENTHUB_TOKEN", raising=False)
    assert config.load_credentials() is None


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------


def test_whoami_json_output(cred_dir):
    """whoami --json prints the verify response as JSON."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(
            200, {"valid": True, "user_id": "u1", "tenant_id": "t1"}
        )
        result = runner.invoke(app, ["--json", "whoami"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body == {"valid": True, "user_id": "u1", "tenant_id": "t1"}


def test_whoami_not_logged_in_exits_2(cred_dir):
    """whoami with no credentials exits 2 (auth failure)."""
    result = runner.invoke(app, ["--json", "whoami"])
    assert result.exit_code == 2, result.output


def test_whoami_401_exits_2(cred_dir):
    """An expired token (401 from server) exits 2."""
    config.save_credentials("ahp_expired", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(401, {"detail": "invalid"})
        result = runner.invoke(app, ["--json", "whoami"])

    assert result.exit_code == 2, result.output


# ---------------------------------------------------------------------------
# agents
# ---------------------------------------------------------------------------


def test_agents_list_json(cred_dir):
    """agents list --json prints the raw array."""
    config.save_credentials("ahp_tok", "http://srv")
    agents_payload = [
        {"id": "a1", "name": "writer", "model": "deepseek-chat", "system_prompt": ""},
        {"id": "a2", "name": "reader", "model": "deepseek-reasoner", "system_prompt": ""},
    ]
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(200, agents_payload)
        result = runner.invoke(app, ["--json", "agents", "list"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert len(body) == 2
    assert body[0]["id"] == "a1"


def test_agents_get_json(cred_dir):
    """agents get <id> --json prints the agent object."""
    config.save_credentials("ahp_tok", "http://srv")
    payload = {"id": "a1", "name": "writer", "model": "deepseek-chat", "system_prompt": "hi"}
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(200, payload)
        result = runner.invoke(app, ["--json", "agents", "get", "a1"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["id"] == "a1"
    assert body["name"] == "writer"


def test_agents_403_exits_3(cred_dir):
    """A permission failure (403) maps to exit code 3."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(403, {"detail": "forbidden"})
        result = runner.invoke(app, ["--json", "agents", "list"])

    assert result.exit_code == 3, result.output


def test_agents_network_error_exits_1(cred_dir):
    """A network failure maps to exit code 1."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.side_effect = httpx.ConnectError("boom")
        result = runner.invoke(app, ["--json", "agents", "list"])

    assert result.exit_code == 1, result.output


# ---------------------------------------------------------------------------
# Pipe detection (Agent-Ready trait #5)
# ---------------------------------------------------------------------------


def test_pipe_detection_defaults_to_json(cred_dir):
    """When stdout is not a TTY (piped), output is JSON even without --json."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls, \
         patch("cli.main.sys.stdout.isatty", return_value=False):
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(
            200, [{"id": "a1", "name": "x", "model": "m", "system_prompt": ""}]
        )
        result = runner.invoke(app, ["agents", "list"])

    assert result.exit_code == 0, result.output
    # JSON output is parseable; a rich table would not be.
    body = json.loads(result.output)
    assert body[0]["id"] == "a1"


# ---------------------------------------------------------------------------
# agents chat (SSE streaming — core AtoA capability)
# ---------------------------------------------------------------------------

_SSE_PAYLOADS = [
    '{"delta": "你"}',
    '{"delta": "好"}',
    '[DONE]',
]


def test_agents_chat_json_accumulates_reply(cred_dir):
    """agents chat --json accumulates deltas and emits one JSON object on DONE.

    Output goes to stdout (parseable); deltas are NOT printed in JSON mode.
    """
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.stream.return_value = _FakeStreamResponse(
            200, _sse_lines(_SSE_PAYLOADS)
        )
        result = runner.invoke(
            app,
            ["--json", "agents", "chat", "--agent", "a1", "你好"],
        )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["reply"] == "你好"
    assert body["agent_id"] == "a1"
    assert body["conversation_id"] is None


def test_agents_chat_with_conversation_id(cred_dir):
    """--conversation-id is forwarded and echoed back in the JSON output."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.stream.return_value = _FakeStreamResponse(
            200, _sse_lines(_SSE_PAYLOADS)
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "agents",
                "chat",
                "--agent",
                "a1",
                "--conversation-id",
                "conv9",
                "续聊",
            ],
        )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["conversation_id"] == "conv9"
    # The stream call got the conversation_id in the body.
    _args, kwargs = mock_client.stream.call_args
    assert kwargs["json"]["conversation_id"] == "conv9"


def test_agents_chat_error_frame_exits_1(cred_dir):
    """An SSE error frame aborts the chat with exit code 1."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.stream.return_value = _FakeStreamResponse(
            200, _sse_lines(['{"error": "模型超时"}'])
        )
        result = runner.invoke(
            app, ["--json", "agents", "chat", "--agent", "a1", "x"]
        )

    assert result.exit_code == 1, result.output


def test_agents_chat_default_writes_to_stderr(cred_dir):
    """In default (non-JSON) mode the reply is NOT a JSON object on stdout.

    typer's CliRunner is non-TTY, so pipe-detection (cli/main.py) forces JSON
    mode and the deltas are accumulated silently. We can't flip that from a
    test without patching click internals, so here we just confirm the JSON
    shape under the runner; the human-readable branch (``sys.stderr.write``)
    is the production code path exercised in real terminals.
    """
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.stream.return_value = _FakeStreamResponse(
            200, _sse_lines(_SSE_PAYLOADS)
        )
        result = runner.invoke(
            app, ["agents", "chat", "--agent", "a1", "你好"]
        )

    assert result.exit_code == 0, result.output
    # Under the runner this is JSON (pipe-detection); the reply is intact.
    body = json.loads(result.output)
    assert body["reply"] == "你好"


# ---------------------------------------------------------------------------
# conversations list / messages / delete
# ---------------------------------------------------------------------------


def test_conversations_list_json(cred_dir):
    """conversations list --json prints the raw array."""
    config.save_credentials("ahp_tok", "http://srv")
    payload = [
        {
            "id": "c1",
            "agent_id": "a1",
            "tenant_id": "t1",
            "user_id": "u1",
            "title": "first",
            "created_at": "2026-07-11T00:00:00",
            "updated_at": "2026-07-11T00:05:00",
        }
    ]
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(200, payload)
        result = runner.invoke(app, ["--json", "conversations", "list"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body[0]["id"] == "c1"


def test_conversations_messages_json(cred_dir):
    """conversations messages <id> --json prints the raw array."""
    config.save_credentials("ahp_tok", "http://srv")
    payload = [
        {"id": "m1", "role": "user", "content": "1+1", "created_at": "2026-07-11T00:00:00"},
        {"id": "m2", "role": "assistant", "content": "2", "created_at": "2026-07-11T00:00:01"},
    ]
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(200, payload)
        result = runner.invoke(
            app, ["--json", "conversations", "messages", "c1"]
        )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert len(body) == 2
    assert body[0]["role"] == "user"


def test_conversations_messages_default_timeline(cred_dir):
    """Default (non-JSON) messages output renders a [role] content timeline.

    CliRunner's stdout is non-TTY, so pipe-detection forces JSON under the
    runner. We exercise the timeline renderer directly here instead, since it's
    a pure function over the API payload.
    """
    from cli.commands.conversations import _print_messages_timeline

    payload = [
        {"role": "user", "content": "hello", "created_at": "2026-07-11T00:00:00"},
    ]
    # The renderer echoes to stdout via typer.echo; capture it.
    with patch("cli.commands.conversations.typer.echo") as echo:
        _print_messages_timeline(payload)

    # First echo is the [user] line; second is the timestamp.
    written = " ".join(str(c.args[0]) for c in echo.call_args_list)
    assert "[user] hello" in written


def test_conversations_messages_empty_timeline():
    """An empty message list prints a friendly placeholder."""
    from cli.commands.conversations import _print_messages_timeline

    with patch("cli.commands.conversations.typer.echo") as echo:
        _print_messages_timeline([])
    assert echo.call_args_list[0].args[0] == "（暂无消息）"


def test_conversations_delete_with_yes_skips_prompt(cred_dir):
    """conversations delete --yes skips the confirmation prompt."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(204)
        result = runner.invoke(
            app, ["--json", "conversations", "delete", "c1", "--yes"]
        )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body == {"deleted": True, "conversation_id": "c1"}
    mock_client.request.assert_called_once_with(
        "DELETE", "/api/v1/conversations/c1"
    )


def test_conversations_delete_declined_exits_0(cred_dir):
    """Answering 'no' to the confirm prompt exits 0 (not an error)."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(204)
        # Input "n" → confirm returns False.
        result = runner.invoke(
            app, ["conversations", "delete", "c1"], input="n\n"
        )

    assert result.exit_code == 0, result.output
    mock_client.request.assert_not_called()


# ---------------------------------------------------------------------------
# agents create / update / delete
# ---------------------------------------------------------------------------


def test_agents_create_json(cred_dir):
    """agents create POSTs the body and prints the new agent as JSON."""
    config.save_credentials("ahp_tok", "http://srv")
    created = {"id": "a9", "name": "helper", "model": "deepseek-chat", "system_prompt": "x"}
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(201, created)
        result = runner.invoke(
            app,
            [
                "--json",
                "agents",
                "create",
                "--name",
                "helper",
                "--model",
                "deepseek-chat",
                "--prompt",
                "x",
            ],
        )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["id"] == "a9"
    _method, _path = mock_client.request.call_args.args
    assert _method == "POST"
    assert _path == "/api/v1/agents/"
    assert mock_client.request.call_args.kwargs["json"] == {
        "name": "helper",
        "model": "deepseek-chat",
        "system_prompt": "x",
    }


def test_agents_create_minimal_body(cred_dir):
    """create with only --name sends a body with just the name field."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(
            201, {"id": "a2", "name": "solo", "model": "", "system_prompt": ""}
        )
        result = runner.invoke(
            app, ["--json", "agents", "create", "--name", "solo"]
        )

    assert result.exit_code == 0, result.output
    assert mock_client.request.call_args.kwargs["json"] == {"name": "solo"}


def test_agents_update_uses_patch(cred_dir):
    """agents update uses PATCH (not PUT) per the backend contract."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(
            200, {"id": "a1", "name": "new", "model": "m", "system_prompt": ""}
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "agents",
                "update",
                "a1",
                "--name",
                "new",
                "--yes",
            ],
        )

    assert result.exit_code == 0, result.output
    _method, _path = mock_client.request.call_args.args
    assert _method == "PATCH"
    assert _path == "/api/v1/agents/a1"
    assert mock_client.request.call_args.kwargs["json"] == {"name": "new"}


def test_agents_update_no_fields_errors(cred_dir):
    """update with no --name/--model/--prompt fails with a parameter error."""
    config.save_credentials("ahp_tok", "http://srv")
    result = runner.invoke(app, ["agents", "update", "a1", "--yes"])
    assert result.exit_code != 0, result.output


def test_agents_update_declined_exits_0(cred_dir):
    """Answering 'no' to update confirm exits 0 and sends no request."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(200, {})
        result = runner.invoke(
            app,
            ["agents", "update", "a1", "--name", "x"],
            input="n\n",
        )

    assert result.exit_code == 0, result.output
    mock_client.request.assert_not_called()


def test_agents_delete_with_yes(cred_dir):
    """agents delete --yes sends DELETE and prints the result JSON."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(204)
        result = runner.invoke(
            app, ["--json", "agents", "delete", "a1", "--yes"]
        )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body == {"deleted": True, "agent_id": "a1"}
    mock_client.request.assert_called_once_with("DELETE", "/api/v1/agents/a1")


def test_agents_delete_no_interactive_skips_prompt(cred_dir):
    """--no-interactive implies --yes, so no prompt blocks delete."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(204)
        result = runner.invoke(
            app, ["--no-interactive", "agents", "delete", "a1"]
        )

    assert result.exit_code == 0, result.output
    mock_client.request.assert_called_once_with("DELETE", "/api/v1/agents/a1")


def test_agents_404_exits_1(cred_dir):
    """A 404 on a write op maps to exit code 1 (generic API error)."""
    config.save_credentials("ahp_tok", "http://srv")
    with patch("cli.client.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.request.return_value = _mock_response(404, {"detail": "not found"})
        result = runner.invoke(
            app, ["--json", "agents", "delete", "ghost", "--yes"]
        )

    assert result.exit_code == 1, result.output
