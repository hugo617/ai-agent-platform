"""ORM model for per-model token pricing.

A row gives the price per 1k tokens for one model. Two scopes share one table,
mirroring ``LlmConfig``:

  - **platform default**: ``tenant_id IS NULL`` — the fallback for any tenant
    without its own row for the model.
  - **tenant override**: ``tenant_id = <id>`` — the platform's markup/discount
    for a specific store (e.g. wholesale vs. retail customers).

Uniqueness is enforced at the service layer (one active row per model per
scope), NOT by a DB constraint: a partial unique index on ``tenant_id`` would
need ``NULLS NOT DISTINCT`` semantics that differ between Postgres and SQLite,
clashing with the project's dual-DB rule (see ``LlmConfig`` for the same
decision).

Resolution order in ``BillingService.calc_cost``:
  tenant override (tenant_id=X, model=Y) > platform default (tenant_id IS NULL,
  model=Y) > "unconfigured" (cost = 0 — allow the chat, record cost=0).

Prices are ``Numeric(10,6)`` to hold sub-cent precision (e.g. DeepSeek's
per-million pricing ÷ 1000). The MVP charges in CNY only; a currency column
was removed as a dead field (multi-currency can be re-added when needed).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class ModelPricing(Base):
    """Price per 1k tokens for one model, platform-wide or tenant-overridden.

    ``input_price_per_1k`` covers prompt tokens; ``output_price_per_1k`` covers
    completion tokens. Both are per *1k* tokens — ``BillingService.calc_cost``
    computes ``prompt/1000*in + completion/1000*out``.
    """

    __tablename__ = "model_pricing"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # NULL = platform-wide default; non-null = tenant override.
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
    output_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        scope = self.tenant_id or "platform"
        return (
            f"<ModelPricing {self.id} scope={scope} model={self.model} "
            f"in={self.input_price_per_1k} out={self.output_price_per_1k}>"
        )
