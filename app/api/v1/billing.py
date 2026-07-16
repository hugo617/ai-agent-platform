"""Token billing endpoints — wallet balance, recharge, ledger, pricing.

Scope split (mirrors the user decision: prepaid-wallet + super-admin recharge):

  - **wallet read** (``GET /billing/wallet``, ``GET /billing/transactions``,
    ``GET /billing/usage``): the caller's own tenant. Guarded by
    ``wallet:read`` / ``billing:read`` (owner/admin). Super admin short-
    circuits in ``permission_service.check``.
  - **wallet read by id** (``GET /billing/wallet/{tenant_id}``): super admin
    only — inspecting any store's balance is platform-level.
  - **recharge** (``POST /billing/recharge``): super admin only. Credits a
    tenant's wallet; no tenant role has this power.
  - **pricing read** (``GET /billing/pricing``): ``billing:read``. Returns the
    effective pricing (tenant overrides + platform defaults) for the caller.
  - **pricing write** (``POST/PUT/DELETE /billing/pricing``): super admin only.
    Pricing is platform policy, not a tenant-scoped action.

All monetary amounts are Decimal snapshots (per-1k-token prices). The balance
itself is an integer token count; money only ever appears as a charge-time
``cost`` on usage_events / transactions.
"""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission, require_super_admin
from app.core.database import get_db
from app.models.model_pricing import ModelPricing
from app.models.wallet import WalletTransaction
from app.repositories.usage_event import UsageEventRepository
from app.repositories.wallet import (
    ModelPricingRepository,
    WalletRepository,
    WalletTransactionRepository,
)
from app.schemas.billing import (
    ModelPricingRead,
    ModelPricingUpsert,
    RechargeRequest,
    WalletRead,
    WalletTransactionRead,
    WalletUpdate,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["billing"])


# --------------------------------------------------------------- wallet read


@router.get(
    "/wallet",
    response_model=WalletRead | None,
    dependencies=[Depends(require_permission("wallet", "read"))],
)
async def get_my_wallet(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletRead | None:
    """The caller's tenant wallet (balance + lifetime counters). None if absent."""
    wallet = await WalletRepository(db).get_for_tenant(user.tenant_id)
    return WalletRead.model_validate(wallet) if wallet else None


@router.get(
    "/wallet/{tenant_id}",
    response_model=WalletRead | None,
    dependencies=[Depends(require_super_admin())],
)
async def get_tenant_wallet(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> WalletRead | None:
    """Any tenant's wallet (super admin only). None if the tenant has none."""
    wallet = await WalletRepository(db).get_for_tenant(tenant_id)
    return WalletRead.model_validate(wallet) if wallet else None


@router.put(
    "/wallet",
    response_model=WalletRead,
    dependencies=[Depends(require_permission("wallet", "update"))],
)
async def update_my_wallet(
    payload: WalletUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletRead:
    """Edit the caller's wallet alert threshold / active flag (balance untouched)."""
    wallet = await BillingService(db).update_wallet_settings(
        user.tenant_id,
        low_balance_threshold=payload.low_balance_threshold,
        is_active=payload.is_active,
    )
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="钱包不存在")
    return WalletRead.model_validate(wallet)


# --------------------------------------------------------------- transactions


@router.get(
    "/transactions",
    response_model=list[WalletTransactionRead],
    dependencies=[Depends(require_permission("wallet", "read"))],
)
async def list_my_transactions(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[WalletTransaction]:
    """The caller's tenant wallet ledger (recharge/consume/refund/adjust)."""
    return await WalletTransactionRepository(db).list_for_tenant(
        user.tenant_id, limit=limit, offset=offset
    )


# --------------------------------------------------------------- usage detail


@router.get(
    "/usage",
    dependencies=[Depends(require_permission("billing", "read"))],
)
async def list_my_usage(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """Usage detail rows for the caller's tenant (drill-down for dashboards).

    Returns a dict with ``items`` (raw usage events) + ``summary`` (token sums)
    so the frontend can render both the table and the totals in one call.
    """
    repo = UsageEventRepository(db)
    items = await repo.list_for_tenant(user.tenant_id, limit=limit, offset=offset)
    prompt, completion, total = await repo.sum_tokens_for_tenant(user.tenant_id)
    return {
        "items": [
            {
                "id": e.id,
                "conversation_id": e.conversation_id,
                "message_id": e.message_id,
                "agent_id": e.agent_id,
                "model": e.model,
                "prompt_tokens": e.prompt_tokens,
                "completion_tokens": e.completion_tokens,
                "total_tokens": e.total_tokens,
                "cost": float(e.cost) if e.cost is not None else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        "summary": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        },
    }


# --------------------------------------------------------------- recharge


@router.post(
    "/recharge",
    response_model=WalletTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin())],
)
async def recharge_wallet(
    payload: RechargeRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletTransaction:
    """Credit a tenant's wallet with tokens (super admin only).

    The operator (super admin) is recorded on the transaction for audit. A
    remark (e.g. "7月采购") is optional.
    """
    service = BillingService(db)
    return await service.recharge(
        payload.tenant_id,
        payload.amount,
        operator_id=user.user_id,
        remark=payload.remark,
    )


# --------------------------------------------------------------- pricing


@router.get(
    "/pricing",
    response_model=list[ModelPricingRead],
    dependencies=[Depends(require_permission("billing", "read"))],
)
async def list_pricing(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelPricing]:
    """Effective pricing for the caller's tenant (overrides + platform defaults).

    Super admins see only platform-level rows (they manage platform policy);
    tenant users see their overrides merged with the platform defaults.
    """
    scope = None if user.platform_role == "super_admin" else user.tenant_id
    return await ModelPricingRepository(db).list_active(scope)


async def _upsert_pricing(
    db: AsyncSession, payload: ModelPricingUpsert
) -> ModelPricing:
    """Create or update a pricing row (one active row per scope+model)."""
    repo = ModelPricingRepository(db)
    # Look up an existing active row for the same (tenant_id, model) scope.
    stmt = select(ModelPricing).where(
        ModelPricing.tenant_id.is_(None) if payload.tenant_id is None
        else ModelPricing.tenant_id == payload.tenant_id,
        ModelPricing.model == payload.model,
        ModelPricing.is_active.is_(True),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.input_price_per_1k = payload.input_price_per_1k
        existing.output_price_per_1k = payload.output_price_per_1k
        existing.is_active = payload.is_active
        await db.commit()
        await db.refresh(existing)
        return existing
    row = ModelPricing(
        tenant_id=payload.tenant_id,
        model=payload.model,
        input_price_per_1k=payload.input_price_per_1k,
        output_price_per_1k=payload.output_price_per_1k,
        is_active=payload.is_active,
    )
    await repo.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.post(
    "/pricing",
    response_model=ModelPricingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin())],
)
async def create_pricing(
    payload: ModelPricingUpsert,
    db: AsyncSession = Depends(get_db),
) -> ModelPricing:
    """Create or update a model pricing row (super admin only).

    ``tenant_id`` null = platform default; set = store override. Idempotent on
    (tenant_id, model): re-POSTing the same scope+model updates in place.
    """
    return await _upsert_pricing(db, payload)


@router.put(
    "/pricing/{pricing_id}",
    response_model=ModelPricingRead,
    dependencies=[Depends(require_super_admin())],
)
async def update_pricing(
    pricing_id: str,
    payload: ModelPricingUpsert,
    db: AsyncSession = Depends(get_db),
) -> ModelPricing:
    """Replace a pricing row's fields (super admin only)."""
    repo = ModelPricingRepository(db)
    row = await repo.get(pricing_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定价不存在")
    row.tenant_id = payload.tenant_id
    row.model = payload.model
    row.input_price_per_1k = payload.input_price_per_1k
    row.output_price_per_1k = payload.output_price_per_1k
    row.is_active = payload.is_active
    await db.commit()
    await db.refresh(row)
    return row


@router.delete(
    "/pricing/{pricing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin())],
)
async def delete_pricing(
    pricing_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a pricing row by deactivating it (super admin only).

    Pricing rows are deactivated rather than hard-deleted so historical charges
    remain interpretable (the row that priced them still exists).
    """
    repo = ModelPricingRepository(db)
    row = await repo.get(pricing_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定价不存在")
    row.is_active = False
    await db.commit()
