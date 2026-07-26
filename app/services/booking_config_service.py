"""Booking-config service — resolve, read, and write the schedule-grid config.

The central method is :meth:`get_effective`, which walks the three-level
fallback chain (tenant > platform > hardcoded defaults) and returns the
resolved window the HqView grid renders against.

Writes go through upserts that enforce "one row per scope" — there is no DB
unique constraint, so this service is the sole place that guarantee is made
(see the model docstring for why). Each upsert records an audit log row via
:class:`LoggingService` (module ``booking_config``) with old/new values, so
config changes are traceable (who changed which store's slot length).

Mirrors :class:`LlmConfigService` structurally but drops the crypto path (no
secrets here) and adds the audit-log call (config changes are a notable admin
action worth logging, unlike the masked-API-key writes in the LLM path).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking_config import BookingConfig
from app.repositories.booking_config import BookingConfigRepository
from app.schemas.booking_config import (
    BookingConfigRead,
    BookingConfigUpsert,
    EffectiveBookingConfig,
)
from app.services.logging_service import LoggingService

# Hardcoded last-resort defaults. The slice-01 migration seeds the platform
# row with these same values, so on a normally-migrated DB the ``default``
# fallback is never hit — it exists for fresh/test DBs that ran
# ``create_all`` without the migration, so the grid still renders sanely.
_DEFAULT_DURATION = 45
_DEFAULT_WINDOW_START = "08:00"
_DEFAULT_WINDOW_END = "22:00"


def _to_read(row: BookingConfig) -> BookingConfigRead:
    return BookingConfigRead(
        id=row.id,
        tenant_id=row.tenant_id,
        default_duration_minutes=row.default_duration_minutes,
        window_start=row.window_start,
        window_end=row.window_end,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class BookingConfigService:
    async def get_effective(
        self, db: AsyncSession, tenant_id: str
    ) -> EffectiveBookingConfig:
        """Resolve the active config via tenant > platform > hardcoded fallback.

        Returns the window the grid renders against + a ``source`` tag
        (``tenant`` / ``platform`` / ``default``) so the frontend can badge
        which scope won.
        """
        repo = BookingConfigRepository(db)
        tenant_row = await repo.get_for_tenant(tenant_id)
        if tenant_row is not None:
            return EffectiveBookingConfig(
                default_duration_minutes=tenant_row.default_duration_minutes,
                window_start=tenant_row.window_start,
                window_end=tenant_row.window_end,
                source="tenant",
            )
        platform_row = await repo.get_platform()
        if platform_row is not None:
            return EffectiveBookingConfig(
                default_duration_minutes=platform_row.default_duration_minutes,
                window_start=platform_row.window_start,
                window_end=platform_row.window_end,
                source="platform",
            )
        return EffectiveBookingConfig(
            default_duration_minutes=_DEFAULT_DURATION,
            window_start=_DEFAULT_WINDOW_START,
            window_end=_DEFAULT_WINDOW_END,
            source="default",
        )

    async def get_platform(self, db: AsyncSession) -> BookingConfigRead | None:
        row = await BookingConfigRepository(db).get_platform()
        return _to_read(row) if row else None

    async def get_tenant(
        self, db: AsyncSession, tenant_id: str
    ) -> BookingConfigRead | None:
        row = await BookingConfigRepository(db).get_for_tenant(tenant_id)
        return _to_read(row) if row else None

    async def _upsert(
        self,
        db: AsyncSession,
        payload: BookingConfigUpsert,
        existing: BookingConfig | None,
        *,
        tenant_id: str | None,
        actor_id: str,
    ) -> BookingConfigRead:
        """Create or patch one config row, then write an audit log entry.

        Every field on the payload is authoritative (the frontend sends all
        three on save), so there is no "patch a subset" path — same contract as
        ``TenantConfigService.upsert``.
        """
        old_values: dict | None = None
        # "tenant=<id>" for a tenant override, "platform" for the platform row —
        # computed once and reused in both the action message and the audit log.
        message_scope = f"tenant={tenant_id}" if tenant_id else "platform"
        if existing is not None:
            old_values = {
                "default_duration_minutes": existing.default_duration_minutes,
                "window_start": existing.window_start,
                "window_end": existing.window_end,
            }
            existing.default_duration_minutes = payload.default_duration_minutes
            existing.window_start = payload.window_start
            existing.window_end = payload.window_end
            row = existing
            action = "booking_config.update"
            message = f"updated booking config ({message_scope})"
        else:
            row = BookingConfig(
                tenant_id=tenant_id,
                default_duration_minutes=payload.default_duration_minutes,
                window_start=payload.window_start,
                window_end=payload.window_end,
            )
            db.add(row)
            action = "booking_config.create"
            message = f"created booking config ({message_scope})"

        await db.flush()
        await db.commit()
        await db.refresh(row)
        read = _to_read(row)

        await LoggingService(db).record(
            action=action,
            module="booking_config",
            message=message,
            user_id=actor_id,
            tenant_id=tenant_id,
            level="info",
            resource_type="booking_config",
            resource_id=row.id,
            old_values=old_values,
            new_values={
                "default_duration_minutes": row.default_duration_minutes,
                "window_start": row.window_start,
                "window_end": row.window_end,
            },
        )
        return read

    async def upsert_platform(
        self, db: AsyncSession, payload: BookingConfigUpsert, *, actor_id: str
    ) -> BookingConfigRead:
        existing = await BookingConfigRepository(db).get_platform()
        return await self._upsert(db, payload, existing, tenant_id=None, actor_id=actor_id)

    async def upsert_tenant(
        self,
        db: AsyncSession,
        tenant_id: str,
        payload: BookingConfigUpsert,
        *,
        actor_id: str,
    ) -> BookingConfigRead:
        existing = await BookingConfigRepository(db).get_for_tenant(tenant_id)
        return await self._upsert(
            db, payload, existing, tenant_id=tenant_id, actor_id=actor_id
        )


booking_config_service = BookingConfigService()
