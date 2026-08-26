"""TurnAccountantService seam unit tests (turn-accountant-sinking).

Direct unit tests at the db_session seam (mirroring test_billing.py's
BillingService direct tests). The HTTP-seam billing cases
(test_usage_tracking.py / test_composite_chat.py) verify the external
behavior but can't see INSIDE the seam — and the paired record→charge
contract is this feature's reason to exist, so we pin it directly:

1. no usage ⇒ no event row, no charge, balance untouched;
2. record failure ⇒ no charge (nothing exists to charge against);
3. charge failure ⇒ the committed UsageEvent row survives (the rollback
   only drops the pending WalletTransaction);
4. happy path ⇒ one event + one consume txn + balance/total_consumed
   debited, for both entry shapes (stream usage dict, composite triple).

The composite entry has no "no usage" state to cover in case 1 — its token
triple is mandatory by signature; its degenerate input (a raise inside the
core) is case 2.
"""

from decimal import Decimal

import pytest

TENANT = "tnt-acct"
USER = "user-acct"


async def _seed_turn(db_session):
    """Agent + Conversation + assistant Message — the FK scaffold one
    UsageEvent row hangs off."""
    from app.models.agent import Agent, Conversation
    from app.models.message import Message

    agent = Agent(
        name="AcctBot", tenant_id=TENANT, system_prompt="hi", model="deepseek-chat"
    )
    db_session.add(agent)
    await db_session.flush()
    conv = Conversation(tenant_id=TENANT, agent_id=agent.id, user_id=USER, title="t")
    db_session.add(conv)
    await db_session.flush()
    msg = Message(conversation_id=conv.id, tenant_id=TENANT, role="assistant",
                  content="hello")
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(conv)
    await db_session.refresh(msg)
    return agent, conv, msg


async def _seed_wallet(db_session, balance: int = 1000):
    from app.models.wallet import Wallet

    w = Wallet(tenant_id=TENANT, balance=balance, total_recharged=balance)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _counts(db_session):
    """(usage_events, consume txns, live wallet) — fresh select, so the
    assertions see committed state rather than the session identity map."""
    from sqlalchemy import select

    from app.models.usage_event import UsageEvent
    from app.models.wallet import Wallet, WalletTransaction

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    txns = (
        await db_session.execute(
            select(WalletTransaction).where(WalletTransaction.type == "consume")
        )
    ).scalars().all()
    wallet = (
        await db_session.execute(select(Wallet).where(Wallet.tenant_id == TENANT))
    ).scalar_one_or_none()
    return events, txns, wallet


# ----------------------------------------------------- 1. no usage ⇒ no-op


@pytest.mark.asyncio
async def test_no_usage_records_nothing_and_charges_nothing(db_session):
    """Guard migrated verbatim from the old ``_record_usage``: no usage
    payload at all, or one whose total_tokens is missing ⇒ no row, no
    charge, balance untouched."""
    from app.services.turn_accountant_service import TurnAccountantService

    agent, conv, msg = await _seed_turn(db_session)
    await _seed_wallet(db_session, balance=1000)

    svc = TurnAccountantService(db_session)
    assert await svc.record_stream_turn(conv, msg, agent.id, USER, None) is None
    assert await svc.record_stream_turn(
        conv,
        msg,
        agent.id,
        USER,
        {"usage": {"input_tokens": 5}, "model": "m"},  # total_tokens missing
    ) is None

    events, txns, wallet = await _counts(db_session)
    assert events == []
    assert txns == []
    assert wallet is not None and wallet.balance == 1000


# --------------------------------------------- 2. record failure ⇒ no charge


@pytest.mark.asyncio
async def test_record_failure_skips_charge(db_session, monkeypatch):
    """A raise inside the UsageEvent insert ⇒ rollback, return None, and the
    wallet is never touched (no event exists to charge against)."""
    from app.repositories.usage_event import UsageEventRepository
    from app.services.turn_accountant_service import TurnAccountantService

    agent, conv, msg = await _seed_turn(db_session)
    await _seed_wallet(db_session, balance=1000)

    async def explode(self, obj):
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr(UsageEventRepository, "add", explode)

    ret = await TurnAccountantService(db_session).record_stream_turn(
        conv,
        msg,
        agent.id,
        USER,
        {"usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
         "model": "m"},
    )
    assert ret is None

    events, txns, wallet = await _counts(db_session)
    assert events == []
    assert txns == []
    assert wallet is not None and wallet.balance == 1000


# --------------------------------- 3. charge failure ⇒ committed event lives


@pytest.mark.asyncio
async def test_charge_failure_keeps_committed_event(db_session, monkeypatch):
    """A raise inside BillingService.charge ⇒ the UsageEvent committed just
    before survives the rollback; only the pending WalletTransaction dies.
    This is the pairing the reconciliation job depends on: the ledger row is
    the authoritative record a missed charge is recovered from."""
    from app.services.billing_service import BillingService
    from app.services.turn_accountant_service import TurnAccountantService

    agent, conv, msg = await _seed_turn(db_session)
    await _seed_wallet(db_session, balance=1000)

    async def explode(self, tenant_id, usage_event, operator_id=None):
        raise RuntimeError("simulated charge failure")

    monkeypatch.setattr(BillingService, "charge", explode)

    ret = await TurnAccountantService(db_session).record_stream_turn(
        conv,
        msg,
        agent.id,
        USER,
        {"usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
         "model": "m"},
    )
    # The event was recorded; the charge is best-effort, so the call still
    # returns the persisted event (test observability).
    assert ret is not None

    events, txns, wallet = await _counts(db_session)
    assert len(events) == 1
    assert events[0].total_tokens == 2
    assert txns == []
    assert wallet is not None and wallet.balance == 1000


# ------------------------------------------------------ 4. paired full chain


@pytest.mark.asyncio
async def test_paired_full_chain_stream_and_composite(db_session):
    """One call = one UsageEvent + one consume txn + balance/total_consumed
    debited — for both entry shapes (stream dict, composite triple)."""
    from app.services.turn_accountant_service import TurnAccountantService

    agent, conv, msg = await _seed_turn(db_session)
    await _seed_wallet(db_session, balance=1000)

    svc = TurnAccountantService(db_session)

    # Stream shape: the aggregated usage dict lands with all its fields.
    ret = await svc.record_stream_turn(
        conv,
        msg,
        agent.id,
        USER,
        {"usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
         "model": "deepseek-chat"},
    )
    assert ret is not None

    events, txns, wallet = await _counts(db_session)
    assert len(events) == 1
    ev = events[0]
    assert ev.tenant_id == TENANT
    assert ev.conversation_id == conv.id
    assert ev.message_id == msg.id
    assert ev.agent_id == agent.id
    assert ev.user_id == USER
    assert ev.model == "deepseek-chat"
    assert ev.prompt_tokens == 12
    assert ev.completion_tokens == 7
    assert ev.total_tokens == 19
    # Unconfigured pricing ⇒ cost stamps 0 (calc_cost's documented default).
    assert ev.cost == Decimal("0")

    assert len(txns) == 1
    txn = txns[0]
    assert txn.amount == -19
    assert txn.balance_after == 1000 - 19
    assert txn.usage_event_id == ev.id
    assert txn.operator_id is None  # consume has no human operator (unchanged)

    assert wallet is not None
    assert wallet.balance == 1000 - 19
    assert wallet.total_consumed == 19

    # Composite shape funnels into the same core (synthesize row: agent_id
    # is None) — the pairing holds for the N+1th row too.
    ret2 = await svc.record_composite_row(
        conv,
        msg,
        None,
        USER,
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
        model="m2",
    )
    assert ret2 is not None

    events, txns, wallet = await _counts(db_session)
    assert len(events) == 2
    synth = next(e for e in events if e.agent_id is None)
    assert synth.total_tokens == 8
    assert synth.model == "m2"
    assert len(txns) == 2
    assert wallet is not None
    assert wallet.balance == 1000 - 19 - 8
    assert wallet.total_consumed == 19 + 8
