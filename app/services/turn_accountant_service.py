"""Turn accountant — the single seam for per-turn usage recording + wallet charge.

This service owns the record→charge ordering contract that used to live in
three hand-written call sites in ``app/api/v1/chat.py`` (SSE normal, SSE
failed-turn, composite N+1 loop): one UsageEvent row is committed first,
then the wallet is charged *paired* against it. Holding that pairing here is
the consistency basis of the daily reconciliation job
(``BillingReconciliationService._find_missed_events`` detects a missed
charge as a UsageEvent with NO consume WalletTransaction — the「对账」
contract, see CONTEXT.md): a caller can no longer record without charging
or charge in the wrong order, because callers make exactly one call.

The two public entries differ ONLY in input shape (they replace the old
"NOT shared" API-layer pair whose behavior was a verbatim mirror):

- ``record_stream_turn`` — SSE shape: the streaming ``{"usage": {...},
  "model": str}`` payload aggregated by ``stream_agent``.
- ``record_composite_row`` — composite shape: an already-resolved token
  triple, called once per fragment (agent_id set) plus once for the
  synthesize step (agent_id=None) — the N+1 billing shape.

Best-effort semantics are preserved verbatim from the API-layer helpers
this replaces: a ledger or charge failure is logged, rolled back, and
swallowed — it never breaks an already-successful chat reply.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Conversation
from app.models.message import Message
from app.models.usage_event import UsageEvent
from app.repositories.usage_event import UsageEventRepository
from app.services.billing_service import BillingService

logger = logging.getLogger(__name__)


def extract_usage_int(usage_data: dict | None, key: str) -> int | None:
    """Read a token count from a streaming usage payload, None-safe.

    Formerly ``chat._u`` (moved here: the SSE usage-dict shape is this
    module's domain). Returns None when there's no usage (a stubbed stream
    in tests, or a provider that didn't return usage) so the caller can keep
    Message token columns NULL — ``chat.py`` imports it for that purpose.
    """
    if usage_data is None:
        return None
    val = usage_data.get("usage", {}).get(key)
    return int(val) if val is not None else None


class TurnAccountantService:
    """Per-turn bookkeeping: UsageEvent row + paired wallet charge.

    The record→charge order is single-sourced in ``_record_and_charge``:
    every caller of either entry gets the pairing by construction.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = UsageEventRepository(db)

    # ------------------------------------------------------------- entries

    async def record_stream_turn(
        self,
        conv: Conversation,
        msg: Message,
        agent_id: str,
        user_id: str,
        usage_data: dict | None,
    ) -> UsageEvent | None:
        """Record + charge one SSE assistant turn (streaming usage payload).

        Thin adapter: guards on missing usage (guard migrated verbatim from
        the old ``_record_usage``), resolves the token triple, then funnels
        into the shared ``_record_and_charge`` core. Returns the persisted
        event for test observability, or None when nothing was recorded.
        """
        if usage_data is None:
            return None
        total = extract_usage_int(usage_data, "total_tokens")
        if total is None:
            return None
        return await self._record_and_charge(
            conv,
            msg,
            agent_id=agent_id,
            user_id=user_id,
            model=usage_data.get("model") or "",
            prompt_tokens=extract_usage_int(usage_data, "input_tokens") or 0,
            completion_tokens=extract_usage_int(usage_data, "output_tokens") or 0,
            total_tokens=total,
        )

    async def record_composite_row(
        self,
        conv: Conversation,
        msg: Message,
        agent_id: str | None,
        user_id: str,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        model: str,
    ) -> UsageEvent | None:
        """Record + charge one composite UsageEvent row (resolved triple).

        Thin adapter over the same core. ``agent_id`` is None on the
        synthesize row (the N+1th call has no agent).
        """
        return await self._record_and_charge(
            conv,
            msg,
            agent_id=agent_id,
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    # --------------------------------------------------------------- core

    async def _record_and_charge(
        self,
        conv: Conversation,
        msg: Message,
        *,
        agent_id: str | None,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> UsageEvent | None:
        """Commit one UsageEvent, then debit the wallet paired against it.

        Failure modes (best-effort, verbatim from the API-layer helpers this
        replaces — a bookkeeping error never breaks the chat reply):

        - record fails → ``logger.exception`` + rollback + return None; the
          wallet is NOT charged (no event exists to charge against);
        - charge fails → ``logger.exception`` + rollback; only the pending
          WalletTransaction is dropped — the UsageEvent committed above
          survives, and reconciliation recovers the missing charge later.

        ``operator_id=None`` is deliberate (unchanged): a consume txn has no
        human operator.
        """
        try:
            event = await self.repo.add(
                UsageEvent(
                    tenant_id=conv.tenant_id,
                    conversation_id=conv.id,
                    message_id=msg.id,
                    agent_id=agent_id,  # None on the composite synthesize row
                    customer_id=conv.customer_id,  # 透传 (Token 费用管理系列 3/4)
                    user_id=user_id,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost=None,  # filled by BillingService.charge below
                )
            )
            await self.db.commit()
        except Exception:  # noqa: BLE001 - ledger is best-effort
            # Drop the pending usage_events insert only — the assistant
            # message was already committed by ``append_message``, so it
            # survives the rollback. logger.exception (not a bare pass):
            # composite writes N+1 rows per turn, so a silent swallow would
            # multiply a quiet ledger bug across every agent + the synthesize
            # step; the SSE single row gets the same visibility (unified from
            # the old SSE silent-swallow / composite logged asymmetry —
            # benign superset).
            logger.exception(
                "UsageEvent insert failed (agent_id=%s, conv=%s)",
                agent_id,
                conv.id,
            )
            await self.db.rollback()
            return None

        # Paired charge: the UsageEvent is committed above, so a charge
        # failure rolls back only the WalletTransaction (best-effort) — the
        # ledger row survives and reconciliation recovers the gap.
        try:
            await BillingService(self.db).charge(
                conv.tenant_id, event, operator_id=None
            )
        except Exception:  # noqa: BLE001 - billing is best-effort
            logger.exception(
                "wallet charge failed (tenant=%s, event=%s)",
                conv.tenant_id,
                event.id,
            )
            await self.db.rollback()
        return event
