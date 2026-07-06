"""Chat (SSE) tests with a mocked LLM.

We don't hit OpenAI in tests. Instead we stub ``stream_agent`` to emit a
fixed reply, then assert the SSE stream + message persistence behave correctly.
"""

import json

import pytest


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


@pytest.mark.asyncio
async def test_chat_persists_user_and_assistant_messages(app_client, db_session, monkeypatch):
    # Create an agent to chat with.
    create = await app_client.post(
        "/api/v1/agents/",
        json={"name": "Bot", "system_prompt": "hi"},
        headers={"Authorization": "Bearer fake"},
    )
    agent_id = create.json()["id"]

    # Stub the LLM streaming so the test is deterministic & offline.
    from app.api.v1 import chat as chat_route

    async def fake_stream(**kwargs):
        for chunk in ["Hello", " ", "world!"]:
            yield chunk

    monkeypatch.setattr(chat_route, "stream_agent", fake_stream)

    resp = await app_client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "Hi"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    assert _collect_deltas(resp.text) == "Hello world!"
    assert "[DONE]" in resp.text

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
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 404
