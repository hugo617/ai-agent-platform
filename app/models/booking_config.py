"""ORM model for booking schedule-grid configuration.

A row holds the **booking-window defaults** the HqView schedule grid renders
against: how long a slot is (``default_duration_minutes``) and which hours of
the day are bookable (``window_start`` / ``window_end``, ``HH:MM`` strings).

Two scopes share one table, mirroring ``ModelPricing`` / ``LlmConfig``:

  - **platform default**: ``tenant_id IS NULL`` — the fallback for any tenant
    without its own row. Seeded by the slice-01 migration
    (duration=45 / 08:00-22:00) so the grid has sane defaults on first boot.
  - **tenant override**: ``tenant_id = <id>`` — one store's local override
    (e.g. 60-minute slots, 09:00-21:00).

Uniqueness is enforced at the service layer (one row per scope), NOT by a DB
constraint: a partial unique index on a nullable ``tenant_id`` would need
``NULLS NOT DISTINCT`` semantics that differ between Postgres and SQLite,
clashing with the project's dual-DB rule (see ``ModelPricing`` / ``LlmConfig``
for the same decision).

Resolution order in ``BookingConfigService.get_effective``:
  tenant override (tenant_id=X) > platform default (tenant_id IS NULL) >
  hardcoded defaults (45 / 08:00 / 22:00 — the same values the migration seeds,
  kept as a code-level fallback so a fresh DB without the seed row still works).

``default_duration_minutes`` is a free-form ``Integer`` (D3 in the plan): the
frontend validates a sensible range (15-240) via preset buttons + custom input,
the backend only rejects non-positive values. This avoids "add a 30-minute
preset → enum migration" churn — any minute count the store wants just stores.

``window_start`` / ``window_end`` are ``HH:MM`` strings (not ``Time`` columns):
SQLite has no native TIME type and would coerce to TEXT anyway, so storing TEXT
keeps both backends byte-identical and lets the frontend pass ``<input
type="time">`` values through unchanged.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class BookingConfig(Base):
    """Booking-window defaults for the schedule grid, platform-wide or
    tenant-overridden.

    ``default_duration_minutes`` is the slot length clicked on the grid (45 =
    one full row + one half row highlight; 60 = two full rows).
    ``window_start`` / ``window_end`` bound the grid's time axis
    (``HH:MM`` wall-clock, e.g. "08:00" / "22:00").
    """

    __tablename__ = "booking_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # NULL = platform-wide default; non-null = tenant override.
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    default_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=45, server_default=text("45")
    )
    window_start: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    window_end: Mapped[str] = mapped_column(String(5), nullable=False, default="22:00")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        scope = self.tenant_id or "platform"
        return (
            f"<BookingConfig {self.id} scope={scope} "
            f"dur={self.default_duration_minutes}min "
            f"window={self.window_start}-{self.window_end}>"
        )
