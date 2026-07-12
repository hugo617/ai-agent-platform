"""Chat (SSE) tests with a mocked LLM.

We don't hit DeepSeek/OpenAI in tests. Instead we stub ``stream_agent`` to emit a
fixed reply, then assert the SSE stream + message persistence behave correctly.
"""

import json

import pytest

AUTH = {"Authorization": "Bearer fake"}


def _collect_deltas(sse_body: str) -> str:
    """Aggregate ``delta`` values from an SSE response body."""
    out = []
    for line in sse_body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if "delta" in obj:
            out.append(obj["delta"])
    return "".join(out)


async def _mock_chat(client, monkeypatch, agent_id: str, message: str = "Hi") -> dict:
    """Run a streaming chat with a stubbed LLM and return the parsed response.

    Stubs ``stream_agent`` in the chat route module so the test is offline and
    deterministic. Returns ``{"status": int, "text": str, "deltas": str}``.
    Also stubs ``llm_config_service.get_effective`` so the model resolution is
    deterministic without touching env/DB config.
    """
    from app.api.v1 import chat as chat_route

    async def fake_stream(**kwargs):
        for chunk in ["Hello", " ", "world!"]:
            yield chunk

    monkeypatch.setattr(chat_route, "stream_agent", fake_stream)
    # Deterministic effective config so model selection doesn't depend on env.
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat", "deepseek-reasoner"]),
    )

    resp = await client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": message},
        headers=AUTH,
    )
    return {"status": resp.status_code, "text": resp.text, "deltas": _collect_deltas(resp.text)}


def _async_effective(available_models: list[str], default_model: str = "deepseek-chat"):
    """Build an awaitable returning a fixed EffectiveLlmConfig."""
    from app.schemas.llm_config import EffectiveLlmConfig

    cfg = EffectiveLlmConfig.from_resolved(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        default_model=default_model,
        available_models=available_models,
    )

    async def _resolve(*_args, **_kwargs):
        return cfg

    return _resolve


# --------------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_chat_persists_user_and_assistant_messages(app_client, db_session, monkeypatch):
    # Create an agent to chat with.
    create = await app_client.post(
        "/api/v1/agents/",
        json={"name": "Bot", "system_prompt": "hi"},
        headers=AUTH,
    )
    agent_id = create.json()["id"]

    out = await _mock_chat(app_client, monkeypatch, agent_id)
    assert out["status"] == 200
    assert out["deltas"] == "Hello world!"
    assert "[DONE]" in out["text"]

    # Verify both messages were persisted to the DB.
    from sqlalchemy import select

    from app.models.message import Message

    result = await db_session.execute(select(Message))
    all_msgs = list(result.scalars().all())
    roles = [m.role for m in all_msgs]
    assert "user" in roles
    assert "assistant" in roles
    assistant = next(m for m in all_msgs if m.role == "assistant")
    assert assistant.content == "Hello world!"


@pytest.mark.asyncio
async def test_chat_rejects_agent_from_other_tenant(app_client, db_session):
    from app.models.agent import Agent

    leaked = Agent(tenant_id="tnt-OTHER", name="x", model="gpt-4o-mini")
    db_session.add(leaked)
    await db_session.commit()

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": leaked.id, "message": "Hi"},
        headers=AUTH,
    )
    assert resp.status_code == 404


# --------------------------------------------------- conversation history API


@pytest.mark.asyncio
async def test_conversation_list_after_chat(app_client, monkeypatch):
    """A conversation created by chat shows up in GET /conversations/."""
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "List Bot"}, headers=AUTH
        )
    ).json()["id"]
    await _mock_chat(app_client, monkeypatch, agent_id)

    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    assert resp.status_code == 200
    convs = resp.json()
    assert len(convs) == 1
    assert convs[0]["agent_id"] == agent_id
    # updated_at is present and parseable (newly added column).
    assert "updated_at" in convs[0]


@pytest.mark.asyncio
async def test_message_history_after_chat(app_client, monkeypatch):
    """GET /conversations/{id}/messages returns user + assistant messages."""
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "History Bot"}, headers=AUTH
        )
    ).json()["id"]
    await _mock_chat(app_client, monkeypatch, agent_id, message="ping")

    conv_id = (
        (await app_client.get("/api/v1/conversations/", headers=AUTH)).json()[0]["id"]
    )

    resp = await app_client.get(
        f"/api/v1/conversations/{conv_id}/messages", headers=AUTH
    )
    assert resp.status_code == 200
    msgs = resp.json()
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant"]
    assert msgs[0]["content"] == "ping"
    assert msgs[1]["content"] == "Hello world!"


@pytest.mark.asyncio
async def test_conversation_title_derived_from_first_message(app_client, monkeypatch):
    """A new conversation's title is the first user message, truncated to 20 chars."""
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Title Bot"}, headers=AUTH
        )
    ).json()["id"]
    long_msg = "请帮我详细分析一下这个多租户系统的权限模型设计思路"
    await _mock_chat(app_client, monkeypatch, agent_id, message=long_msg)

    conv = (
        await app_client.get("/api/v1/conversations/", headers=AUTH)
    ).json()[0]
    # Title is the first 20 chars + ellipsis, not None, not the whole message.
    assert conv["title"] is not None
    assert conv["title"] == long_msg[:20] + "…"
    assert len(conv["title"]) == 21  # 20 chars + ellipsis


@pytest.mark.asyncio
async def test_conversation_title_short_message_no_ellipsis(app_client, monkeypatch):
    """A short first message (<20 chars) becomes the title verbatim, no ellipsis."""
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Short Bot"}, headers=AUTH
        )
    ).json()["id"]
    await _mock_chat(app_client, monkeypatch, agent_id, message="你好")

    conv = (
        await app_client.get("/api/v1/conversations/", headers=AUTH)
    ).json()[0]
    assert conv["title"] == "你好"


@pytest.mark.asyncio
async def test_delete_conversation(app_client, monkeypatch):
    """DELETE removes the conversation; it no longer appears in the list."""
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Doomed Bot"}, headers=AUTH
        )
    ).json()["id"]
    await _mock_chat(app_client, monkeypatch, agent_id)

    conv_id = (
        (await app_client.get("/api/v1/conversations/", headers=AUTH)).json()[0]["id"]
    )

    resp = await app_client.delete(
        f"/api/v1/conversations/{conv_id}", headers=AUTH
    )
    assert resp.status_code == 204

    # The conversation no longer appears in the list.
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    assert all(c["id"] != conv_id for c in resp.json())

    # Re-deleting the same (now absent) conversation → 404.
    resp = await app_client.delete(
        f"/api/v1/conversations/{conv_id}", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_conversation_returns_404(app_client):
    """NotFoundError → 404 (typed exception, not a blanket ValueError→404)."""
    resp = await app_client.delete(
        "/api/v1/conversations/nonexistent-id", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_messages_for_nonexistent_conversation_returns_empty(app_client):
    """No matching conversation → empty message list (no leakage, no 404)."""
    resp = await app_client.get(
        "/api/v1/conversations/nonexistent-id/messages", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json() == []


# --------------------------------------------------------- multi-tenant wall


@pytest.mark.asyncio
async def test_cross_tenant_conversation_not_visible(app_client, db_session, tenant_owner):
    """A conversation in tenant B is invisible from tenant A (list + history)."""
    from app.models.agent import Conversation

    other_conv = Conversation(
        id="conv-other-tenant",
        tenant_id="tnt-other-isolated",
        agent_id="some-agent",
        user_id="other-user",
        title="Other Tenant's Chat",
    )
    db_session.add(other_conv)
    await db_session.commit()

    # Not in this tenant's list.
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    assert all(c["id"] != other_conv.id for c in resp.json())

    # History is empty (no message belongs to this conversation in this tenant).
    resp = await app_client.get(
        f"/api/v1/conversations/{other_conv.id}/messages", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ------------------------------------------------------- permission boundary


@pytest.mark.asyncio
async def test_member_cannot_delete_conversation(member_client):
    """member has no conversations:delete → 403 (guard fires before lookup)."""
    resp = await member_client.delete("/api/v1/conversations/any-id", headers=AUTH)
    assert resp.status_code == 403


# ----------------------------------------------- bug fix: agent.model is used


@pytest.mark.asyncio
async def test_agent_model_is_passed_to_stream_agent(app_client, monkeypatch):
    """Bug 1 regression: stream_agent must receive agent.model, not the global default.

    Before the fix, chat.py never forwarded the agent's model and stream_agent
    hardcoded settings.openai_model — so every agent spoke as the same model
    regardless of its configured ``model`` field.
    """
    from app.api.v1 import chat as chat_route

    captured: dict = {}

    async def capturing_stream(**kwargs):
        captured.update(kwargs)
        yield "ok"

    monkeypatch.setattr(chat_route, "stream_agent", capturing_stream)
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat", "deepseek-reasoner"]),
    )

    create = await app_client.post(
        "/api/v1/agents/",
        json={"name": "Reasoner", "model": "deepseek-reasoner"},
        headers=AUTH,
    )
    agent_id = create.json()["id"]

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "Hi"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    # The agent's chosen model reached the LLM layer.
    assert captured.get("model") == "deepseek-reasoner"
    assert captured.get("api_key") == "test-key"
    assert captured.get("base_url") == "https://api.deepseek.com"


@pytest.mark.asyncio
async def test_agent_inference_params_passed_to_stream_agent(app_client, monkeypatch):
    """Agent inference config (temperature/max_tokens/top_p) reaches stream_agent.

    Verifies the full chain: Agent.temperature/max_tokens/top_p → chat.py →
    stream_agent kwargs. A None value (top_p here) is forwarded as None so the
    LLM layer knows to skip it (use provider default).
    """
    from app.api.v1 import chat as chat_route

    captured: dict = {}

    async def capturing_stream(**kwargs):
        captured.update(kwargs)
        yield "ok"

    monkeypatch.setattr(chat_route, "stream_agent", capturing_stream)
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat"]),
    )

    create = await app_client.post(
        "/api/v1/agents/",
        json={
            "name": "Tuned Agent",
            "temperature": 0.1,
            "max_tokens": 1024,
            # top_p omitted → None → forwarded as None
        },
        headers=AUTH,
    )
    agent_id = create.json()["id"]

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "Hi"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert captured.get("temperature") == 0.1
    assert captured.get("max_tokens") == 1024
    assert captured.get("top_p") is None


# --------------------------------------- context engineering: truncation


@pytest.mark.asyncio
async def test_truncate_history_called_on_long_conversation(
    app_client, db_session, tenant_owner, monkeypatch
):
    """Long conversations are truncated before reaching ``stream_agent``.

    We pre-seed a conversation with many heavy messages, then chat and capture
    the ``history`` kwarg the (stubbed) ``stream_agent`` received. The captured
    history must be smaller than the stored message count — proving the
    sliding-window truncation fired.
    """
    from app.api.v1 import chat as chat_route

    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Long Bot"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    # Establish a conversation by sending one (mocked) message.
    await _mock_chat(app_client, monkeypatch, agent_id, message="seed")

    # Find the conversation id.
    conv_id = (
        (await app_client.get("/api/v1/conversations/", headers=AUTH)).json()[0]["id"]
    )

    # Inject a large number of heavy messages directly into the DB so the
    # next chat has a very long history that exceeds the token budget.
    from app.models.message import Message

    heavy = "你好世界测试" * 200  # ~1000 CJK chars ≈ 1000+ tokens per message
    msgs = [
        Message(
            conversation_id=conv_id,
            tenant_id=tenant_owner["tenant_id"],
            role="user" if i % 2 == 0 else "assistant",
            content=f"{heavy} #{i}",
        )
        for i in range(40)
    ]
    db_session.add_all(msgs)
    await db_session.commit()

    captured: dict = {}

    async def capturing_stream(**kwargs):
        captured.update(kwargs)
        yield "ok"

    monkeypatch.setattr(chat_route, "stream_agent", capturing_stream)
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat"]),
    )

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "next", "conversation_id": conv_id},
        headers=AUTH,
    )
    assert resp.status_code == 200
    # The history passed to the LLM was truncated (well below 40 stored + seed).
    assert len(captured["history"]) < 40
    # The minimum floor is respected.
    assert len(captured["history"]) >= 6


# --------------------------- context engineering: partial reply persistence


@pytest.mark.asyncio
async def test_assistant_partial_reply_persisted_on_error(app_client, db_session, monkeypatch):
    """A partial reply is persisted when the stream fails mid-way.

    Without this, a mid-stream failure leaves the user's message in history
    with no assistant counterpart — a "断档" (gap). The fix stores whatever was
    generated, tagged ``[生成中断]``.
    """
    from app.api.v1 import chat as chat_route

    async def failing_stream(**kwargs):
        yield "partial "
        yield "reply"
        raise RuntimeError("LLM boom")

    monkeypatch.setattr(chat_route, "stream_agent", failing_stream)
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat"]),
    )

    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Failing Bot"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "Hi"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert "[DONE]" not in resp.text  # stream aborted, no completion frame
    assert "error" in resp.text

    # The partial assistant reply was persisted with the interruption marker.
    from sqlalchemy import select

    from app.models.message import Message

    result = await db_session.execute(select(Message))
    all_msgs = list(result.scalars().all())
    assistant_msgs = [m for m in all_msgs if m.role == "assistant"]
    assert len(assistant_msgs) == 1
    assert "partial reply" in assistant_msgs[0].content
    assert "[生成中断]" in assistant_msgs[0].content


# ------------------------------- context engineering: LLM timeout protection


@pytest.mark.asyncio
async def test_llm_timeout_yields_error_frame(app_client, monkeypatch):
    """A stalled LLM stream is cancelled by the timeout and surfaces as an error.

    We stub ``ChatOpenAI`` + ``create_react_agent`` so the *real* ``stream_agent``
    runs (including its ``asyncio.timeout`` guard), but the fake agent never
    yields an event — it hangs. With the timeout shortened to 0.1s the guard
    fires, ``stream_agent`` raises ``TimeoutError``, and the chat endpoint
    returns an error frame instead of hanging forever.
    """
    import asyncio

    from app.agents import graph as graph_module
    from app.api.v1 import chat as chat_route

    class _HangingAgent:
        async def astream_events(self, *_args, **_kwargs):
            # Never yields an event → simulates a stalled upstream provider.
            await asyncio.sleep(30)
            yield {}  # pragma: no cover - unreachable

    monkeypatch.setattr(graph_module, "LLM_STREAM_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(graph_module, "ChatOpenAI", lambda **_kw: object())
    monkeypatch.setattr(
        graph_module, "create_react_agent", lambda *_a, **_kw: _HangingAgent()
    )
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat"]),
    )

    create = await app_client.post(
        "/api/v1/agents/", json={"name": "Slow Bot"}, headers=AUTH
    )
    agent_id = create.json()["id"]

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "Hi"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert "error" in resp.text
    assert "[DONE]" not in resp.text
