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
