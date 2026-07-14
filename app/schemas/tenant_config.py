"""Pydantic schemas for tenant branding config DTOs.

Naming follows the project convention: ``Update`` for write payloads, ``Read``
for API responses. ``theme_color`` is validated as ``#RRGGBB`` via a regex
``pattern`` on the Field (a native constraint) so the validation error stays a
plain string — a hand-rolled ``field_validator`` raising ``ValueError`` would
embed the raw exception object in the error's ``ctx``, which the FastAPI
validation-error handler then fails to JSON-serialize.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ``#RRGGBB`` (case-insensitive). Kept as a module constant so the migration
# docstring and a future frontend reference share one source of truth.
THEME_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class TenantConfigUpdate(BaseModel):
    """Payload for PUT /tenant-config.

    All fields optional — omit a field to leave it unchanged. The frontend sends
    all four on save, so a ``None`` means "clear this field".
    """

    display_name: str | None = Field(None, max_length=128)
    logo_url: str | None = Field(None, max_length=255)
    theme_color: str | None = Field(None, max_length=7, pattern=THEME_COLOR_PATTERN)
    login_text: str | None = None


class TenantConfigRead(BaseModel):
    """Branding config returned by GET endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    display_name: str | None
    logo_url: str | None
    theme_color: str | None
    login_text: str | None
    created_at: datetime
    updated_at: datetime
