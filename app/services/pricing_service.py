"""Pricing write service — model pricing row lifecycle (super-admin writes).

Owns the three pricing write paths (upsert / update / deactivate) that used to
live inline in ``app/api/v1/billing.py``: business logic, audit records, and
the business ``commit()`` all live here, with every audit ``record`` inside
the caller's commit scope (the ``BillingService.recharge`` record→commit
atomic precedent — audit rows commit together with the business write and can
never dangle). Read-side price resolution (tenant override > platform
default) stays in ``BillingService.calc_cost``.
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_pricing import ModelPricing
from app.repositories.wallet import ModelPricingRepository
from app.schemas.billing import ModelPricingUpsert
from app.services.logging_service import LoggingService


def _pricing_snapshot(row: ModelPricing) -> dict:
    """JSON-safe before/after snapshot of a pricing row for the audit log.

    Decimals are stringified — the SystemLog JSON column cannot serialise
    Decimal objects (an unserialisable payload would silently drop the audit
    row inside LoggingService's best-effort catch). Quantised to the column's
    Numeric(10,6) scale so DB-loaded old values and in-memory payload values
    render identically, mirroring how the API itself serialises prices.
    """
    q = Decimal("0.000001")
    return {
        "tenant_id": row.tenant_id,
        "model": row.model,
        "input_price_per_1k": str(row.input_price_per_1k.quantize(q)),
        "output_price_per_1k": str(row.output_price_per_1k.quantize(q)),
        "is_active": row.is_active,
    }


def _pricing_scope(tenant_id: str | None) -> str:
    return "platform" if tenant_id is None else "tenant"


class PricingService:
    """Pricing row lifecycle: upsert, update, deactivate (audit + commit)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ModelPricingRepository(db)

    async def upsert(
        self, payload: ModelPricingUpsert, operator_id: str
    ) -> ModelPricing:
        """Create or update a pricing row (one active row per scope+model)."""
        # Look up an existing active row for the same (tenant_id, model) scope.
        existing = await self.repo.get_active_for_scope(
            payload.model, payload.tenant_id
        )
        scope = _pricing_scope(payload.tenant_id)
        if existing is not None:
            old_values = _pricing_snapshot(existing)
            existing.input_price_per_1k = payload.input_price_per_1k
            existing.output_price_per_1k = payload.output_price_per_1k
            existing.is_active = payload.is_active
            await LoggingService(self.db).record(
                action="pricing.upsert",
                module="billing",
                message=f"updated pricing for model {payload.model} (scope={scope})",
                user_id=operator_id,
                tenant_id=payload.tenant_id,
                level="info",
                resource_type="model_pricing",
                resource_id=existing.id,
                details={"scope": scope},
                old_values=old_values,
                new_values=_pricing_snapshot(existing),
            )
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        row = ModelPricing(
            tenant_id=payload.tenant_id,
            model=payload.model,
            input_price_per_1k=payload.input_price_per_1k,
            output_price_per_1k=payload.output_price_per_1k,
            is_active=payload.is_active,
        )
        await self.repo.add(row)
        await LoggingService(self.db).record(
            action="pricing.upsert",
            module="billing",
            message=f"created pricing for model {payload.model} (scope={scope})",
            user_id=operator_id,
            tenant_id=payload.tenant_id,
            level="info",
            resource_type="model_pricing",
            resource_id=row.id,
            details={"scope": scope},
            new_values=_pricing_snapshot(row),
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update(
        self, pricing_id: str, payload: ModelPricingUpsert, operator_id: str
    ) -> ModelPricing | None:
        """Replace a pricing row's fields; None when the id doesn't exist.

        None is the API layer's signal to raise 404 (the PUT /wallet
        precedent) — this service never raises HTTP-aware errors.
        """
        row = await self.repo.get(pricing_id)
        if row is None:
            return None
        old_values = _pricing_snapshot(row)
        row.tenant_id = payload.tenant_id
        row.model = payload.model
        row.input_price_per_1k = payload.input_price_per_1k
        row.output_price_per_1k = payload.output_price_per_1k
        row.is_active = payload.is_active
        scope = _pricing_scope(payload.tenant_id)
        await LoggingService(self.db).record(
            action="pricing.update",
            module="billing",
            message=f"updated pricing {pricing_id}",
            user_id=operator_id,
            tenant_id=payload.tenant_id,
            level="info",
            resource_type="model_pricing",
            resource_id=row.id,
            details={"scope": scope},
            old_values=old_values,
            new_values=_pricing_snapshot(row),
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def deactivate(
        self, pricing_id: str, operator_id: str
    ) -> ModelPricing | None:
        """Deactivate a pricing row (soft delete); None when the id doesn't exist.

        Rows are deactivated rather than hard-deleted so historical charges
        remain interpretable. Returns the deactivated row; the API layer
        discards it (204, no body).
        """
        row = await self.repo.get(pricing_id)
        if row is None:
            return None
        old_values = _pricing_snapshot(row)
        row.is_active = False
        await LoggingService(self.db).record(
            action="pricing.deactivate",
            module="billing",
            message=f"deactivated pricing {pricing_id}",
            user_id=operator_id,
            tenant_id=row.tenant_id,
            level="warn",  # destructive — mirrors user.delete / role.revoke
            resource_type="model_pricing",
            resource_id=row.id,
            details={"scope": _pricing_scope(row.tenant_id)},
            old_values=old_values,
            new_values={"is_active": False},
        )
        await self.db.commit()
        return row
