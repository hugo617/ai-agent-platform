"""Reconciliation job tests (billing-reconciliation-job slice 01).

Direct-call paradigm mirroring ``scan_balance_warnings``'s test
(tests/test_notifications.py): build a session factory bound to the same
StaticPool test engine, seed rows via ``db_session``, then call
``BillingReconciliationService.run`` with an explicit ``as_of`` — no cron
wait, no app client. Assertions only touch externally observable state: the
returned report dict and the SystemLog rows the run appends.

Time is fully pinned: ``as_of`` is a fixed aware datetime and every seeded
row carries an explicit ``created_at`` relative to it, so the 30-minute
lookback buffer is exercised at exact boundaries (−5min = shielded,
−31min = judged).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.billing_reconciliation_service import (
    BillingReconciliationService,
)

# Fixed judgment baseline (09:30, the production cron slot) and derived
# window anchors. cutoff = as_of − 30min (D9 buffer, single constant source).
AS_OF = datetime(2026, 8, 17, 9, 30, tzinfo=UTC)
OLD_AT = AS_OF - timedelta(minutes=31)  # 08:59 — outside the buffer, judged
FRESH_AT = AS_OF - timedelta(minutes=5)  # 09:25 — in-flight window, shielded
DAY2_AS_OF = AS_OF + timedelta(days=1)  # next calendar day (no skip lock)
DAY2_OLD_AT = DAY2_AS_OF - timedelta(minutes=31)


# ----------------------------------------------------------- helpers


@pytest.fixture
def factory(db_session):
    """Session factory on the test engine (StaticPool single connection)."""
    return async_sessionmaker(db_session.bind, expire_on_commit=False)


async def _run(factory, as_of: datetime, *, force: bool = False) -> dict:
    """Invoke the service the way the scheduler shell does."""
    async with factory() as db:
        return await BillingReconciliationService(db).run(as_of, force=force)


async def _fetch_run_records(db_session) -> list:
    """All reconciliation run records, oldest first."""
    from app.models.log import SystemLog

    res = await db_session.execute(
        select(SystemLog)
        .where(SystemLog.action == "billing_reconciliation")
        .order_by(SystemLog.created_at, SystemLog.id)
    )
    return list(res.scalars().all())


async def _seed_tenant(db_session, tenant_id: str):
    from app.models.tenant import Tenant

    db_session.add(Tenant(id=tenant_id, name=f"recon-{tenant_id}"))
    await db_session.commit()


async def _seed_wallet(db_session, tenant_id: str, balance: int = 0):
    """Insert a live wallet whose counters match its balance (consistent)."""
    from app.models.wallet import Wallet

    w = Wallet(tenant_id=tenant_id, balance=balance, total_recharged=balance)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _seed_conv_and_msg(db_session, tenant_id: str):
    """Insert an Agent + Conversation + two Messages so UsageEvent FKs hold."""
    from app.models.agent import Agent, Conversation
    from app.models.message import Message

    agent = Agent(
        name="ReconBot",
        tenant_id=tenant_id,
        system_prompt="hi",
        model="deepseek-chat",
    )
    db_session.add(agent)
    await db_session.flush()
    conv = Conversation(tenant_id=tenant_id, agent_id=agent.id, user_id="test-user", title="t")
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    now = datetime.now(UTC)
    m1 = Message(
        conversation_id=conv.id,
        tenant_id=tenant_id,
        role="user",
        content="hi",
        created_at=now,
    )
    m2 = Message(
        conversation_id=conv.id,
        tenant_id=tenant_id,
        role="assistant",
        content="hello",
        created_at=now,
    )
    db_session.add_all([m1, m2])
    await db_session.commit()
    await db_session.refresh(m1)
    await db_session.refresh(m2)
    return conv, m1, m2


async def _seed_usage_event(
    db_session,
    tenant_id: str,
    conv_id: str,
    msg_id: str,
    total: int,
    created_at: datetime,
    prompt: int = 10,
    completion: int = 20,
    model: str = "deepseek-chat",
):
    """Insert a UsageEvent row at an explicit point in time."""
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
        created_at=created_at,
    )
    db_session.add(ev)
    await db_session.commit()
    await db_session.refresh(ev)
    return ev


async def _charge_and_pin(db_session, tenant_id: str, ev) -> None:
    """Run the REAL charge chain, then pin the ledger timestamp.

    ``charge()`` stamps ``created_at`` with the server's real clock, which is
    unrelated to the fixed test ``as_of``; pinning it just after the event
    keeps the aggregate layer's window deterministic while still proving the
    genuine charge transaction satisfies the event-level NOT EXISTS check.
    """
    from app.services.billing_service import BillingService

    tx = await BillingService(db_session).charge(tenant_id, ev)
    assert tx is not None  # wallet must exist for the full chain
    tx.created_at = ev.created_at + timedelta(seconds=1)
    await db_session.commit()


# ----------------------------------------------------- case 2: zero false positives


@pytest.mark.asyncio
async def test_clean_run_writes_single_info_record(db_session, factory, test_env):
    """Case 2 — a fully-charged chain reconciles clean: exactly one run
    record at level=info, a discrepancy-free report, no skip."""
    conv, _, m2 = await _seed_conv_and_msg(db_session, test_env.tenant_id)
    await _seed_wallet(db_session, test_env.tenant_id, balance=1_000)
    ev = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=100,
        created_at=OLD_AT,
    )
    await _charge_and_pin(db_session, test_env.tenant_id, ev)

    report = await _run(factory, AS_OF)

    assert report["skipped"] is False
    assert report["has_discrepancy"] is False
    stats = report["stats"]
    assert stats["tenants_checked"] == 1
    assert stats["events_scanned"] == 1
    assert stats["new_alerted_count"] == 0
    assert stats["existing_unhandled_count"] == 0
    assert stats["residual_tenants"] == 0
    assert stats["wallet_drift_count"] == 0

    rows = await _fetch_run_records(db_session)
    assert len(rows) == 1
    assert rows[0].level == "info"
    assert rows[0].action == "billing_reconciliation"
    assert rows[0].details_json["as_of"] == AS_OF.isoformat()


# ----------------------------------------------------- case 1: missed-charge detection


@pytest.mark.asyncio
async def test_detects_missed_charges_per_tenant(db_session, factory, test_env):
    """Case 1 — events with no consume transaction are reported as missed
    charges with full detail, grouped per tenant (no cross-tenant bleed); a
    charged control event on the same clock is NOT flagged."""
    # Tenant A (test tenant): one missed event + one fully-charged control.
    conv_a, _, m2_a = await _seed_conv_and_msg(db_session, test_env.tenant_id)
    await _seed_wallet(db_session, test_env.tenant_id, balance=1_000)
    missed_a = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv_a.id,
        m2_a.id,
        total=100,
        created_at=OLD_AT,
    )
    control = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv_a.id,
        m2_a.id,
        total=40,
        created_at=OLD_AT,
    )
    await _charge_and_pin(db_session, test_env.tenant_id, control)

    # Tenant B: one missed event only.
    tnt_b = "tnt-recon-b"
    await _seed_tenant(db_session, tnt_b)
    conv_b, _, m2_b = await _seed_conv_and_msg(db_session, tnt_b)
    missed_b = await _seed_usage_event(
        db_session,
        tnt_b,
        conv_b.id,
        m2_b.id,
        total=70,
        created_at=OLD_AT,
    )

    report = await _run(factory, AS_OF)

    assert report["has_discrepancy"] is True
    new_ids = report["stats"]["new_alerted_event_ids"]
    assert missed_a.id in new_ids
    assert missed_b.id in new_ids
    assert control.id not in new_ids
    assert report["stats"]["new_alerted_count"] == 2

    per_a = report["per_tenant"][test_env.tenant_id]
    detail = per_a["missed_new"][0]
    assert detail["event_id"] == missed_a.id
    assert detail["conversation_id"] == conv_a.id
    assert detail["model"] == "deepseek-chat"
    assert detail["total_tokens"] == 100
    assert detail["prompt_tokens"] == 10
    assert detail["completion_tokens"] == 20
    # The charged control explains itself — no residual on top of the miss.
    assert per_a["residual_tokens"] == 0

    per_b = report["per_tenant"][tnt_b]
    assert [d["event_id"] for d in per_b["missed_new"]] == [missed_b.id]

    rows = await _fetch_run_records(db_session)
    assert len(rows) == 1
    assert rows[0].level == "warning"
    assert rows[0].details_json["stats"]["new_alerted_count"] == 2


# ----------------------------------------------------- case 5: lookback buffer


@pytest.mark.asyncio
async def test_buffer_window_shields_inflight_events(db_session, factory, test_env):
    """Case 5 — an event 5min before as_of sits inside the 30min buffer and
    is not judged (clean run, level=info); an event at −31min is judged."""
    conv, _, m2 = await _seed_conv_and_msg(db_session, test_env.tenant_id)
    fresh = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=80,
        created_at=FRESH_AT,
    )

    report = await _run(factory, AS_OF)

    assert report["has_discrepancy"] is False
    assert report["stats"]["events_scanned"] == 0  # nothing outside the buffer
    rows = await _fetch_run_records(db_session)
    assert len(rows) == 1
    assert rows[0].level == "info"

    # Same clock +31min later: now the event crosses the boundary.
    old = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=60,
        created_at=OLD_AT,
    )
    report2 = await _run(factory, AS_OF, force=True)
    assert old.id in report2["stats"]["new_alerted_event_ids"]
    assert fresh.id not in report2["stats"]["new_alerted_event_ids"]


# ----------------------------------------------------- case 3: idempotency


@pytest.mark.asyncio
async def test_same_day_rerun_skips_without_new_record(db_session, factory, test_env):
    """Case 3a — the as_of day-granularity lock: re-running with an as_of on
    the same calendar day skips (no second run record); the next day runs."""
    conv, _, m2 = await _seed_conv_and_msg(db_session, test_env.tenant_id)
    await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=100,
        created_at=OLD_AT,
    )

    first = await _run(factory, AS_OF)
    assert first["skipped"] is False
    assert len(await _fetch_run_records(db_session)) == 1

    second = await _run(factory, AS_OF + timedelta(hours=1))  # same UTC day
    assert second["skipped"] is True
    assert len(await _fetch_run_records(db_session)) == 1  # no new record

    third = await _run(factory, DAY2_AS_OF)  # next day runs normally
    assert third["skipped"] is False
    assert len(await _fetch_run_records(db_session)) == 2


@pytest.mark.asyncio
async def test_force_rerun_appends_but_never_realerts(db_session, factory, test_env):
    """Case 3b — force re-runs the same day: a new run record IS appended,
    but the already-alerted event is never re-alerted (it moves to the
    existing-unhandled stat instead)."""
    conv, _, m2 = await _seed_conv_and_msg(db_session, test_env.tenant_id)
    ev = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=100,
        created_at=OLD_AT,
    )

    first = await _run(factory, AS_OF)
    assert first["stats"]["new_alerted_event_ids"] == [ev.id]

    second = await _run(factory, AS_OF, force=True)
    assert second["skipped"] is False
    assert second["forced"] is True
    assert second["stats"]["new_alerted_event_ids"] == []
    assert second["stats"]["new_alerted_count"] == 0
    assert second["stats"]["existing_unhandled_count"] == 1
    assert second["stats"]["existing_unhandled_event_ids"] == [ev.id]

    rows = await _fetch_run_records(db_session)
    assert len(rows) == 2  # force bypasses the day lock and appends


# ----------------------------------------------------- case 4: first alert + existing stock


@pytest.mark.asyncio
async def test_first_alert_once_then_counts_as_existing(db_session, factory, test_env):
    """Case 4 — an event is alerted exactly once: day1 alerts A; day2 (A
    still uncharged + new event B) alerts only B and counts A as existing
    unhandled stock in both the report and the run record."""
    conv, _, m2 = await _seed_conv_and_msg(db_session, test_env.tenant_id)
    ev_a = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=100,
        created_at=OLD_AT,
    )
    day1 = await _run(factory, AS_OF)
    assert day1["stats"]["new_alerted_event_ids"] == [ev_a.id]
    assert day1["stats"]["existing_unhandled_count"] == 0

    ev_b = await _seed_usage_event(
        db_session,
        test_env.tenant_id,
        conv.id,
        m2.id,
        total=60,
        created_at=DAY2_OLD_AT,
    )
    day2 = await _run(factory, DAY2_AS_OF)

    assert day2["stats"]["new_alerted_event_ids"] == [ev_b.id]
    assert day2["stats"]["new_alerted_count"] == 1
    assert day2["stats"]["existing_unhandled_count"] == 1
    assert day2["stats"]["existing_unhandled_event_ids"] == [ev_a.id]

    # The persisted day2 record keeps the same split for audit readers.
    # (Records are picked by as_of, not row order: created_at comes from
    # SQLite's second-precision CURRENT_TIMESTAMP, so two runs in the same
    # second tie and the id tiebreaker is a random uuid.)
    rows = await _fetch_run_records(db_session)
    assert len(rows) == 2
    by_as_of = {r.details_json["as_of"]: r for r in rows}
    day2_details = by_as_of[DAY2_AS_OF.isoformat()].details_json["stats"]
    assert day2_details["new_alerted_event_ids"] == [ev_b.id]
    assert day2_details["existing_unhandled_event_ids"] == [ev_a.id]


# ----------------------------------------------------- case 6: aggregate residual


@pytest.mark.asyncio
async def test_residual_detects_orphan_consume_transaction(db_session, factory, test_env):
    """Case 6 — a consume transaction with no usage_event_id (transaction-
    side anomaly: SET-NULL orphan / manual ledger insert) is caught by the
    aggregate residual even though the event level sees zero missed."""
    from app.models.wallet import WalletTransaction

    w = await _seed_wallet(db_session, test_env.tenant_id, balance=1_000)
    db_session.add(
        WalletTransaction(
            wallet_id=w.id,
            tenant_id=test_env.tenant_id,
            type="consume",
            amount=-50,
            balance_after=w.balance,
            usage_event_id=None,
            model="deepseek-chat",
            created_at=OLD_AT,
        )
    )
    await db_session.commit()

    report = await _run(factory, AS_OF)

    # Event level is clean — the anomaly lives on the transaction side.
    assert report["stats"]["new_alerted_count"] == 0
    # Aggregate layer catches it: 0 event tokens − 50 consumed − 0 missed.
    assert report["stats"]["residual_tenants"] == 1
    per = report["per_tenant"][test_env.tenant_id]
    assert per["residual_tokens"] == -50
    assert report["has_discrepancy"] is True
    rows = await _fetch_run_records(db_session)
    assert len(rows) == 1
    assert rows[0].level == "warning"


# ----------------------------------------------------- case 7: wallet invariant


@pytest.mark.asyncio
async def test_wallet_invariant_detects_manual_balance_edit(db_session, factory, test_env):
    """Case 7 — editing wallet.balance without a ledger row breaks the
    lifetime invariant (balance = recharged + signed refund/adjust −
    consumed); the drift is reported with both sides of the equation."""
    w = await _seed_wallet(db_session, test_env.tenant_id, balance=1_000)
    w.balance = 900  # manual edit, no transaction row
    await db_session.commit()

    report = await _run(factory, AS_OF)

    assert report["stats"]["wallet_drift_count"] == 1
    drift = report["per_tenant"][test_env.tenant_id]["wallet_drift"]
    assert drift == {"balance": 900, "expected_balance": 1_000, "drift": -100}
    assert report["has_discrepancy"] is True
    rows = await _fetch_run_records(db_session)
    assert rows[0].level == "warning"


# ----------------------------------------------------- scheduler shell + registration


@pytest.mark.asyncio
async def test_reconcile_billing_shell_swallows_service_errors(monkeypatch, factory):
    """The scheduler shell wraps the service: a raised error is logged via
    logger.exception and turned into a None return — a broken run must be
    visible without taking down the scheduler process."""
    from app.core import scheduler as sched_mod

    async def _boom(self, as_of, *, force=False):  # noqa: ANN001
        raise RuntimeError("reconciliation exploded")

    monkeypatch.setattr(sched_mod.BillingReconciliationService, "run", _boom)
    result = await sched_mod.reconcile_billing(factory)
    assert result is None


@pytest.mark.asyncio
async def test_reconcile_billing_shell_runs_the_service(factory, db_session, test_env):
    """Happy-path shell: real service runs with as_of = now, run record
    lands in the DB (the shell is a thin pass-through, nothing more)."""
    from app.core.scheduler import reconcile_billing

    report = await reconcile_billing(factory)
    assert report["skipped"] is False
    assert "as_of" in report
    records = await _fetch_run_records(db_session)
    assert len(records) == 1


def test_register_jobs_schedules_reconcile_billing_at_0930():
    """The job is registered on the shared scheduler at 09:30 (staggered off
    the 09:00 balance scan) under a stable id, alongside the existing job."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    from app.core.scheduler import _register_jobs

    sched = AsyncIOScheduler()
    _register_jobs(sched)

    job = sched.get_job("reconcile_billing")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "9"
    assert fields["minute"] == "30"
    # The existing job is untouched.
    assert sched.get_job("scan_balance_warnings") is not None
