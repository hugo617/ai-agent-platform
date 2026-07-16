"""Repositories for the wallet billing domain.

Three repositories, each pure data-access (no business logic — that lives in
``BillingService``):

- ``WalletRepository`` — CRUD + the FOR UPDATE read used by charge to lock the
  wallet row against concurrent debits.
- ``WalletTransactionRepository`` — append-only ledger inserts + history reads.
- ``ModelPricingRepository`` — pricing lookups with the tenant-override >
  platform-default resolution.
"""

from sqlalchemy import select

from app.models.model_pricing import ModelPricing
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.base import BaseRepository, TenantScopedRepository


class WalletRepository(TenantScopedRepository[Wallet]):
    """Wallet data access, tenant-scoped.

    ``get_for_tenant_for_update`` reads the wallet with ``SELECT ... FOR
    UPDATE`` so two concurrent chats in the same tenant cannot both see the
    same balance and double-spend. On Postgres this is a real row lock; on
    SQLite (tests) ``with_for_update`` is a no-op but single-threaded async
    tests are still consistent.
    """

    model = Wallet

    async def get_for_tenant(self, tenant_id: str) -> Wallet | None:
        """Return the *live usable* wallet for a tenant, or None.

        "Usable" = not soft-deleted AND ``is_active=True``. An inactive wallet
        is administratively disabled and must not serve chats/billing (the
        ``is_active`` toggle is honoured here, not just written and ignored).
        """
        stmt = select(Wallet).where(
            Wallet.tenant_id == tenant_id,
            Wallet.is_deleted.is_(False),
            Wallet.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_tenant_for_update(self, tenant_id: str) -> Wallet | None:
        """Like ``get_for_tenant`` but acquires a row lock (PG FOR UPDATE).

        Used by ``BillingService.charge`` to serialize concurrent debits on the
        same wallet. SQLite ignores ``with_for_update`` (no-op, no error), so
        single-threaded async tests still pass.
        """
        stmt = (
            select(Wallet)
            .where(
                Wallet.tenant_id == tenant_id,
                Wallet.is_deleted.is_(False),
                Wallet.is_active.is_(True),
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class WalletTransactionRepository(BaseRepository[WalletTransaction]):
    """Append-only ledger for wallet mutations."""

    model = WalletTransaction

    async def list_for_tenant(
        self, tenant_id: str, limit: int = 100, offset: int = 0
    ) -> list[WalletTransaction]:
        """Most-recent transactions for a tenant (history / dashboard)."""
        stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.tenant_id == tenant_id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class ModelPricingRepository(BaseRepository[ModelPricing]):
    """Per-model pricing, with tenant-override > platform-default resolution."""

    model = ModelPricing

    async def get_for_model(
        self, model: str, tenant_id: str
    ) -> ModelPricing | None:
        """Resolve the active pricing for a model in a tenant.

        Order: tenant override (tenant_id=X, model=Y) > platform default
        (tenant_id IS NULL, model=Y). Returns None when neither exists — the
        caller (``BillingService.calc_cost``) treats that as cost=0 (allow the
        chat, record cost=0).
        """
        # 1. Tenant override.
        stmt = select(ModelPricing).where(
            ModelPricing.tenant_id == tenant_id,
            ModelPricing.model == model,
            ModelPricing.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            return row

        # 2. Platform default.
        stmt = select(ModelPricing).where(
            ModelPricing.tenant_id.is_(None),
            ModelPricing.model == model,
            ModelPricing.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self, tenant_id: str | None = None) -> list[ModelPricing]:
        """List active pricing rows.

        With ``tenant_id`` set, returns both the tenant's overrides and the
        platform defaults (so the UI can show "effective pricing per model").
        With ``tenant_id=None`` (super admin platform view), returns only
        platform-level rows.
        """
        stmt = select(ModelPricing).where(ModelPricing.is_active.is_(True))
        if tenant_id is None:
            stmt = stmt.where(ModelPricing.tenant_id.is_(None))
        else:
            stmt = stmt.where(
                (ModelPricing.tenant_id == tenant_id)
                | (ModelPricing.tenant_id.is_(None))
            )
        stmt = stmt.order_by(ModelPricing.model)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
