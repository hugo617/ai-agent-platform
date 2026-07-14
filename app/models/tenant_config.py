"""ORM model for per-tenant white-label branding config.

One row per tenant carries the store's brand identity: display name (overrides
the default tenant name in the top bar), logo URL, theme color (applied
globally via the ``--primary`` CSS variable), and login-page text. This is the
white-label foundation — a logged-in user sees their tenant's brand, not the
platform default.

Design (matches the ``LlmConfig`` config-table convention — no soft-delete):

- **One row per tenant**, enforced at the DB layer by a unique constraint on
  ``tenant_id`` (the dashboard task learned the alembic-check drift lesson: the
  constraint is declared in ``__table_args__`` *and* created by the migration so
  autogenerate sees model and DB in sync).
- **No soft-delete**: branding is a live config, not a business entity. Matches
  ``LlmConfig`` / ``Tenant``, which also don't soft-delete.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class TenantConfig(Base):
    """The white-label branding config for one tenant (one row per tenant).

    ``theme_color`` is stored as ``#RRGGBB`` (7 chars) and converted to the HSL
    format the shadcn CSS variable expects on the frontend. All fields are
    optional — a tenant with no row renders the platform defaults.
    """

    __tablename__ = "tenant_configs"
    __table_args__ = (
        # At most one branding row per tenant. Mirrored in the migration so
        # ``alembic check`` sees model and DB in sync (the dashboard task hit a
        # CI drift failure by creating a DB object not declared in the model).
        UniqueConstraint("tenant_id", name="uq_tenant_config_tenant"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Overrides the default tenant name shown in the top bar / login page.
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Logo URL (upload lands in task 56 — file-upload; for now a pasted URL).
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ``#RRGGBB``; converted to HSL on the frontend and applied as --primary.
    theme_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Free-text shown on the login page (welcome message / instructions).
    login_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<TenantConfig {self.id} tenant={self.tenant_id}>"
