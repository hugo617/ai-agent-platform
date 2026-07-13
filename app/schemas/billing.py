"""Pydantic schemas for the token billing domain (wallet / pricing / ledger).

These DTOs back the ``/billing/*`` endpoints. The wallet read carries the live
balance + lifetime counters; transactions are the append-only ledger; pricing
rows hold per-model token prices (platform default + tenant override).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------- wallet


class WalletRead(BaseModel):
    """The prepaid token wallet for one tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    balance: int = Field(description="剩余 token 数(整数)")
    total_recharged: int
    total_consumed: int
    low_balance_threshold: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WalletUpdate(BaseModel):
    """Edit a wallet's non-balance fields (alert line / active flag).

    Balance is never edited directly here — recharge credits it, charge debits
    it. This payload only tunes the alert threshold and the active flag.
    """

    low_balance_threshold: int | None = Field(None, ge=0)
    is_active: bool | None = None


# --------------------------------------------------------------- transaction


class WalletTransactionRead(BaseModel):
    """One append-only ledger row (recharge / consume / refund / adjust)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    wallet_id: str
    tenant_id: str
    type: str
    amount: int = Field(description="带符号:+充值 -消耗")
    balance_after: int
    usage_event_id: str | None = None
    model: str | None = None
    remark: str | None = None
    operator_id: str | None = None
    created_at: datetime


class RechargeRequest(BaseModel):
    """Super-admin payload for POST /billing/recharge."""

    tenant_id: str
    amount: int = Field(ge=1, description="充值 token 数(正整数)")
    remark: str | None = Field(None, max_length=500)


# --------------------------------------------------------------- pricing


class ModelPricingRead(BaseModel):
    """One per-model pricing row (platform default or tenant override)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = Field(
        None, description="NULL=平台默认;非空=租户覆盖"
    )
    model: str
    input_price_per_1k: Decimal
    output_price_per_1k: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ModelPricingUpsert(BaseModel):
    """Payload for POST/PUT /billing/pricing.

    ``tenant_id`` is optional: omit/null = platform default (super admin only);
    set it to scope the price to one store. Prices are per 1k tokens.
    """

    tenant_id: str | None = None
    model: str = Field(min_length=1, max_length=64)
    input_price_per_1k: Decimal = Field(ge=0)
    output_price_per_1k: Decimal = Field(ge=0)
    currency: str = Field("CNY", max_length=8)
    is_active: bool = True
