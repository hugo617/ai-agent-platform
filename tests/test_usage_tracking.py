"""Token usage tracking tests (Token billing series 1/4).

Covers the full chain: ``stream_agent`` accumulates ``usage_metadata`` from
every ``on_chat_model_end`` (ReAct multi-turn sum, not last-wins) → yields a
usage dict at stream end → ``event_source`` persists it on the assistant
Message + appends a UsageEvent ledger row. Also covers backward compat
(stubbed streams that only yield text → NULL token columns, no crash) and
the interrupted-stream partial-usage path.
"""

import json

import pytest

AUTH = {"Authorization": "Bearer fake"}


def _collect_deltas(sse_body: str) -> str:
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


def _stream_with_usage(chunks: list[str], usage: dict, model: str = "deepseek-chat"):
    """Build a fake stream_agent that yields text then a usage dict."""

    async def _fake(**_kwargs):
        for c in chunks:
            yield c
        yield {"usage": usage, "model": model}

    return _fake


async def _do_chat(client, monkeypatch, agent_id: str, fake_stream) -> dict:
    """Run a streaming chat with the given fake stream, return response."""
    from app.api.v1 import chat as chat_route

    monkeypatch.setattr(chat_route, "stream_agent", fake_stream)
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat", "deepseek-reasoner"]),
    )

    resp = await client.post(
        "/api/v1/chat/stream",
        json={"agent_id": agent_id, "message": "Hi"},
        headers=AUTH,
    )
    return {"status": resp.status_code, "text": resp.text, "deltas": _collect_deltas(resp.text)}


# ----------------------------------------------------------- stream_agent unit


@pytest.mark.asyncio
async def test_stream_agent_accumulates_usage_across_multiple_llm_calls(
    app_client, db_session, monkeypatch
):
    """ReAct agents call the LLM more than once; usage must sum, not overwrite.

    We stub ChatOpenAI + create_react_agent so the *real* stream_agent runs
    against a fake agent whose astream_events emits two on_chat_model_end
    events (simulating think → tool → think again). The accumulated totals
    must equal the sum of both calls.
    """
    from langchain_core.messages import AIMessageChunk

    from app.agents import graph as graph_mod

    class _FakeOutput:
        # LangChain's usage_metadata is a dict (with input/output/total keys),
        # not a typed object — graph.py calls .get() on it.
        def __init__(self, usage_dict):
            self.usage_metadata = usage_dict

    class _FakeStream:
        async def astream_events(self, *_args, **_kwargs):
            # First LLM call: emits a text chunk + usage
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="Hello")}}
            yield {
                "event": "on_chat_model_end",
                "data": {"output": _FakeOutput({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})},
            }
            # Second LLM call (after a tool): more text + usage
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content=" world")}}
            yield {
                "event": "on_chat_model_end",
                "data": {"output": _FakeOutput({"input_tokens": 20, "output_tokens": 8, "total_tokens": 28})},
            }

    def _fake_react(_llm, *_args, **_kwargs):
        return _FakeStream()

    class _FakeLLM:
        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(graph_mod, "ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(graph_mod, "create_react_agent", _fake_react)

    collected = []
    async for item in graph_mod.stream_agent(
        user_id="u1",
        tenant_id="tnt-test",
        db=db_session,
        api_key="k",
        base_url="http://x",
        model="deepseek-chat",
        system_prompt="",
        history=[],
        user_message="hi",
    ):
        collected.append(item)

    texts = [c for c in collected if isinstance(c, str)]
    usage = [c for c in collected if isinstance(c, dict)]
    assert "".join(texts) == "Hello world"
    assert len(usage) == 1
    # Sum of both calls: 10+20=30 input, 5+8=13 output, 15+28=43 total
    assert usage[0]["usage"]["input_tokens"] == 30
    assert usage[0]["usage"]["output_tokens"] == 13
    assert usage[0]["usage"]["total_tokens"] == 43
    assert usage[0]["model"] == "deepseek-chat"


# ----------------------------------------------------------- end-to-end via API


@pytest.mark.asyncio
async def test_chat_records_usage_on_message_and_ledger(app_client, db_session, monkeypatch):
    """A successful chat writes token cols on Message + a UsageEvent row."""
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Usage Bot"}, headers=AUTH
        )
    ).json()["id"]

    fake = _stream_with_usage(["Hi ", "there"], {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19})
    out = await _do_chat(app_client, monkeypatch, agent_id, fake)
    assert out["status"] == 200
    assert out["deltas"] == "Hi there"

    from sqlalchemy import select

    from app.models.message import Message
    from app.models.usage_event import UsageEvent

    msgs = (await db_session.execute(select(Message))).scalars().all()
    assistant = next(m for m in msgs if m.role == "assistant")
    assert assistant.prompt_tokens == 12
    assert assistant.completion_tokens == 7
    assert assistant.total_tokens == 19
    assert assistant.model == "deepseek-chat"

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    assert len(events) == 1
    ev = events[0]
    assert ev.tenant_id == assistant.tenant_id
    assert ev.conversation_id == assistant.conversation_id
    assert ev.message_id == assistant.id
    assert ev.total_tokens == 19
    assert ev.prompt_tokens == 12
    assert ev.completion_tokens == 7
    assert ev.model == "deepseek-chat"
    # customer_id / cost left NULL for later tasks
    assert ev.customer_id is None
    assert ev.cost is None


@pytest.mark.asyncio
async def test_chat_without_usage_keeps_nulls_and_no_ledger(app_client, db_session, monkeypatch):
    """A stubbed stream (text only, no usage dict) leaves token cols NULL.

    This is the backward-compat path: existing tests and any provider that
    doesn't return usage must not crash, and must not write a ledger row.
    """

    async def _text_only_stream(**_kwargs):
        for c in ["Hello", "!", ""]:
            if c:
                yield c

    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "No Usage Bot"}, headers=AUTH
        )
    ).json()["id"]

    out = await _do_chat(app_client, monkeypatch, agent_id, _text_only_stream)
    assert out["status"] == 200

    from sqlalchemy import select

    from app.models.message import Message
    from app.models.usage_event import UsageEvent

    assistant = next(
        m for m in (await db_session.execute(select(Message))).scalars().all()
        if m.role == "assistant"
    )
    assert assistant.prompt_tokens is None
    assert assistant.completion_tokens is None
    assert assistant.total_tokens is None
    assert assistant.model is None

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    assert events == []


@pytest.mark.asyncio
async def test_interrupted_stream_records_partial_usage(app_client, db_session, monkeypatch):
    """A stream that fails mid-way still records whatever usage it captured."""

    async def _failing_stream(**_kwargs):
        yield "partial"
        yield {"usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}, "model": "deepseek-chat"}
        raise RuntimeError("upstream broke")

    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Fail Bot"}, headers=AUTH
        )
    ).json()["id"]

    out = await _do_chat(app_client, monkeypatch, agent_id, _failing_stream)
    assert out["status"] == 200  # SSE always 200; error is in the body
    assert "error" in out["text"]

    from sqlalchemy import select

    from app.models.message import Message
    from app.models.usage_event import UsageEvent

    assistant = next(
        m for m in (await db_session.execute(select(Message))).scalars().all()
        if m.role == "assistant"
    )
    assert "partial" in assistant.content
    assert assistant.status == "failed"
    assert assistant.total_tokens == 8
    assert assistant.prompt_tokens == 5
    assert assistant.completion_tokens == 3

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].total_tokens == 8


# ----------------------------------------------------------- tenant isolation


@pytest.mark.asyncio
async def test_usage_events_tenant_isolated(app_client, db_session, monkeypatch):
    """UsageEventRepository.list_for_tenant only returns this tenant's rows."""
    from app.models.usage_event import UsageEvent
    from app.repositories.usage_event import UsageEventRepository

    # Two events in different tenants.
    db_session.add(UsageEvent(
        tenant_id="tnt-A", conversation_id="c1", message_id="m1",
        user_id="u1", model="m", prompt_tokens=1, completion_tokens=1, total_tokens=2,
    ))
    db_session.add(UsageEvent(
        tenant_id="tnt-B", conversation_id="c2", message_id="m2",
        user_id="u2", model="m", prompt_tokens=3, completion_tokens=3, total_tokens=6,
    ))
    await db_session.commit()

    repo = UsageEventRepository(db_session)
    rows_a = await repo.list_for_tenant("tnt-A")
    assert len(rows_a) == 1
    assert rows_a[0].tenant_id == "tnt-A"

    rows_b = await repo.list_for_tenant("tnt-B")
    assert len(rows_b) == 1
    assert rows_b[0].tenant_id == "tnt-B"

    # sum aggregation
    p, c, t = await repo.sum_tokens_for_tenant("tnt-A")
    assert (p, c, t) == (1, 1, 2)
    p, c, t = await repo.sum_tokens_for_tenant("tnt-B")
    assert (p, c, t) == (3, 3, 6)
    # empty tenant returns zeros
    p, c, t = await repo.sum_tokens_for_tenant("tnt-NONE")
    assert (p, c, t) == (0, 0, 0)


# ----------------------------------------------------------- append_message compat


@pytest.mark.asyncio
async def test_append_message_backward_compat_no_token_kwargs(app_client, db_session):
    """append_message still works without the new token kwargs (NULL cols)."""
    from app.models.agent import Conversation
    from app.models.message import Message
    from app.services.conversation_service import ConversationService

    conv = Conversation(tenant_id="tnt-test", agent_id="a1", user_id="u1", title="t")
    db_session.add(conv)
    await db_session.commit()

    svc = ConversationService(db_session)
    msg = await svc.append_message("tnt-test", conv.id, "user", "hello")
    assert msg.prompt_tokens is None
    assert msg.completion_tokens is None
    assert msg.total_tokens is None
    assert msg.model is None
    # And the DB row matches
    fresh = await db_session.get(Message, msg.id)
    assert fresh.prompt_tokens is None
    assert fresh.role == "user"
