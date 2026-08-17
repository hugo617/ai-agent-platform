"""Composite chat (POST /chat/composite) integration tests.

We never hit DeepSeek/OpenAI here. ``composite_query`` (slice 02's fan-out +
synthesize engine) is stubbed via monkeypatch — same pattern ``test_chat.py``
uses for ``stream_agent``. Each test builds its own agents via the agents API,
then asserts the endpoint's HTTP behavior: permission gating, wallet pre-check,
dedup, kind-consistency, persistence, and the N+1 billing ledger.

The fake ``composite_query`` returns the exact dict shape the real one produces
(synthesis / fragments / synthesize_usage / usage_total), so the endpoint's
record + bill path is exercised faithfully without a real LLM call.
"""

from decimal import Decimal

import pytest

AUTH = {"Authorization": "Bearer fake"}


# --------------------------------------------------------------- test helpers


def _fragment(
    agent,
    name: str | None = None,
    *,
    status_: str = "completed",
    in_t: int = 10,
    out_t: int = 5,
    total_t: int = 15,
    model: str = "deepseek-chat",
    snippet: str = "agent reply",
    error: str | None = None,
) -> dict:
    """Build one fragment dict in the shape composite_query returns.

    ``agent`` may be an Agent ORM object (we read .id/.name/.model off it) OR
    a bare id string — both show up in tests (kw["agents"] are ORM objects,
    while helpers sometimes pass the id directly).
    """
    aid = getattr(agent, "id", agent)
    aname = name if name is not None else getattr(agent, "name", "Bot")
    amodel = getattr(agent, "model", model) or model
    return {
        "agent_id": aid,
        "agent_name": aname,
        "snippet": snippet,
        "status": status_,
        "error": error,
        "model": amodel,
        "input_tokens": in_t,
        "output_tokens": out_t,
        "total_tokens": total_t,
    }


def _result(
    fragments: list[dict],
    *,
    synthesis: str = "merged answer",
    synth_in: int = 20,
    synth_out: int = 8,
    synth_total: int = 28,
    synth_model: str = "deepseek-chat",
) -> dict:
    """Build the full composite_query return dict (4 keys)."""
    total_in = sum(f["input_tokens"] for f in fragments) + synth_in
    total_out = sum(f["output_tokens"] for f in fragments) + synth_out
    total_all = sum(f["total_tokens"] for f in fragments) + synth_total
    return {
        "synthesis": synthesis,
        "fragments": fragments,
        "synthesize_usage": {
            "input_tokens": synth_in,
            "output_tokens": synth_out,
            "total_tokens": synth_total,
            "model": synth_model,
        },
        "usage_total": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_all,
        },
    }


async def _make_agent(client, name: str = "Bot") -> str:
    """Create an agent via the API and return its id."""
    resp = await client.post(
        "/api/v1/agents/",
        json={"name": name, "system_prompt": "hi"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _patch_composite(monkeypatch, result_factory):
    """Stub ``composite_query`` in the chat route module.

    ``result_factory`` receives the kwargs dict and returns the composite_query
    result dict, so a test can vary the output by the agents/message passed in
    (e.g. inject failures for specific agents, or assert fan-out parallelism).
    """
    from app.api.v1 import chat as chat_route

    captured: list[dict] = []

    async def fake_composite(**kwargs):
        captured.append(kwargs)
        return result_factory(kwargs)

    monkeypatch.setattr(chat_route, "composite_query", fake_composite)

    # Deterministic effective LLM config (no env/DB dependency).
    from app.schemas.llm_config import EffectiveLlmConfig

    cfg = EffectiveLlmConfig.from_resolved(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        default_model="deepseek-chat",
        available_models=["deepseek-chat", "deepseek-reasoner"],
    )

    async def _resolve(*_args, **_kwargs):
        return cfg

    monkeypatch.setattr(chat_route.llm_config_service, "get_effective", _resolve)
    return captured


async def _seed_wallet(db_session, tenant_id: str, balance: int = 1000):
    """Insert a live wallet for a tenant with the given balance."""
    from app.models.wallet import Wallet

    w = Wallet(tenant_id=tenant_id, balance=balance, total_recharged=balance)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _seed_pricing(db_session, model: str, in_price: Decimal, out_price: Decimal):
    """Insert a platform-default ModelPricing row."""
    from app.models.model_pricing import ModelPricing

    p = ModelPricing(
        model=model,
        input_price_per_1k=in_price,
        output_price_per_1k=out_price,
        is_active=True,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _composite(client, agent_ids: list[str], message: str = "Hi", **extra) -> dict:
    """POST /chat/composite and return {"status": int, "json": dict, "text": str}."""
    body = {"agent_ids": agent_ids, "message": message, **extra}
    resp = await client.post("/api/v1/chat/composite", json=body, headers=AUTH)
    out = {"status": resp.status_code, "text": resp.text}
    try:
        out["json"] = resp.json()
    except ValueError:
        out["json"] = None
    return out


# --------------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_composite_happy_path_3_agents(app_client, db_session, test_env, monkeypatch):
    """3 agents → synthesis + 3 fragments + conversation persisted."""
    # Both chat paths block on no/empty wallet (shared _require_wallet_balance
    # gate), so the happy path needs a funded wallet to clear the pre-check.
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    ids = [await _make_agent(app_client, f"Bot{i}") for i in range(3)]

    def factory(kw):
        return _result([_fragment(a, name=f"Bot{i}") for i, a in enumerate(kw["agents"])])

    _patch_composite(monkeypatch, factory)

    out = await _composite(app_client, ids, message="hello")
    assert out["status"] == 200, out["text"]
    body = out["json"]
    assert body["synthesis"] == "merged answer"
    assert len(body["fragments"]) == 3
    # Conversation is composite-kind; agent_id = agents[0] (lead/attribution).
    conv_id = body["conversation_id"]
    convs = (await app_client.get("/api/v1/conversations/", headers=AUTH)).json()
    conv = next(c for c in convs if c["id"] == conv_id)
    assert conv["kind"] == "composite"
    assert conv["agent_id"] == ids[0]


@pytest.mark.asyncio
async def test_composite_persists_assistant_message_with_fragments(
    app_client, db_session, test_env, monkeypatch
):
    """The synthesized assistant Message carries the fragments JSONB."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    ids = [await _make_agent(app_client, "Bot")]

    def factory(kw):
        return _result([_fragment(ids[0], snippet="agent says hi")])

    _patch_composite(monkeypatch, factory)

    out = await _composite(app_client, ids)
    conv_id = out["json"]["conversation_id"]

    msgs = (
        await app_client.get(
            f"/api/v1/conversations/{conv_id}/messages", headers=AUTH
        )
    ).json()
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant"]
    assistant = msgs[1]
    assert assistant["fragments"] is not None
    assert len(assistant["fragments"]) == 1
    assert assistant["fragments"][0]["snippet"] == "agent says hi"


# --------------------------------------------------------------- failure modes


@pytest.mark.asyncio
async def test_composite_partial_failure_other_agents_succeed(
    app_client, db_session, test_env, monkeypatch
):
    """One agent fails → its fragment is 'failed', others complete, synthesis ok."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    ids = [await _make_agent(app_client, f"Bot{i}") for i in range(3)]

    def factory(kw):
        frags = []
        for i, a in enumerate(kw["agents"]):
            if i == 1:
                frags.append(_fragment(a, name="Bot1", status_="failed", error="boom"))
            else:
                frags.append(_fragment(a, name=f"Bot{i}"))
        return _result(frags)

    _patch_composite(monkeypatch, factory)

    out = await _composite(app_client, ids)
    assert out["status"] == 200, out["text"]
    frags = out["json"]["fragments"]
    statuses = [f["status"] for f in frags]
    assert statuses == ["completed", "failed", "completed"]


@pytest.mark.asyncio
async def test_composite_synthesize_failure_degrades_to_fallback(
    app_client, db_session, test_env, monkeypatch
):
    """When the synthesis itself fails, the endpoint still returns (fallback)."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    ids = [await _make_agent(app_client, "Bot")]

    def factory(kw):
        # Real composite_query degrades to _fallback_synthesis on synth failure;
        # we simulate the degraded output directly.
        return _result(
            [_fragment(ids[0])],
            synthesis="[fallback] agent reply",
            synth_in=0,
            synth_out=0,
            synth_total=0,
        )

    _patch_composite(monkeypatch, factory)

    out = await _composite(app_client, ids)
    assert out["status"] == 200
    assert out["json"]["synthesis"].startswith("[fallback]")


# --------------------------------------------------------------- wallet 402


@pytest.mark.asyncio
async def test_composite_402_when_wallet_balance_zero(app_client, db_session, test_env, monkeypatch):
    """A zero-balance wallet blocks composite with HTTP 402 (project-first)."""
    ids = [await _make_agent(app_client, "Bot")]
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(ids[0])]))

    out = await _composite(app_client, ids)
    assert out["status"] == 402
    assert "余额不足" in out["json"]["detail"]


@pytest.mark.asyncio
async def test_composite_402_when_no_wallet(app_client, test_env, monkeypatch):
    """No wallet at all → 402 (same gate as /chat/stream: has_balance blocks)."""
    ids = [await _make_agent(app_client, "Bot")]
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(ids[0])]))

    out = await _composite(app_client, ids)
    assert out["status"] == 402


@pytest.mark.asyncio
async def test_composite_super_admin_bypasses_wallet(app_client, db_session, test_env, monkeypatch):
    """super_admin skips the wallet pre-check even with zero balance."""
    ids = [await _make_agent(app_client, "Bot")]
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)

    from app.models.tenant import User

    async with test_env.factory() as session:
        user = await session.get(User, test_env.owner_user)
        if user is not None:
            user.platform_role = "super_admin"
            await session.commit()

    _patch_composite(monkeypatch, lambda kw: _result([_fragment(ids[0])]))
    out = await _composite(app_client, ids)
    assert out["status"] == 200, out["text"]


# --------------------------------------------------------------- permissions


@pytest.mark.asyncio
async def test_composite_403_without_chat_permission(app_client, test_env, monkeypatch):
    """A subject without conversations:chat → 403 (router-level Depends fires).

    The default owner/member roles both grant conversations:chat, so we
    temporarily strip it from the owner's role policy and restore it after
    the assertion (the enforcer is a shared singleton across the test session).
    """
    ids = [await _make_agent(app_client, "Bot")]
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(ids[0])]))

    # Strip conversations:chat from the owner role → the router-level Depends
    # fires before Pass 1 even runs. Restored in the finally below so the
    # shared enforcer stays clean for subsequent tests. Policy subject is the
    # bare role code "owner" (not "role:owner") — see permission_service seed.
    pol = ("owner", test_env.tenant_id, "conversations", "chat")
    test_env.enforcer.remove_policy(*pol)
    try:
        out = await _composite(app_client, ids)
        assert out["status"] == 403
    finally:
        test_env.enforcer.add_policy(*pol)


# --------------------------------------------------------------- resolution 404


@pytest.mark.asyncio
async def test_composite_404_cross_tenant_agent(app_client, db_session, monkeypatch):
    """An agent_id from another tenant → 404 (no existence leak)."""
    from app.models.agent import Agent
    from app.models.tenant import Tenant

    other = "tnt-xchat-1"
    db_session.add(Tenant(id=other, name="Other"))
    leaked = Agent(tenant_id=other, name="spy", model="deepseek-chat")
    db_session.add(leaked)
    await db_session.commit()

    own = await _make_agent(app_client, "Bot")
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(own)]))

    out = await _composite(app_client, [own, leaked.id])
    assert out["status"] == 404


@pytest.mark.asyncio
async def test_composite_404_soft_deleted_agent(app_client, db_session, monkeypatch):
    """A soft-deleted agent → 404 (get_for_tenant filters is_deleted)."""
    own = await _make_agent(app_client, "Bot")
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(own)]))

    # Soft-delete the agent directly (the API DELETE also soft-deletes).
    from sqlalchemy import select

    from app.models.agent import Agent

    agent = (
        await db_session.execute(select(Agent).where(Agent.id == own))
    ).scalar_one()
    agent.is_deleted = True
    await db_session.commit()

    out = await _composite(app_client, [own])
    assert out["status"] == 404


# --------------------------------------------------------------- validation


@pytest.mark.asyncio
async def test_composite_dedups_repeated_agent_ids(app_client, db_session, test_env, monkeypatch):
    """Repeated agent_ids fan out once (no duplicated fragment, no double charge)."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    own = await _make_agent(app_client, "Bot")

    captured = _patch_composite(
        monkeypatch, lambda kw: _result([_fragment(a) for a in kw["agents"]])
    )

    out = await _composite(app_client, [own, own, own])
    assert out["status"] == 200, out["text"]
    # composite_query received exactly ONE agent (de-duped before fan-out).
    assert len(captured[0]["agents"]) == 1
    assert len(out["json"]["fragments"]) == 1


@pytest.mark.asyncio
async def test_composite_422_too_many_agents(app_client, monkeypatch):
    """More than 8 agent_ids → 422 (Pydantic max_length)."""
    ids = [await _make_agent(app_client, f"B{i}") for i in range(9)]
    _patch_composite(monkeypatch, lambda kw: _result([]))

    out = await _composite(app_client, ids)
    assert out["status"] == 422


@pytest.mark.asyncio
async def test_composite_422_empty_agent_ids(app_client, monkeypatch):
    """An empty agent_ids list → 422 (Pydantic min_length)."""
    _patch_composite(monkeypatch, lambda kw: _result([]))
    out = await _composite(app_client, [])
    assert out["status"] == 422


# --------------------------------------------------------------- resume / kind


@pytest.mark.asyncio
async def test_composite_resume_single_conversation_404(app_client, db_session, test_env, monkeypatch):
    """Resuming a single-kind conversation as composite → 404 (H2 guard)."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    own = await _make_agent(app_client, "Bot")
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(own)]))

    # Create a composite conversation, then flip its kind to "single" to
    # simulate a legacy single-agent chat being resumed as composite.
    out = await _composite(app_client, [own])
    composite_conv_id = out["json"]["conversation_id"]

    from sqlalchemy import update

    from app.models.agent import Conversation

    await db_session.execute(
        update(Conversation)
        .where(Conversation.id == composite_conv_id)
        .values(kind="single")
    )
    await db_session.commit()

    # Now try to resume it as composite → kind mismatch → 404.
    out2 = await _composite(app_client, [own], conversation_id=composite_conv_id)
    assert out2["status"] == 404


@pytest.mark.asyncio
async def test_composite_resume_composite_conversation_ok(app_client, db_session, test_env, monkeypatch):
    """Resuming a composite conversation as composite → 200 (same kind)."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    own = await _make_agent(app_client, "Bot")
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(own)]))

    first = await _composite(app_client, [own])
    conv_id = first["json"]["conversation_id"]

    second = await _composite(app_client, [own], conversation_id=conv_id)
    assert second["status"] == 200, second["text"]
    assert second["json"]["conversation_id"] == conv_id


# --------------------------------------------------------------- billing


@pytest.mark.asyncio
async def test_composite_records_n_plus_1_usage_events(app_client, db_session, test_env, monkeypatch):
    """3 agents → 4 UsageEvents (3 fragments + 1 synthesize), tokens = usage_total."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    ids = [await _make_agent(app_client, f"Bot{i}") for i in range(3)]
    _patch_composite(
        monkeypatch,
        lambda kw: _result([_fragment(a, in_t=10, out_t=5, total_t=15) for a in kw["agents"]]),
    )

    out = await _composite(app_client, ids)
    conv_id = out["json"]["conversation_id"]

    from sqlalchemy import select

    from app.models.usage_event import UsageEvent

    events = (
        await db_session.execute(
            select(UsageEvent).where(UsageEvent.conversation_id == conv_id)
        )
    ).scalars().all()
    # N fragments + 1 synthesize row.
    assert len(events) == 4
    # The synthesize row has agent_id = None; the 3 fragment rows carry agents.
    assert sum(1 for e in events if e.agent_id is None) == 1
    # Total tokens across all rows = usage_total.total_tokens (15*3 + 28 = 73).
    assert sum(e.total_tokens for e in events) == 73


@pytest.mark.asyncio
async def test_composite_customer_id_propagated_to_usage_events(
    app_client, db_session, test_env, monkeypatch
):
    """A composite turn with customer_id → all N+1 UsageEvents carry it."""
    from app.models.customer import Customer, CustomerProfile

    # Customer is platform-level (no tenant_id); CustomerProfile carries the
    # tenant binding. We need a profile so the customer is "in" this tenant.
    cust = Customer(identity_key="comp-cust-1", name="测试客户")
    db_session.add(cust)
    await db_session.flush()
    db_session.add(
        CustomerProfile(customer_id=cust.id, tenant_id=test_env.tenant_id, status="active")
    )
    await db_session.commit()
    await _seed_wallet(db_session, test_env.tenant_id, balance=1000)

    ids = [await _make_agent(app_client, f"Bot{i}") for i in range(2)]
    _patch_composite(monkeypatch, lambda kw: _result([_fragment(a) for a in kw["agents"]]))

    out = await _composite(app_client, ids, customer_id=cust.id)
    conv_id = out["json"]["conversation_id"]

    from sqlalchemy import select

    from app.models.usage_event import UsageEvent

    events = (
        await db_session.execute(
            select(UsageEvent).where(UsageEvent.conversation_id == conv_id)
        )
    ).scalars().all()
    assert len(events) == 3  # 2 fragments + 1 synthesize
    assert all(e.customer_id == cust.id for e in events), {
        e.customer_id for e in events
    }


@pytest.mark.asyncio
async def test_composite_charge_tolerance_one_row_failure(
    app_client, db_session, test_env, monkeypatch
):
    """If the 2nd charge throws, rows 1/3/4 still persist (best-effort, H4)."""
    ids = [await _make_agent(app_client, f"Bot{i}") for i in range(3)]
    await _seed_wallet(db_session, test_env.tenant_id, balance=100000)
    await _seed_pricing(db_session, "deepseek-chat", Decimal("1"), Decimal("1"))

    _patch_composite(
        monkeypatch,
        lambda kw: _result([_fragment(a, in_t=10, out_t=5, total_t=15) for a in kw["agents"]]),
    )

    # Make the 2nd charge (the 2nd fragment's charge) raise. We patch
    # BillingService.charge directly (the endpoint calls it via _charge_usage);
    # the real charge runs for every other row.
    from app.services.billing_service import BillingService

    real_charge = BillingService.charge
    call_count = {"n": 0}

    async def flaky_charge(self, tenant_id, usage_event, operator_id=None):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated charge failure on row 2")
        return await real_charge(self, tenant_id, usage_event, operator_id)

    monkeypatch.setattr(BillingService, "charge", flaky_charge)

    out = await _composite(app_client, ids)
    assert out["status"] == 200, out["text"]
    conv_id = out["json"]["conversation_id"]

    from sqlalchemy import select

    from app.models.usage_event import UsageEvent

    events = (
        await db_session.execute(
            select(UsageEvent).where(UsageEvent.conversation_id == conv_id)
        )
    ).scalars().all()
    # All 4 UsageEvents persist (the ledger is best-effort; a charge failure
    # rolls back only the WalletTransaction, not the committed UsageEvent).
    assert len(events) == 4
    # The charge path was actually invoked 4 times (N+1).
    assert call_count["n"] == 4
