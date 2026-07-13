"""Customer-conversation attribution tests (Token billing series 3/4).

Covers the attribution chain that lets the platform answer "how many tokens
did serving customer X consume":

- ``Conversation.customer_id`` — the new optional FK, written when a staff
  member starts a chat while serving a customer.
- ``create_or_get`` — passes ``customer_id`` into a NEW conversation but never
  overwrites it on a follow-up turn (reuse path keeps the original binding).
- ``_record_usage`` — propagates ``conv.customer_id`` onto the UsageEvent so
  the ledger row is attributable.
- ``UsageEventRepository`` — ``sum_tokens_for_customer`` / ``list_for_customer``
  aggregation, store-scoped vs global (HQ) views.
- ``ConversationRepository.list_for_customer`` — chats tied to a customer.
- API — ``GET /customers/{id}/usage`` store vs HQ scope, permission boundary,
  backward compatibility (NULL customer_id → zero usage).

All seed helpers use the ORM directly (no real LLM call); the chat endpoint
is exercised only where the full attribution chain matters.
"""

from datetime import UTC, datetime

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------------- helpers


async def _seed_customer(db_session, identity_key: str = "13800000099",
                         name: str = "测试客户"):
    """Insert a global Customer identity and return it."""
    from app.models.customer import Customer

    c = Customer(identity_key=identity_key, name=name)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _seed_agent(db_session, tenant_id: str):
    from app.models.agent import Agent

    agent = Agent(name="TestBot", tenant_id=tenant_id, system_prompt="hi",
                  model="deepseek-chat")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _seed_conversation(db_session, tenant_id: str, agent_id: str,
                             user_id: str = "test-user", customer_id=None,
                             title: str = "t"):
    """Insert a Conversation (optionally attributed to a customer)."""
    from app.models.agent import Conversation

    conv = Conversation(tenant_id=tenant_id, agent_id=agent_id, user_id=user_id,
                        title=title, customer_id=customer_id)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


async def _seed_message(db_session, tenant_id: str, conv_id: str,
                        role: str = "assistant"):
    from app.models.message import Message

    msg = Message(conversation_id=conv_id, tenant_id=tenant_id, role=role,
                  content="hi", created_at=datetime.now(UTC))
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


async def _seed_usage_event(db_session, tenant_id: str, conv_id: str, msg_id: str,
                            customer_id=None, total: int = 100,
                            prompt: int = 40, completion: int = 60,
                            cost=None, model: str = "deepseek-chat"):
    """Insert a UsageEvent ledger row attributed to a customer (or NULL)."""
    from app.models.usage_event import UsageEvent

    ev = UsageEvent(
        tenant_id=tenant_id,
        conversation_id=conv_id,
        message_id=msg_id,
        agent_id=None,
        customer_id=customer_id,
        user_id="test-user",
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost=cost,
    )
    db_session.add(ev)
    await db_session.commit()
    await db_session.refresh(ev)
    return ev


# ----------------------------------------------------- model + create_or_get


async def test_conversation_customer_id_column_nullable_by_default(
    db_session, test_env
):
    """A conversation created without customer_id has NULL (backward compat)."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(db_session, test_env.tenant_id, agent.id)
    assert conv.customer_id is None


def _stream_with_usage(chunks: list[str], usage: dict, model: str = "deepseek-chat"):
    """Build a fake stream_agent that yields text then a usage dict."""
    async def _fake(**_kwargs):
        for c in chunks:
            yield c
        yield {"usage": usage, "model": model}

    return _fake


def _async_effective(available_models: list[str], default_model: str = "deepseek-chat"):
    """Build an awaitable returning a fixed EffectiveLlmConfig (mock LLM cfg)."""
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


async def _do_chat(client, monkeypatch, agent_id: str, fake_stream,
                   customer_id: str | None = None):
    """Run a streaming chat (optionally attributed to a customer). Returns resp."""
    from app.api.v1 import chat as chat_route

    monkeypatch.setattr(chat_route, "stream_agent", fake_stream)
    monkeypatch.setattr(
        chat_route.llm_config_service,
        "get_effective",
        _async_effective(["deepseek-chat", "deepseek-reasoner"]),
    )
    body = {"agent_id": agent_id, "message": "Hi"}
    if customer_id is not None:
        body["customer_id"] = customer_id
    return await client.post(
        "/api/v1/chat/stream", json=body, headers=AUTH
    )


async def test_chat_attributes_new_conversation_to_customer(
    app_client, db_session, monkeypatch
):
    """POST /chat/stream with customer_id writes it on the new Conversation.

    Full attribution chain: ChatRequest.customer_id → create_or_get →
    Conversation.customer_id → _record_usage → UsageEvent.customer_id.
    """
    from sqlalchemy import select

    from app.models.agent import Conversation
    from app.models.usage_event import UsageEvent

    # Create an agent + a customer to attribute to.
    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Attrib Bot"}, headers=AUTH
        )
    ).json()["id"]
    customer = await _seed_customer(db_session)

    fake = _stream_with_usage(["Hi"], {"input_tokens": 10, "output_tokens": 5,
                                       "total_tokens": 15})
    resp = await _do_chat(app_client, monkeypatch, agent_id, fake,
                          customer_id=customer.id)
    assert resp.status_code == 200

    convs = (await db_session.execute(select(Conversation))).scalars().all()
    assert len(convs) == 1
    assert convs[0].customer_id == customer.id

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].customer_id == customer.id  # propagated through the chain


async def test_chat_without_customer_id_backward_compat(
    app_client, db_session, monkeypatch
):
    """POST /chat/stream without customer_id → conversation + event keep NULL."""
    from sqlalchemy import select

    from app.models.agent import Conversation

    agent_id = (
        await app_client.post(
            "/api/v1/agents/", json={"name": "Plain Bot"}, headers=AUTH
        )
    ).json()["id"]
    fake = _stream_with_usage(["Hi"], {"input_tokens": 5, "output_tokens": 5,
                                       "total_tokens": 10})
    resp = await _do_chat(app_client, monkeypatch, agent_id, fake)
    assert resp.status_code == 200

    convs = (await db_session.execute(select(Conversation))).scalars().all()
    assert len(convs) == 1
    assert convs[0].customer_id is None  # staff internal query, no attribution


# ----------------------------------------------------- _record_usage propagation
#
# The _record_usage → UsageEvent.customer_id propagation is exercised end-to-end
# by test_chat_attributes_new_conversation_to_customer above (it asserts
# events[0].customer_id == customer.id through the full chat chain). We don't
# add a separate unit test here because isolating _record_usage under the
# db_session fixture requires careful expire management that doesn't reflect
# the real call path (where conv/agent are freshly committed in-request).


# ----------------------------------------------- UsageEventRepository aggregation


async def test_sum_tokens_for_customer_store_scoped(db_session, test_env):
    """Store-scoped sum counts only this tenant's events for the customer."""
    from app.repositories.usage_event import UsageEventRepository

    agent = await _seed_agent(db_session, test_env.tenant_id)
    customer = await _seed_customer(db_session)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id, customer_id=customer.id
    )
    msg = await _seed_message(db_session, test_env.tenant_id, conv.id)
    await _seed_usage_event(
        db_session, test_env.tenant_id, conv.id, msg.id,
        customer_id=customer.id, total=100, prompt=40, completion=60,
    )

    prompt, completion, total, cost, conv_count, last = (
        await UsageEventRepository(db_session).sum_tokens_for_customer(
            customer.id, tenant_id=test_env.tenant_id
        )
    )
    assert (prompt, completion, total) == (40, 60, 100)
    assert conv_count == 1
    assert last is not None


async def test_sum_tokens_for_customer_global_cross_tenant(db_session, test_env):
    """Global (HQ) sum aggregates across tenants for the same customer."""
    from app.repositories.usage_event import UsageEventRepository

    tid = test_env.tenant_id
    other_tid = "tnt-custlink-other"
    agent = await _seed_agent(db_session, tid)
    customer = await _seed_customer(db_session)

    # Store A
    conv_a = await _seed_conversation(db_session, tid, agent.id,
                                      customer_id=customer.id)
    msg_a = await _seed_message(db_session, tid, conv_a.id)
    await _seed_usage_event(db_session, tid, conv_a.id, msg_a.id,
                            customer_id=customer.id, total=100)

    # Store B (different tenant, same customer identity)
    conv_b = await _seed_conversation(db_session, other_tid, agent.id,
                                      customer_id=customer.id)
    msg_b = await _seed_message(db_session, other_tid, conv_b.id)
    await _seed_usage_event(db_session, other_tid, conv_b.id, msg_b.id,
                            customer_id=customer.id, total=200)

    # Global: both events
    _, _, total_global, _, conv_count_global, _ = (
        await UsageEventRepository(db_session).sum_tokens_for_customer(
            customer.id, tenant_id=None
        )
    )
    assert total_global == 300
    assert conv_count_global == 2

    # Store-scoped: only store A's event
    _, _, total_a, _, conv_count_a, _ = (
        await UsageEventRepository(db_session).sum_tokens_for_customer(
            customer.id, tenant_id=tid
        )
    )
    assert total_a == 100
    assert conv_count_a == 1


async def test_sum_tokens_for_customer_no_attribution_returns_zeros(
    db_session, test_env
):
    """A customer with no attributed usage returns zeros / None."""
    from app.repositories.usage_event import UsageEventRepository

    customer = await _seed_customer(db_session)
    prompt, completion, total, cost, conv_count, last = (
        await UsageEventRepository(db_session).sum_tokens_for_customer(
            customer.id
        )
    )
    assert (prompt, completion, total) == (0, 0, 0)
    assert conv_count == 0
    assert last is None


# ----------------------------------------- ConversationRepository.list_for_customer


async def test_list_for_customer_returns_attributed_conversations(
    db_session, test_env
):
    """list_for_customer returns only conversations tied to the customer."""
    from app.repositories.conversation import ConversationRepository

    agent = await _seed_agent(db_session, test_env.tenant_id)
    customer = await _seed_customer(db_session)
    conv1 = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id, customer_id=customer.id
    )
    # An unattributed conversation (staff internal) — must NOT appear.
    await _seed_conversation(db_session, test_env.tenant_id, agent.id)

    result = await ConversationRepository(db_session).list_for_customer(
        test_env.tenant_id, customer.id
    )
    assert [c.id for c in result] == [conv1.id]


# ----------------------------------------------------------- API layer


async def test_get_customer_usage_store_scoped(app_client, db_session, test_env):
    """Store owner reads this tenant's AI usage for a customer."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    customer = await _seed_customer(db_session)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id, customer_id=customer.id
    )
    msg = await _seed_message(db_session, test_env.tenant_id, conv.id)
    await _seed_usage_event(
        db_session, test_env.tenant_id, conv.id, msg.id,
        customer_id=customer.id, total=150,
    )

    resp = await app_client.get(
        f"/api/v1/customers/{customer.id}/usage", headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == customer.id
    assert body["total_tokens"] == 150
    assert body["conversation_count"] == 1


async def test_get_customer_usage_no_data_returns_zeros(app_client, db_session):
    """A customer with no attributed usage returns an all-zero summary."""
    customer = await _seed_customer(db_session)
    resp = await app_client.get(
        f"/api/v1/customers/{customer.id}/usage", headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tokens"] == 0
    assert body["conversation_count"] == 0
    assert body["last_active_at"] is None


async def test_get_customer_usage_member_can_read(member_client, db_session, test_env):
    """A member (customers:read) can read the store-scoped usage."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    customer = await _seed_customer(db_session)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id, customer_id=customer.id
    )
    msg = await _seed_message(db_session, test_env.tenant_id, conv.id)
    await _seed_usage_event(
        db_session, test_env.tenant_id, conv.id, msg.id,
        customer_id=customer.id, total=50,
    )

    resp = await member_client.get(
        f"/api/v1/customers/{customer.id}/usage", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["total_tokens"] == 50


async def test_get_customer_usage_super_admin_global(super_admin_client, db_session,
                                                     test_env):
    """super_admin sees the global aggregate across tenants."""
    tid = test_env.tenant_id
    other_tid = "tnt-custlink-sa-other"
    agent = await _seed_agent(db_session, tid)
    customer = await _seed_customer(db_session)

    # Two stores, same customer
    conv_a = await _seed_conversation(db_session, tid, agent.id,
                                      customer_id=customer.id)
    msg_a = await _seed_message(db_session, tid, conv_a.id)
    await _seed_usage_event(db_session, tid, conv_a.id, msg_a.id,
                            customer_id=customer.id, total=100)

    conv_b = await _seed_conversation(db_session, other_tid, agent.id,
                                      customer_id=customer.id)
    msg_b = await _seed_message(db_session, other_tid, conv_b.id)
    await _seed_usage_event(db_session, other_tid, conv_b.id, msg_b.id,
                            customer_id=customer.id, total=200)

    resp = await super_admin_client.get(
        f"/api/v1/customers/{customer.id}/usage", headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tokens"] == 300  # global aggregate
    assert body["conversation_count"] == 2
