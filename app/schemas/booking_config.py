"""Pydantic schemas for the booking schedule-grid config DTOs.

Naming follows the project convention: ``Upsert`` for write payloads (the
service does upsert, not create-vs-update), ``Read`` for API responses. A
separate ``Effective`` shape carries the resolved three-level fallback so the
``GET /effective`` endpoint can signal which scope won (tenant vs platform vs
hardcoded default).

``default_duration_minutes`` is a free-form ``Integer`` (D3 in the plan): the
backend rejects only non-positive values, the frontend enforces a sensible
range (15-240) via preset buttons + custom input. This avoids enum churn.

``window_start`` / ``window_end`` are ``HH:MM`` strings (24-hour): validated via
a regex ``pattern`` on the Field (native constraint) so a malformed value
surfaces as a clean 422 string rather than a serializer-incompatible error.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ``HH:MM`` 24-hour (00:00-23:59). Kept as a module constant so the migration
# seed docstring and any future frontend reference share one source of truth.
HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class BookingConfigUpsert(BaseModel):
    """Payload for PUT /bookings/config/platform and /bookings/config/tenant/{id}.

    All three fields are required — the frontend sends all of them on save, so
    the service upsert treats every field as authoritative (a full replace,
    not a partial patch; mirrors ``TenantConfigService.upsert``).
    """

    default_duration_minutes: int = Field(ge=1, description="单时段时长(分钟,正整数)")
    window_start: str = Field(min_length=5, max_length=5, pattern=HHMM_PATTERN)
    window_end: str = Field(min_length=5, max_length=5, pattern=HHMM_PATTERN)


class BookingConfigRead(BaseModel):
    """One config row (platform default or tenant override)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = Field(None, description="NULL=平台默认;非空=租户覆盖")
    default_duration_minutes: int
    window_start: str
    window_end: str
    created_at: datetime
    updated_at: datetime


class EffectiveBookingConfig(BaseModel):
    """The resolved config for one tenant (the three-level fallback result).

    ``source`` records which scope won so the frontend can badge "using
    platform default" vs "using this store's override" vs "no config row yet —
    using hardcoded defaults".
    """

    default_duration_minutes: int
    window_start: str
    window_end: str
    source: str = Field(
        description="生效来源:tenant / platform / default(硬编码兜底)"
    )
