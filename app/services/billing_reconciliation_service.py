"""Billing reconciliation: dual-layer discrepancy detection (read-only).

Closes the loop that ``BillingService.charge``'s docstring promises: usage-
event recording and wallet charging are two independent transactions, and a
failed charge used to vanish silently (cost stays NULL, no consume
transaction). This service makes the gap visible — it never mutates balances
(plan D7: report only; manual top-ups go through the existing ``adjust``
transaction type).

Detection layers (plan D1), both scoped by the same ``cutoff = as_of −
LOOKBACK_BUFFER`` window (D9: charge is awaited in-request milliseconds after
the event commit, so 30 minutes is three orders of magnitude of headroom
against in-flight false positives):

1. **Event level** — every usage event older than the cutoff with no
   matching ``consume`` transaction (NOT EXISTS on ``usage_event_id``) is a
   missed charge, reported with full detail (tenant / conversation / model /
   token facts; cost is never recomputed — D7).
2. **Aggregate level** — checks the event-level join cannot express:
   per-tenant residual (transaction-side anomalies such as SET-NULL orphan
   transactions or manual ledger edits) and the wallet lifetime invariant
   (balance edited outside the charge/recharge orchestration).

Both layers share the cutoff window: an uncharged event inside the buffer is
invisible to both (in-flight, not yet judgeable), and a missed event outside
it is fully explained by the event layer so it cancels out of the residual —
the residual therefore reports only what the event layer cannot explain, and
no second buffer concept is needed.

Every run appends exactly ONE SystemLog row (``action =
billing_reconciliation``, ``details_json`` = the full report): warning when
discrepancies exist, info for a clean run (plan D8 — "ran and found nothing"
must be distinguishable from "never ran"). The row is written directly
instead of via ``LoggingService.record`` because it IS the run's primary
artifact: a swallowed write failure would silently break the idempotency
locks, so it must fail loudly to the scheduler shell.

Discrepant runs additionally ring a third channel: a targeted ``system``
in-app notification to every reachable super_admin (their first active
membership's tenant — a platform-wide tenant_id=NULL row would be invisible
through the notification repo's equality match). Clean runs stay silent;
the info record in the audit log is the daily proof of life.

All datetimes are normalized to aware-UTC; a naive ``as_of`` is interpreted
as UTC. On SQLite (tests) the offset is dropped at bind time, which is
lossless for UTC wall-clock values.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import SystemLog
from app.models.tenant import User, UserTenant
from app.models.usage_event import UsageEvent
from app.models.wallet import Wallet, WalletTransaction
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

#: Plan D9 — lookback buffer shielding in-flight charges from judgement.
#: The real in-flight window is milliseconds (charge is awaited in-request
#: right after the event commit); 30min is deliberate over-provisioning.
LOOKBACK_BUFFER = timedelta(minutes=30)

#: SystemLog action identifying reconciliation run records (the idempotency
#: lock and the first-alert history both key off this action).
RECONCILIATION_ACTION = "billing_reconciliation"

# A usage event counts as charged iff a consume ledger row links back to it.
# (charge failures roll the whole debit back, so "no row" and "row rolled
# back" are the same observable state.)
_CONSUME_TX_EXISTS = (
    select(WalletTransaction.id)
    .where(
        WalletTransaction.usage_event_id == UsageEvent.id,
        WalletTransaction.type == "consume",
    )
    .exists()
)


def _normalize_utc(dt: datetime) -> datetime:
    """Aware-UTC form of ``dt`` (naive input is interpreted as UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _record_as_of(record: SystemLog) -> datetime | None:
    """Parse a run record's ``as_of``; None when absent/corrupt (a damaged
    record must disable the skip lock, not crash the job)."""
    raw = (record.details_json or {}).get("as_of")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _normalize_utc(parsed)


def _new_tenant_signal() -> dict[str, Any]:
    """Empty per-tenant signal block (filled in by the detection layers)."""
    return {
        "missed_new": [],
        "missed_new_tokens": 0,
        "missed_existing_ids": [],
        "residual_tokens": 0,
        "wallet_drift": None,
    }


class BillingReconciliationService:
    """One ``run()`` = one reconciliation pass + one SystemLog run record."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run(self, as_of: datetime, *, force: bool = False) -> dict[str, Any]:
        """Reconcile the billing ledgers up to ``as_of`` and report.

        Returns the report dict (also persisted as the run record's
        ``details_json``). ``force=True`` bypasses the same-day idempotency
        lock for manual re-runs.
        """
        as_of = _normalize_utc(as_of)
        cutoff = as_of - LOOKBACK_BUFFER

        # ---- idempotency lock (run level, as_of day granularity) --------
        history = await self._load_run_history()
        latest_as_of = _record_as_of(history[0]) if history else None
        if not force and latest_as_of is not None and latest_as_of.date() == as_of.date():
            logger.info(
                "reconciliation already ran for %s (as_of=%s); skipping "
                "(pass force=True to re-run)",
                as_of.date(),
                latest_as_of.isoformat(),
            )
            return {
                "skipped": True,
                "forced": force,
                "as_of": as_of.isoformat(),
                "last_run_as_of": latest_as_of.isoformat(),
                "note": "同日已跑过,skip(force=True 可强制重跑)",
            }

        # ---- first-alert dedup (event level, across all history) --------
        alerted_ids: set[str] = set()
        for record in history:
            details = record.details_json or {}
            stats = details.get("stats") or {}
            ids = stats.get("new_alerted_event_ids") or []
            # Historical rows predate the JSON list format only in theory —
            # defensive str() keeps a hand-edited record from crashing the job.
            alerted_ids.update(str(i) for i in ids)

        # ---- layer 1: event-level missed charges ------------------------
        missed = await self._find_missed_events(cutoff)
        missed_ids = {ev.id for ev in missed}
        new_ids = [ev.id for ev in missed if ev.id not in alerted_ids]
        existing_ids = sorted(alerted_ids & missed_ids)

        # ---- shared window stats ----------------------------------------
        window = await self._window_event_stats(cutoff)
        events_scanned = sum(w["events"] for w in window.values())
        missed_tokens_by_tenant: dict[str, int] = {}
        for ev in missed:
            missed_tokens_by_tenant[ev.tenant_id] = (
                missed_tokens_by_tenant.get(ev.tenant_id, 0) + ev.total_tokens
            )

        per_tenant: dict[str, Any] = {}
        for ev in missed:
            signal = per_tenant.setdefault(ev.tenant_id, _new_tenant_signal())
            if ev.id in alerted_ids:
                signal["missed_existing_ids"].append(ev.id)
                continue
            signal["missed_new"].append(
                {
                    "event_id": ev.id,
                    "tenant_id": ev.tenant_id,
                    "conversation_id": ev.conversation_id,
                    "model": ev.model,
                    "prompt_tokens": ev.prompt_tokens,
                    "completion_tokens": ev.completion_tokens,
                    "total_tokens": ev.total_tokens,
                    "created_at": ev.created_at.isoformat(),
                }
            )
            signal["missed_new_tokens"] += ev.total_tokens

        # ---- layer 2a: per-tenant aggregate residual --------------------
        # windowed event tokens − windowed consumed tokens − known missed
        # tokens. Missed charges appear on both the event and the missed
        # side, so they cancel out: a non-zero residual means the
        # transaction side moved in ways the event level cannot explain
        # (SET-NULL orphan transactions, manual ledger edits, overcharging).
        # A tenant with consume rows but no windowed events (orphan only)
        # must still be visited, hence the union of keys.
        consume = await self._window_consume_stats(cutoff)
        residual_by_tenant: dict[str, int] = {}
        for tid in set(window) | set(consume):
            residual = (
                window.get(tid, {}).get("tokens", 0)
                - consume.get(tid, 0)
                - missed_tokens_by_tenant.get(tid, 0)
            )
            if residual != 0:
                residual_by_tenant[tid] = residual

        # ---- layer 2b: wallet lifetime invariant ------------------------
        # balance must equal total_recharged + signed refund/adjust sums −
        # total_consumed. refund/adjust are summed WITH sign so a correctly
        # executed manual adjustment never false-positives; a mismatch means
        # wallet fields were edited outside the charge/recharge path.
        # Lifetime scope (no window) — the counters are lifetime totals.
        wallets = await self._live_wallets()
        drift_by_tenant = await self._wallet_drifts(wallets)

        for tid, residual in residual_by_tenant.items():
            per_tenant.setdefault(tid, _new_tenant_signal())["residual_tokens"] = residual
        for tid, drift in drift_by_tenant.items():
            per_tenant.setdefault(tid, _new_tenant_signal())["wallet_drift"] = drift

        tenants_checked = set(window) | set(consume) | set(drift_by_tenant)
        # Live wallets without any signal still count as checked scope.
        for wallet in wallets:
            tenants_checked.add(wallet.tenant_id)

        has_discrepancy = bool(new_ids) or bool(residual_by_tenant) or bool(drift_by_tenant)
        report: dict[str, Any] = {
            "skipped": False,
            "forced": force,
            "as_of": as_of.isoformat(),
            "cutoff": cutoff.isoformat(),
            "stats": {
                "tenants_checked": len(tenants_checked),
                "events_scanned": events_scanned,
                "new_alerted_event_ids": new_ids,
                "new_alerted_count": len(new_ids),
                "existing_unhandled_count": len(existing_ids),
                "existing_unhandled_event_ids": existing_ids,
                "residual_tenants": len(residual_by_tenant),
                "wallet_drift_count": len(drift_by_tenant),
            },
            "per_tenant": {tid: per_tenant[tid] for tid in sorted(per_tenant)},
            "has_discrepancy": has_discrepancy,
        }

        if has_discrepancy:
            message = (
                f"计费对账发现差额:新告漏扣 {len(new_ids)} 条,"
                f"存量未处理 {len(existing_ids)} 条,"
                f"残余差租户 {len(residual_by_tenant)} 个,"
                f"钱包漂移 {len(drift_by_tenant)} 个"
                f"(as_of={as_of.isoformat()})"
            )
        else:
            message = (
                f"计费对账完成,无差额:扫描事件 {events_scanned} 条,"
                f"覆盖租户 {len(tenants_checked)} 个"
                f"(as_of={as_of.isoformat()})"
            )

        # Written directly (not via LoggingService): this row is the run's
        # primary artifact — a swallowed failure must surface to the shell.
        self.db.add(
            SystemLog(
                level="warning" if has_discrepancy else "info",
                action=RECONCILIATION_ACTION,
                module="billing",
                message=message,
                details_json=report,
                tenant_id=None,  # platform-level job, not tenant-scoped
            )
        )
        await self.db.commit()

        if has_discrepancy:
            logger.error("billing reconciliation: %s", message)
            # Third channel (plan D5): targeted in-app notifications, after
            # the run record is safely committed — the record is the primary
            # artifact, notifications are best-effort follow-up.
            await self._notify_super_admins(message)
        else:
            logger.info("billing reconciliation: %s", message)
        return report

    # ------------------------------------------------------- detection

    async def _load_run_history(self) -> list[SystemLog]:
        """All previous run records, newest first (id tiebreaker, mirroring
        SystemLogRepository's stable ordering)."""
        stmt = (
            select(SystemLog)
            .where(SystemLog.action == RECONCILIATION_ACTION)
            .order_by(SystemLog.created_at.desc(), SystemLog.id.desc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def _find_missed_events(self, cutoff: datetime) -> list[UsageEvent]:
        """Usage events older than ``cutoff`` with no consume transaction."""
        stmt = (
            select(UsageEvent)
            .where(UsageEvent.created_at < cutoff, ~_CONSUME_TX_EXISTS)
            .order_by(UsageEvent.created_at, UsageEvent.id)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def _window_event_stats(self, cutoff: datetime) -> dict[str, dict[str, int]]:
        """Per-tenant event count / token sum inside the cutoff window."""
        stmt = (
            select(
                UsageEvent.tenant_id,
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            )
            .where(UsageEvent.created_at < cutoff)
            .group_by(UsageEvent.tenant_id)
        )
        rows = (await self.db.execute(stmt)).all()
        return {tid: {"events": int(count), "tokens": int(tokens)} for tid, count, tokens in rows}

    async def _window_consume_stats(self, cutoff: datetime) -> dict[str, int]:
        """Per-tenant consumed tokens (|amount| of consume rows) inside the
        cutoff window. Consume rows are matched by their own ``created_at``:
        charge is awaited in-request milliseconds after the event commit, so
        a charge delayed past the window boundary is practically impossible
        and a mismatch here would itself be a finding."""
        stmt = (
            select(
                WalletTransaction.tenant_id,
                func.coalesce(-func.sum(WalletTransaction.amount), 0),
            )
            .where(
                WalletTransaction.type == "consume",
                WalletTransaction.created_at < cutoff,
            )
            .group_by(WalletTransaction.tenant_id)
        )
        rows = (await self.db.execute(stmt)).all()
        return {tid: int(tokens) for tid, tokens in rows}

    async def _live_wallets(self) -> list[Wallet]:
        stmt = select(Wallet).where(Wallet.is_deleted.is_(False))
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def _wallet_drifts(
        self, wallets: list[Wallet]
    ) -> dict[str, dict[str, int]]:
        """Wallets whose balance breaks the lifetime invariant, per tenant.

        expected = total_recharged + Σ(refund/adjust amounts, signed)
                   − total_consumed
        """
        ra_stmt = (
            select(
                WalletTransaction.wallet_id,
                func.coalesce(func.sum(WalletTransaction.amount), 0),
            )
            .where(WalletTransaction.type.in_(("refund", "adjust")))
            .group_by(WalletTransaction.wallet_id)
        )
        ra_rows = (await self.db.execute(ra_stmt)).all()
        refund_adjust_by_wallet = {wid: int(total) for wid, total in ra_rows}

        drifts: dict[str, dict[str, int]] = {}
        for w in wallets:
            expected = w.total_recharged + (
                refund_adjust_by_wallet.get(w.id, 0)
            ) - (w.total_consumed)
            drift = w.balance - expected
            if drift != 0:
                drifts[w.tenant_id] = {
                    "balance": w.balance,
                    "expected_balance": expected,
                    "drift": drift,
                }
        return drifts

    # ------------------------------------------------------- notifications

    async def _super_admin_targets(self) -> dict[str, str | None]:
        """Live super_admins → tenant of their first active membership.

        Returns ``{user_id: tenant_id_or_None}``; None marks a super_admin
        with no active membership (skipped with a warning by the caller).
        "First" = earliest ``valid_from`` (id tiebreaker) so the pick is
        deterministic when a super_admin holds active memberships in
        several tenants.
        """
        admin_rows = await self.db.execute(
            select(User.id)
            .where(
                User.platform_role == "super_admin",
                User.is_deleted.is_(False),
            )
            .order_by(User.id)
        )
        admin_ids = [row[0] for row in admin_rows.all()]
        if not admin_ids:
            return {}

        membership_rows = await self.db.execute(
            select(UserTenant.user_id, UserTenant.tenant_id)
            .where(
                UserTenant.user_id.in_(admin_ids),
                UserTenant.valid_to.is_(None),
            )
            .order_by(UserTenant.user_id, UserTenant.valid_from, UserTenant.id)
        )
        first_membership: dict[str, str] = {}
        for user_id, tenant_id in membership_rows.all():
            first_membership.setdefault(user_id, tenant_id)  # ordered: first wins
        return {user_id: first_membership.get(user_id) for user_id in admin_ids}

    async def _notify_super_admins(self, summary: str) -> int:
        """Targeted ``system`` notification to every reachable super_admin.

        Best-effort by construction: ``NotificationService.create`` never
        raises (nested SAVEPOINT + swallow), so a broken notification can
        neither crash this run nor poison the already-committed run record.
        The notification must carry ``tenant_id`` of a membership — a
        platform-wide (tenant_id=NULL) row is invisible through the
        notification repo's equality match (plan D5 rationale).
        """
        targets = await self._super_admin_targets()
        notifier = NotificationService(self.db)
        created = 0
        for user_id, tenant_id in targets.items():
            if tenant_id is None:
                logger.warning(
                    "super_admin %s has no active membership; skipping "
                    "reconciliation notification",
                    user_id,
                )
                continue
            notification = await notifier.create(
                type="system",
                title="计费对账发现差额",
                content=summary,
                tenant_id=tenant_id,
                user_id=user_id,
                link="/logs",
            )
            if notification is not None:
                created += 1
        # create() only flushes inside its SAVEPOINT — the caller of a
        # best-effort insert must commit it (mirrors scan_balance_warnings).
        await self.db.commit()
        return created
