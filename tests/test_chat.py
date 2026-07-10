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
    """
    from app.api.v1 import chat as chat_route

    async def fake_stream(**kwargs):
        for chunk in ["Hello", " ", "world!"]:
            yield chunk

    monkeypatch.setattr(chat_route, "stream_agent", fake_stream)

    resp = await client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": message},
        headers=AUTH,
    )
    return {"status": resp.status_code, "text": resp.text, "deltas": _collect_deltas(resp.text)}


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
