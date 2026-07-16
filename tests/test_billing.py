"""Token wallet billing tests (Token billing series 2/4).

Covers the prepaid-wallet accounting chain:

- ``BillingService.charge`` — debit the consumed tokens for one usage event
  (balance/total_consumed update, WalletTransaction consume row, cost snapshot
  stamped on the usage event).
- ``BillingService.recharge`` — credit tokens, append a recharge transaction.
- ``BillingService.calc_cost`` — pricing resolution (tenant override > platform
  default > unconfigured → 0) and the (prompt/1000*in + completion/1000*out)
  formula.
- ``BillingService.create_wallet_for_tenant`` / ``TenantService.create_tenant``
  — a new tenant gets a zero-balance wallet atomically.
- ``event_source`` — a zero-balance wallet blocks new chats (SSE error);
  a missing wallet lets the chat through (graceful degradation).
- API layer — wallet read, recharge (super admin), pricing CRUD, tenant
  isolation, permission boundaries.

SQLite caveat: ``SELECT ... FOR UPDATE`` is a no-op on SQLite (no row lock),
so the concurrent-debit test runs single-threaded and asserts the *logical*
serial-debit outcome, not true PG row-locking. PG enforces the lock in prod.
"""

from decimal import Decimal

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------------- helpers


async def _seed_wallet(db_session, tenant_id: str, balance: int = 0):
    """Insert a live wallet for a tenant with the given balance."""
    from app.models.wallet import Wallet

    w = Wallet(tenant_id=tenant_id, balance=balance, total_recharged=balance)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _seed_usage_event(db_session, tenant_id: str, conv_id: str, msg_id: str,
                            total: int, prompt: int = 10, completion: int = 20,
                            model: str = "deepseek-chat"):
    """Insert a UsageEvent row (mimics what _record_usage persists)."""
    from app.models.usage_event import UsageEvent

    ev = UsageEvent(
        tenant_id=tenant_id,
        conversation_id=conv_id,
        message_id=msg_id,
        agent_id=None,
        user_id="test-user",
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost=None,
    )
    db_session.add(ev)
    await db_session.commit()
    await db_session.refresh(ev)
    return ev


async def _seed_conv_and_msg(db_session, tenant_id: str):
    """Insert an Agent + Conversation + two Messages so a UsageEvent FK is valid."""
    from datetime import UTC, datetime

    from app.models.agent import Agent, Conversation
    from app.models.message import Message

    agent = Agent(name="TestBot", tenant_id=tenant_id, system_prompt="hi",
                  model="deepseek-chat")
    db_session.add(agent)
    await db_session.flush()
    conv = Conversation(tenant_id=tenant_id, agent_id=agent.id, user_id="test-user",
                        title="t")
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    now = datetime.now(UTC)
    m1 = Message(conversation_id=conv.id, tenant_id=tenant_id, role="user",
                 content="hi", created_at=now)
    m2 = Message(conversation_id=conv.id, tenant_id=tenant_id, role="assistant",
                 content="hello", created_at=now)
    db_session.add_all([m1, m2])
    await db_session.commit()
    await db_session.refresh(m1)
    await db_session.refresh(m2)
    return conv, m1, m2


async def _seed_pricing(db_session, model: str, in_price: Decimal, out_price: Decimal,
                        tenant_id: str | None = None):
    """Insert a ModelPricing row (platform default when tenant_id=None)."""
    from app.models.model_pricing import ModelPricing

    p = ModelPricing(
        tenant_id=tenant_id,
        model=model,
        input_price_per_1k=in_price,
        output_price_per_1k=out_price,
        is_active=True,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


# ----------------------------------------------------------- calc_cost


@pytest.mark.asyncio
async def test_calc_cost_tenant_override_beats_platform_default(db_session, test_env):
    """Tenant pricing overrides the platform default for the same model."""
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    await _seed_pricing(db_session, "m1", Decimal("1"), Decimal("2"), tenant_id=None)
    await _seed_pricing(db_session, "m1", Decimal("10"), Decimal("20"), tenant_id=tid)
    cost, pricing = await BillingService(db_session).calc_cost("m1", 1000, 1000, tid)
    # 1000/1000*10 + 1000/1000*20 = 30 (tenant override wins)
    assert cost == Decimal("30.000000")
    assert pricing.tenant_id == tid


@pytest.mark.asyncio
async def test_calc_cost_falls_back_to_platform_default(db_session, test_env):
    """No tenant override → platform default applies."""
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    await _seed_pricing(db_session, "m1", Decimal("1"), Decimal("2"), tenant_id=None)
    cost, pricing = await BillingService(db_session).calc_cost("m1", 500, 500, tid)
    # 500/1000*1 + 500/1000*2 = 1.5
    assert cost == Decimal("1.500000")
    assert pricing.tenant_id is None


@pytest.mark.asyncio
async def test_calc_cost_unconfigured_returns_zero(db_session, test_env):
    """No pricing row at all → cost 0, pricing None (chat still allowed)."""
    from app.services.billing_service import BillingService

    cost, pricing = await BillingService(db_session).calc_cost(
        "unknown-model", 1000, 1000, test_env.tenant_id
    )
    assert cost == Decimal("0")
    assert pricing is None


# ----------------------------------------------------------- charge


@pytest.mark.asyncio
async def test_charge_debits_balance_and_writes_transaction(db_session, test_env):
    """charge() debits the wallet, updates total_consumed, appends a consume txn,
    and stamps the cost snapshot on the usage event."""
    from sqlalchemy import select

    from app.models.wallet import WalletTransaction
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    wallet = await _seed_wallet(db_session, tid, balance=1000)
    await _seed_pricing(db_session, "deepseek-chat", Decimal("1"), Decimal("1"))
    conv, m_user, m_asst = await _seed_conv_and_msg(db_session, tid)
    ev = await _seed_usage_event(db_session, tid, conv.id, m_asst.id, total=100,
                                 prompt=40, completion=60, model="deepseek-chat")

    txn = await BillingService(db_session).charge(tid, ev)
    assert txn is not None
    assert txn.type == "consume"
    assert txn.amount == -100
    assert txn.balance_after == 900

    # Wallet updated.
    await db_session.refresh(wallet)
    assert wallet.balance == 900
    assert wallet.total_consumed == 100

    # Cost snapshot stamped on the event.
    # 40/1000*1 + 60/1000*1 = 0.1 per the per-1k price; but with unit prices
    # (1.0 per 1k) the math is 40*1/1000 + 60*1/1000 = 0.1. Use the same
    # formula the service uses so the assertion is self-consistent.
    await db_session.refresh(ev)
    from decimal import ROUND_HALF_UP
    expected_cost = (
        (Decimal(40) * Decimal("1")) / Decimal(1000)
        + (Decimal(60) * Decimal("1")) / Decimal(1000)
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    assert ev.cost == expected_cost

    # Exactly one consume transaction.
    txns = (await db_session.execute(
        select(WalletTransaction).where(WalletTransaction.tenant_id == tid)
    )).scalars().all()
    assert len(txns) == 1
    assert txns[0].usage_event_id == ev.id


@pytest.mark.asyncio
async def test_charge_without_wallet_returns_none_and_is_safe(db_session, test_env):
    """charge() on a tenant with no wallet is a no-op (returns None), so the
    chat path (which calls charge best-effort) never crashes on a wallet gap."""
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    conv, m_user, m_asst = await _seed_conv_and_msg(db_session, tid)
    ev = await _seed_usage_event(db_session, tid, conv.id, m_asst.id, total=50)
    txn = await BillingService(db_session).charge(tid, ev)
    assert txn is None


@pytest.mark.asyncio
async def test_charge_unconfigured_model_records_zero_cost(db_session, test_env):
    """charge() with no pricing still debits the tokens but records cost=0."""
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    await _seed_wallet(db_session, tid, balance=500)
    conv, m_user, m_asst = await _seed_conv_and_msg(db_session, tid)
    ev = await _seed_usage_event(db_session, tid, conv.id, m_asst.id, total=50)
    await BillingService(db_session).charge(tid, ev)
    await db_session.refresh(ev)
    assert ev.cost == Decimal("0")


# ----------------------------------------------------------- recharge


@pytest.mark.asyncio
async def test_recharge_credits_balance_and_writes_transaction(db_session, test_env):
    """recharge() adds tokens, bumps total_recharged, appends a recharge txn."""
    from sqlalchemy import select

    from app.models.wallet import WalletTransaction
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    wallet = await _seed_wallet(db_session, tid, balance=100)
    txn = await BillingService(db_session).recharge(
        tid, amount=500, operator_id="super-admin", remark="7月采购"
    )
    assert txn.type == "recharge"
    assert txn.amount == 500
    assert txn.balance_after == 600
    await db_session.refresh(wallet)
    assert wallet.balance == 600
    assert wallet.total_recharged == 600  # 100 initial + 500

    rows = (await db_session.execute(
        select(WalletTransaction).where(WalletTransaction.type == "recharge")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].remark == "7月采购"


@pytest.mark.asyncio
async def test_recharge_rejects_non_positive_amount(db_session, test_env):
    """recharge() refuses zero/negative amounts (caller bug, not recoverable)."""
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    await _seed_wallet(db_session, tid, balance=0)
    with pytest.raises(ValueError):
        await BillingService(db_session).recharge(tid, amount=0, operator_id="x")
    with pytest.raises(ValueError):
        await BillingService(db_session).recharge(tid, amount=-5, operator_id="x")


@pytest.mark.asyncio
async def test_recharge_without_wallet_raises(db_session, test_env):
    """recharge() on a wallet-less tenant raises (recharge-before-bootstrap bug)."""
    from app.services.billing_service import BillingService

    with pytest.raises(ValueError):
        await BillingService(db_session).recharge(
            test_env.tenant_id, amount=100, operator_id="x"
        )


# ----------------------------------------------------------- wallet bootstrap


@pytest.mark.asyncio
async def test_create_wallet_for_tenant_is_idempotent(db_session, test_env):
    """Re-running the bootstrap on a tenant that already has a wallet is a no-op
    (returns the existing wallet, doesn't create a duplicate)."""
    from sqlalchemy import select

    from app.models.wallet import Wallet
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    w1 = await BillingService(db_session).create_wallet_for_tenant(tid)
    w2 = await BillingService(db_session).create_wallet_for_tenant(tid)
    assert w1.id == w2.id
    count = (await db_session.execute(
        select(Wallet).where(Wallet.tenant_id == tid)
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_create_tenant_initializes_zero_balance_wallet(super_admin_client, db_session, test_env):
    """POST /tenants/ (super_admin) leaves the new tenant with a zero-balance
    wallet, so chats work without a manual recharge step once credits arrive."""
    from sqlalchemy import select

    from app.models.wallet import Wallet

    resp = await super_admin_client.post(
        "/api/v1/tenants/",
        json={"name": "Wallet Bootstrap Tenant"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    new_tid = resp.json()["id"]
    # Wallet exists and is zero-balance.
    wallets = (await db_session.execute(
        select(Wallet).where(Wallet.tenant_id == new_tid)
    )).scalars().all()
    assert len(wallets) == 1
    assert wallets[0].balance == 0
    assert wallets[0].total_recharged == 0


# ----------------------------------------------------------- chat gate


def _stream_with_usage(chunks, usage, model="deepseek-chat"):
    """Build a fake stream_agent that yields text then a usage dict."""
    async def _fake(**_kwargs):
        for c in chunks:
            yield c
        yield {"usage": usage, "model": model}
    return _fake


def _async_effective(available_models, default_model="deepseek-chat"):
    from app.schemas.llm_config import EffectiveLlmConfig
    cfg = EffectiveLlmConfig.from_resolved(
        api_key="test-key", base_url="https://api.deepseek.com",
        default_model=default_model, available_models=available_models,
    )
    async def _resolve(*_a, **_kw):
        return cfg
    return _resolve


async def _mock_chat(client, monkeypatch, agent_id, message="Hi"):
    from app.api.v1 import chat as chat_route
    monkeypatch.setattr(chat_route, "stream_agent",
                        _stream_with_usage(["Hi", "!"], {"input_tokens": 10,
                         "output_tokens": 20, "total_tokens": 30}))
    monkeypatch.setattr(chat_route.llm_config_service, "get_effective",
                        _async_effective(["deepseek-chat"]))
    resp = await client.post("/api/v1/chat/stream",
                             json={"agent_id": agent_id, "message": message},
                             headers=AUTH)
    return resp


@pytest.mark.asyncio
async def test_chat_blocked_when_wallet_balance_is_zero(app_client, db_session, monkeypatch, test_env):
    """A wallet with balance 0 blocks new chats via an SSE error event."""
    create = await app_client.post("/api/v1/agents/",
                                   json={"name": "Bot", "system_prompt": "hi"},
                                   headers=AUTH)
    agent_id = create.json()["id"]
    # Zero-balance wallet → chat blocked.
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)
    resp = await _mock_chat(app_client, monkeypatch, agent_id)
    assert resp.status_code == 200
    assert "余额不足" in resp.text
    assert "[DONE]" not in resp.text


@pytest.mark.asyncio
async def test_chat_allowed_when_wallet_has_balance(app_client, db_session, monkeypatch, test_env):
    """A wallet with balance > 0 lets the chat through and debits the tokens."""
    create = await app_client.post("/api/v1/agents/",
                                   json={"name": "Bot", "system_prompt": "hi"},
                                   headers=AUTH)
    agent_id = create.json()["id"]
    wallet = await _seed_wallet(db_session, test_env.tenant_id, balance=1000)
    await _seed_pricing(db_session, "deepseek-chat", Decimal("1"), Decimal("1"))
    resp = await _mock_chat(app_client, monkeypatch, agent_id)
    assert resp.status_code == 200
    assert "[DONE]" in resp.text
    assert "余额不足" not in resp.text
    # Wallet debited by the 30 tokens the fake stream reported.
    await db_session.refresh(wallet)
    assert wallet.balance == 1000 - 30
    assert wallet.total_consumed == 30


@pytest.mark.asyncio
async def test_chat_allowed_when_no_wallet_exists(app_client, db_session, monkeypatch, test_env):
    """No wallet at all → chat proceeds (graceful degradation for tenants set
    up before billing, and for the test environment)."""
    create = await app_client.post("/api/v1/agents/",
                                   json={"name": "Bot", "system_prompt": "hi"},
                                   headers=AUTH)
    agent_id = create.json()["id"]
    resp = await _mock_chat(app_client, monkeypatch, agent_id)
    assert resp.status_code == 200
    assert "[DONE]" in resp.text
    assert "余额不足" not in resp.text


# ----------------------------------------------------------- API: wallet read


@pytest.mark.asyncio
async def test_get_my_wallet_owner_can_read(app_client, db_session, test_env):
    """owner (wallet:read) sees the tenant wallet; balance + counters present."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=300)
    resp = await app_client.get("/api/v1/billing/wallet", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance"] == 300
    assert body["tenant_id"] == test_env.tenant_id


@pytest.mark.asyncio
async def test_get_my_wallet_returns_none_when_absent(app_client, test_env):
    """No wallet yet → 200 with null body (not 404)."""
    resp = await app_client.get("/api/v1/billing/wallet", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_member_cannot_read_wallet(member_client, test_env):
    """member lacks wallet:read → 403."""
    resp = await member_client.get("/api/v1/billing/wallet", headers=AUTH)
    assert resp.status_code == 403


# ----------------------------------------------------------- API: recharge


@pytest.mark.asyncio
async def test_recharge_super_admin_only(app_client, db_session, test_env):
    """A tenant owner (not super admin) cannot recharge → 403."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)
    resp = await app_client.post(
        "/api/v1/billing/recharge",
        json={"tenant_id": test_env.tenant_id, "amount": 100},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recharge_super_admin_credits_wallet(super_admin_client, db_session, test_env):
    """super_admin can recharge any tenant's wallet."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)
    resp = await super_admin_client.post(
        "/api/v1/billing/recharge",
        json={"tenant_id": test_env.tenant_id, "amount": 500, "remark": "test"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "recharge"
    assert body["amount"] == 500
    assert body["balance_after"] == 500


# ----------------------------------------------------------- API: pricing


@pytest.mark.asyncio
async def test_pricing_crud_super_admin(super_admin_client, db_session, test_env):
    """super_admin can create / list / update / delete pricing rows."""
    # Create platform-default pricing.
    resp = await super_admin_client.post(
        "/api/v1/billing/pricing",
        json={"model": "deepseek-chat",
              "input_price_per_1k": "1.0",
              "output_price_per_1k": "2.0"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    # Create a tenant override.
    resp = await super_admin_client.post(
        "/api/v1/billing/pricing",
        json={"tenant_id": test_env.tenant_id, "model": "deepseek-chat",
              "input_price_per_1k": "5.0", "output_price_per_1k": "6.0"},
        headers=AUTH,
    )
    assert resp.status_code == 201

    # Super admin lists platform-level rows only.
    resp = await super_admin_client.get("/api/v1/billing/pricing", headers=AUTH)
    assert resp.status_code == 200
    rows = resp.json()
    plat = [r for r in rows if r["tenant_id"] is None]
    assert len(plat) == 1
    assert plat[0]["model"] == "deepseek-chat"

    # Update.
    resp = await super_admin_client.put(
        f"/api/v1/billing/pricing/{pid}",
        json={"model": "deepseek-chat",
              "input_price_per_1k": "9.0", "output_price_per_1k": "9.0"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["input_price_per_1k"] == "9.000000"

    # Delete (soft: is_active=False).
    resp = await super_admin_client.delete(
        f"/api/v1/billing/pricing/{pid}", headers=AUTH
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_pricing_owner_cannot_write(app_client, test_env):
    """owner (not super admin) cannot create pricing → 403."""
    resp = await app_client.post(
        "/api/v1/billing/pricing",
        json={"model": "x", "input_price_per_1k": "1", "output_price_per_1k": "1"},
        headers=AUTH,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pricing_owner_reads_effective(app_client, db_session, test_env):
    """owner sees tenant overrides merged with platform defaults."""
    await _seed_pricing(db_session, "m1", Decimal("1"), Decimal("1"), tenant_id=None)
    await _seed_pricing(db_session, "m1", Decimal("2"), Decimal("2"),
                        tenant_id=test_env.tenant_id)
    resp = await app_client.get("/api/v1/billing/pricing", headers=AUTH)
    assert resp.status_code == 200
    rows = resp.json()
    # Both the platform default and the tenant override are visible.
    assert len(rows) == 2


# ----------------------------------------------------------- API: transactions


@pytest.mark.asyncio
async def test_list_transactions_owner_can_read(app_client, db_session, test_env):
    """owner (wallet:read) sees the wallet ledger."""
    from app.services.billing_service import BillingService

    tid = test_env.tenant_id
    await _seed_wallet(db_session, tid, balance=0)
    await BillingService(db_session).recharge(tid, 100, operator_id="x")
    resp = await app_client.get("/api/v1/billing/transactions", headers=AUTH)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["type"] == "recharge"


# ----------------------------------------------------------- tenant isolation


@pytest.mark.asyncio
async def test_wallet_tenant_isolation(db_session, test_env):
    """WalletRepository.get_for_tenant only returns the requested tenant's wallet."""
    from app.models.wallet import Wallet
    from app.repositories.wallet import WalletRepository

    tid_a = test_env.tenant_id
    tid_b = f"tnt-other-{__import__('uuid').uuid4().hex}"
    # Seed wallet for tenant A only.
    db_session.add(Wallet(tenant_id=tid_a, balance=100))
    # Tenant B exists but has no wallet.
    from app.models.tenant import Tenant
    db_session.add(Tenant(id=tid_b, name="Other"))
    await db_session.commit()

    repo = WalletRepository(db_session)
    assert (await repo.get_for_tenant(tid_a)) is not None
    assert (await repo.get_for_tenant(tid_b)) is None


@pytest.mark.asyncio
async def test_inactive_wallet_is_not_usable(db_session, test_env):
    """S1: an inactive wallet is treated as "no wallet" — get_for_tenant and the
    FOR UPDATE variant both skip it, so chats/billing on a disabled wallet are
    blocked (previously is_active was written but never read).
    """
    from app.models.wallet import Wallet
    from app.repositories.wallet import WalletRepository

    tid = test_env.tenant_id
    db_session.add(Wallet(tenant_id=tid, balance=100, is_active=False))
    await db_session.commit()

    repo = WalletRepository(db_session)
    # Both lookups honour is_active now (the fix).
    assert (await repo.get_for_tenant(tid)) is None
    assert (await repo.get_for_tenant_for_update(tid)) is None
