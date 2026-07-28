"""Schema + model tests for composite-chat slice 01 (priority 72).

Slice 01 is the data layer: ``Conversation.kind`` + ``Message.fragments``
columns plus the new ``CompositeRequest`` / ``CompositeFragment`` /
``CompositeResponse`` schemas. No编排 / API / LLM here — those land in
slices 02-03. This file locks the data-layer contracts slice 02-03 build on:

- A new Conversation defaults to ``kind="single"`` (backward compatible).
- A legacy Conversation row (no ``kind`` attribute, simulating pre-migration
  data) round-trips through ConversationRead as ``kind="single"`` — the
  Pydantic default kicks in when ``from_attributes`` can't find the field.
- A new Message defaults to ``fragments=None`` (zero cost for ordinary chats).
- A composite assistant Message's fragments round-trip with the full token
  triple (slice-03 billing contract).
- CompositeRequest enforces agent_ids non-empty + ≤8 + message non-empty.
- CompositeFragment enforces status ∈ {completed, failed} + model ≤64.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------------- model defaults


@pytest.mark.asyncio
async def test_new_conversation_defaults_to_single_kind(db_session, test_env):
    """A Conversation created with no explicit kind gets the 'single' default.

    This is the backward-compatibility guarantee (AC1.1 + AC1.4): existing
    single-agent code paths keep producing kind='single' without touching
    ConversationService (slice 03 is the first to pass kind explicitly).
    """
    from app.models.agent import Agent, Conversation

    agent = Agent(name="Bot", tenant_id=test_env.tenant_id, system_prompt="",
                  model="deepseek-chat")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    conv = Conversation(
        tenant_id=test_env.tenant_id,
        agent_id=agent.id,
        user_id=test_env.owner_user,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.kind == "single"


@pytest.mark.asyncio
async def test_new_message_defaults_to_none_fragments(db_session, test_env):
    """A Message created with no explicit fragments gets None (AC1.2).

    None — not [] — so ordinary messages pay zero serialization cost; only
    the assistant turn of a composite conversation fills this column.
    """
    from app.models.agent import Agent, Conversation
    from app.models.message import Message

    agent = Agent(name="Bot", tenant_id=test_env.tenant_id, system_prompt="",
                  model="deepseek-chat")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    conv = Conversation(
        tenant_id=test_env.tenant_id, agent_id=agent.id,
        user_id=test_env.owner_user,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg = Message(
        conversation_id=conv.id, tenant_id=test_env.tenant_id,
        role="user", content="hi",
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    assert msg.fragments is None


# ----------------------------------------------------------- ConversationRead


@pytest.mark.asyncio
async def test_legacy_conversation_round_trips_as_single():
    """A pre-migration Conversation (no kind attr) round-trips as 'single'.

    Simulates a row written before the migration added the kind column: the
    ORM object simply doesn't have the attribute. ConversationRead's Pydantic
    default ('single') must kick in so legacy history stays legible. This is
    the schema-level belt-and-braces behind the migration's backfill.
    """
    from app.schemas.conversation import ConversationRead

    legacy_row = SimpleNamespace(
        id="conv-legacy",
        agent_id="agent-1",
        tenant_id="tnt-1",
        user_id="user-1",
        title="old chat",
        customer_id=None,
        tags=[],
        is_pinned=False,
        is_starred=False,
        # NOTE: no `kind` attribute — mimics a pre-migration row.
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    dto = ConversationRead.model_validate(legacy_row)
    assert dto.kind == "single"


@pytest.mark.asyncio
async def test_composite_conversation_round_trips_with_kind():
    """A composite Conversation surfaces kind='composite' through the schema."""
    from app.schemas.conversation import ConversationRead

    row = SimpleNamespace(
        id="conv-comp", agent_id="agent-1", tenant_id="tnt-1", user_id="user-1",
        title="monthly review", customer_id=None, tags=[], is_pinned=False,
        is_starred=False, kind="composite",
        created_at="2026-07-28T00:00:00+00:00",
        updated_at="2026-07-28T00:00:00+00:00",
    )
    dto = ConversationRead.model_validate(row)
    assert dto.kind == "composite"


@pytest.mark.asyncio
async def test_conversation_read_rejects_invalid_kind():
    """Literal['single','composite'] rejects typos like 'compsite'."""
    from app.schemas.conversation import ConversationRead

    row = SimpleNamespace(
        id="c", agent_id="a", tenant_id="t", user_id="u", title=None,
        customer_id=None, tags=[], is_pinned=False, is_starred=False,
        kind="compsite",  # typo
        created_at="2026-07-28T00:00:00+00:00",
        updated_at="2026-07-28T00:00:00+00:00",
    )
    with pytest.raises(ValidationError):
        ConversationRead.model_validate(row)


# ----------------------------------------------------------- MessageRead


@pytest.mark.asyncio
async def test_legacy_message_round_trips_with_none_fragments():
    """A pre-migration Message (no fragments attr) round-trips as None."""
    from app.schemas.conversation import MessageRead

    legacy_msg = SimpleNamespace(
        id="msg-1", role="user", content="hi", status="completed", error=None,
        # NOTE: no `fragments` attribute — mimics a pre-migration row.
        created_at="2026-01-01T00:00:00+00:00",
    )
    dto = MessageRead.model_validate(legacy_msg)
    assert dto.fragments is None


@pytest.mark.asyncio
async def test_composite_message_round_trips_with_fragments():
    """A composite assistant Message surfaces fragments with the token triple.

    The token triple (input/output/total) is the slice-03 billing contract:
    each fragment drives one UsageEvent row, so the round-trip must preserve
    all three fields verbatim.
    """
    from app.schemas.conversation import MessageRead

    fragments = [
        {
            "agent_id": "agent-a", "agent_name": "健康顾问", "snippet": "...",
            "status": "completed", "error": None, "model": "deepseek-chat",
            "input_tokens": 50, "output_tokens": 73, "total_tokens": 123,
        },
        {
            "agent_id": "agent-b", "agent_name": "预约专员", "snippet": "",
            "status": "failed", "error": "rate limited", "model": "deepseek-chat",
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        },
    ]
    msg = SimpleNamespace(
        id="msg-2", role="assistant", content="synthesis...", status="completed",
        error=None, fragments=fragments,
        created_at="2026-07-28T00:00:00+00:00",
    )
    dto = MessageRead.model_validate(msg)
    assert dto.fragments is not None
    assert len(dto.fragments) == 2
    assert dto.fragments[0]["total_tokens"] == 123
    assert dto.fragments[1]["status"] == "failed"


# ----------------------------------------------------------- CompositeRequest


@pytest.mark.asyncio
async def test_composite_request_happy_path():
    from app.schemas.conversation import CompositeRequest

    req = CompositeRequest(
        agent_ids=["a1", "a2", "a3"], message="本月服务复盘建议",
    )
    assert req.agent_ids == ["a1", "a2", "a3"]
    assert req.conversation_id is None
    assert req.synthesize_model is None


@pytest.mark.asyncio
async def test_composite_request_rejects_empty_agent_ids():
    from app.schemas.conversation import CompositeRequest

    with pytest.raises(ValidationError):
        CompositeRequest(agent_ids=[], message="hi")


@pytest.mark.asyncio
async def test_composite_request_rejects_more_than_eight_agents():
    from app.schemas.conversation import CompositeRequest

    with pytest.raises(ValidationError):
        CompositeRequest(agent_ids=[f"a{i}" for i in range(9)], message="hi")


@pytest.mark.asyncio
async def test_composite_request_rejects_empty_message():
    from app.schemas.conversation import CompositeRequest

    with pytest.raises(ValidationError):
        CompositeRequest(agent_ids=["a1"], message="")


# ----------------------------------------------------------- CompositeFragment


@pytest.mark.asyncio
async def test_fragment_rejects_invalid_status():
    """status is Literal['completed','failed'] — anything else is rejected."""
    from app.schemas.conversation import CompositeFragment

    with pytest.raises(ValidationError):
        CompositeFragment(
            agent_id="a", agent_name="n", snippet="s", status="pending",
        )


@pytest.mark.asyncio
async def test_fragment_accepts_token_triple():
    """The token triple is the slice-03 billing contract — must round-trip."""
    from app.schemas.conversation import CompositeFragment

    frag = CompositeFragment(
        agent_id="a", agent_name="n", snippet="s", status="completed",
        model="deepseek-chat", input_tokens=10, output_tokens=20, total_tokens=30,
    )
    assert frag.total_tokens == 30
    assert frag.model == "deepseek-chat"


# ----------------------------------------------------------- CompositeResponse


@pytest.mark.asyncio
async def test_composite_response_constructs_with_fragments():
    from app.schemas.conversation import CompositeFragment, CompositeResponse

    resp = CompositeResponse(
        conversation_id="conv-1",
        synthesis="综合建议...",
        fragments=[
            CompositeFragment(
                agent_id="a", agent_name="n1", snippet="s1", status="completed",
            ),
            CompositeFragment(
                agent_id="b", agent_name="n2", snippet="", status="failed",
                error="timeout",
            ),
        ],
    )
    assert resp.conversation_id == "conv-1"
    assert len(resp.fragments) == 2
    assert resp.fragments[1].error == "timeout"
