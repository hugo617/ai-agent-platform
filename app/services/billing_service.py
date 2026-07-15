"""Billing service — prepaid wallet accounting for token usage.

The wallet is the tenant's prepaid token quota. This service owns the three
operations on it:

- ``get_wallet`` / ``has_balance`` — read the live balance and the "can the
  tenant still chat?" gate (used by the chat endpoint to block over-spend).
- ``charge`` — debit the consumed tokens for one successful assistant turn.
  Uses ``SELECT ... FOR UPDATE`` to serialize concurrent debits on the same
  wallet (preventing two parallel chats from both seeing the same balance and
  double-spending). Writes one ``WalletTransaction`` (consume) and stamps the
  monetary ``cost`` snapshot onto the ``UsageEvent``.
- ``recharge`` — credit tokens (super admin only at the route layer). Writes
  one ``WalletTransaction`` (recharge).
- ``calc_cost`` — resolve the model price (tenant override > platform default)
  and compute the monetary cost of a (prompt, completion) pair. Returns 0 when
  no pricing is configured (we still allow the chat; cost is recorded as 0).
- ``create_wallet_for_tenant`` — the bootstrap path: a zero-balance wallet is
  created in the same transaction as ``TenantService.create_tenant`` so every
  tenant has a wallet from birth.

Design notes (see ``plan-token-wallet-billing.md``):

- **Balance is token count, not money.** Pricing changes never move the
  balance; ``cost`` is computed at charge time and frozen on the event/txn.
- **charge is best-effort.** It runs *after* the assistant message has been
  committed, so a charge failure (e.g. concurrent conflict) is logged and
  swallowed — we never break an otherwise-successful chat over a bookkeeping
  error. Discrepancies are reconciled from the usage_events ledger.
- **charge uses the caller's session.** It is invoked from the chat endpoint
  with the request-scoped ``db`` so the debit joins the same transaction as
  the message write when possible.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_pricing import ModelPricing
from app.models.usage_event import UsageEvent
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallet import (
    ModelPricingRepository,
    WalletRepository,
    WalletTransactionRepository,
)
from app.services.errors import BizError

# How many decimal places the cost snapshot keeps. Pricing is per-1k-tokens at
# sub-cent precision, so 6dp is enough to represent a single token's cost for
# the cheapest models while staying well clear of float drift.
_COST_QUANT = Decimal("0.000001")


class BillingService:
    """Prepaid-wallet accounting: balance gate, charge, recharge, pricing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.wallets = WalletRepository(db)
        self.txs = WalletTransactionRepository(db)
        self.pricing = ModelPricingRepository(db)

    # --------------------------------------------------------------- read

    async def get_wallet(self, tenant_id: str) -> Wallet | None:
        """The *live* wallet for a tenant, or None if it doesn't exist."""
        return await self.wallets.get_for_tenant(tenant_id)

    async def update_wallet_settings(
        self,
        tenant_id: str,
        low_balance_threshold: int | None = None,
        is_active: bool | None = None,
    ) -> Wallet | None:
        """Tune a wallet's non-balance fields (alert line / active flag).

        Balance is never edited here — ``recharge`` credits it, ``charge``
        debits it. This method only adjusts the alert threshold and the active
        flag. Returns the updated wallet, or None when no live wallet exists.
        """
        wallet = await self.wallets.get_for_tenant(tenant_id)
        if wallet is None:
            return None
        if low_balance_threshold is not None:
            wallet.low_balance_threshold = low_balance_threshold
        if is_active is not None:
            wallet.is_active = is_active
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def has_balance(self, tenant_id: str) -> bool:
        """True if the tenant may start a new chat (wallet exists + balance>0).

        A missing wallet is treated as "no balance" — the chat endpoint blocks.
        (Every tenant gets a wallet at create_tenant, so a missing wallet is an
        anomaly; blocking is the safe default.)
        """
        wallet = await self.wallets.get_for_tenant(tenant_id)
        return wallet is not None and wallet.balance > 0

    # --------------------------------------------------------------- pricing

    async def calc_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        tenant_id: str,
    ) -> tuple[Decimal, ModelPricing | None]:
        """Monetary cost of a (prompt, completion) pair on ``model``.

        Resolution: tenant override (tenant_id=X, model=Y) > platform default
        (tenant_id IS NULL, model=Y) > "unconfigured" (cost=0, pricing=None).
        Returns ``(cost, pricing_row)``. When unconfigured, cost is Decimal(0)
        and pricing_row is None — the caller records cost=0 and allows the chat
        (a missing price is not the user's fault; we don't block on it).
        """
        pricing = await self.pricing.get_for_model(model, tenant_id)
        if pricing is None:
            return Decimal("0"), None
        # (prompt/1000 * in_price) + (completion/1000 * out_price)
        in_cost = (
            (Decimal(prompt_tokens) * pricing.input_price_per_1k) / Decimal(1000)
        )
        out_cost = (
            (Decimal(completion_tokens) * pricing.output_price_per_1k)
            / Decimal(1000)
        )
        cost = (in_cost + out_cost).quantize(_COST_QUANT, rounding=ROUND_HALF_UP)
        return cost, pricing

    # --------------------------------------------------------------- charge

    async def charge(
        self,
        tenant_id: str,
        usage_event: UsageEvent,
        operator_id: str | None = None,
    ) -> WalletTransaction | None:
        """Debit the consumed tokens for one usage event.

        Acquires ``SELECT ... FOR UPDATE`` on the wallet so concurrent charges
        serialize (PG row lock; SQLite no-op in tests). Computes the cost
        snapshot from the current pricing, stamps it on the usage event, and
        appends a ``consume`` transaction.

        Best-effort: on failure (e.g. wallet gone, concurrent conflict) the
        exception propagates to the caller, which wraps this in try/except so
        a bookkeeping error never breaks a finished chat.

        Returns the transaction row, or None if no live wallet exists (the
        debit is skipped — the chat already succeeded; reconciliation handles
        the gap).
        """
        wallet = await self.wallets.get_for_tenant_for_update(tenant_id)
        if wallet is None:
            # No wallet to debit — record a zero-cost usage and move on. The
            # chat already succeeded; we don't block here. Reconciliation from
            # usage_events recovers the missing charge later.
            return None

        total = usage_event.total_tokens
        cost, _ = await self.calc_cost(
            usage_event.model,
            usage_event.prompt_tokens,
            usage_event.completion_tokens,
            tenant_id,
        )

        # Stamp the cost snapshot onto the usage event (it was left NULL by
        # task 1's collection path).
        usage_event.cost = cost

        # Debit. Guard against going negative only loosely — the balance gate
        # blocks *new* chats at 0, but an in-flight turn started above 0 can
        # legitimately push the balance negative (the tokens were consumed
        # before the gate could re-check). We honor the real consumption.
        wallet.balance -= total
        wallet.total_consumed += total

        txn = WalletTransaction(
            wallet_id=wallet.id,
            tenant_id=tenant_id,
            type="consume",
            amount=-total,
            balance_after=wallet.balance,
            usage_event_id=usage_event.id,
            model=usage_event.model,
            operator_id=operator_id,
            remark=None,
        )
        await self.txs.add(txn)
        await self.db.commit()
        return txn

    # --------------------------------------------------------------- recharge

    async def recharge(
        self,
        tenant_id: str,
        amount: int,
        operator_id: str,
        remark: str | None = None,
    ) -> WalletTransaction:
        """Credit ``amount`` tokens to the tenant's wallet.

        Super-admin-only at the route layer (``require_super_admin``); this
        method trusts the caller. Acquires FOR UPDATE so a recharge racing a
        charge produces a consistent ``balance_after``. Raises ``ValueError``
        if the tenant has no wallet yet (recharge before wallet bootstrap is a
        caller bug, not a recoverable state).
        """
        if amount <= 0:
            raise BizError("充值额度必须为正整数")

        wallet = await self.wallets.get_for_tenant_for_update(tenant_id)
        if wallet is None:
            raise BizError(f"租户 {tenant_id} 没有钱包,无法充值")

        wallet.balance += amount
        wallet.total_recharged += amount

        txn = WalletTransaction(
            wallet_id=wallet.id,
            tenant_id=tenant_id,
            type="recharge",
            amount=amount,
            balance_after=wallet.balance,
            remark=remark,
            operator_id=operator_id,
        )
        await self.txs.add(txn)
        await self.db.commit()

        # Notification trigger (priority 54): inform the tenant a recharge
        # landed. Targeted at all tenant users (user_id=NULL) so the owner +
        # admins all see it in their bell. Best-effort — never breaks the
        # committed recharge (the txn is already persisted above).
        from app.services.notification_service import NotificationService

        await NotificationService(self.db).create(
            tenant_id=tenant_id,
            user_id=None,
            type="recharge",
            title="充值到账",
            content=f"钱包已充值 {amount} tokens,当前余额 {wallet.balance}。",
            link="/billing",
        )
        return txn

    # --------------------------------------------------------------- bootstrap

    async def create_wallet_for_tenant(self, tenant_id: str) -> Wallet:
        """Create a zero-balance wallet for a new tenant.

        Called by ``TenantService.create_tenant`` within its transaction, so
        the wallet is committed atomically with the tenant + RBAC seed. If a
        live wallet already exists (e.g. idempotent re-run), the existing one
        is returned untouched.
        """
        existing = await self.wallets.get_for_tenant(tenant_id)
        if existing is not None:
            return existing
        wallet = Wallet(tenant_id=tenant_id, balance=0)
        await self.wallets.add(wallet)
        return wallet
