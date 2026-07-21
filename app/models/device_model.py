"""ORM model for device_models (platform-level device catalogue).

A ``DeviceModel`` is a platform-level entity — the catalogue of device
*types* a tenant can instantiate (e.g. "Blood-pressure chamber X100",
"Smart ring R2"). It has **no tenant_id**: the catalogue is shared across
all tenants, mirroring the ``Group`` convention.

Permissions are platform-level: writes are guarded by
``require_super_admin()`` (only the platform super admin can reshape the
catalogue), while reads are open to any authenticated user — the service
splits super_admin / hq_staff (full fields incl. ``unit_cost``) from
tenant users (only ``id``, ``name``, ``specs.form_factor`` for the
device-picker dropdown).

Soft-deleted (``is_deleted`` + partial unique index on ``name`` so a
deleted model's name can be reused, mirroring the Group/User/Role
convention).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class DeviceModel(Base):
    """A device model in the shared platform catalogue (no ``tenant_id``).

    Stores brand/supplier for procurement, a free-form ``specs`` JSONB for
    physical attributes (``form_factor`` is the only conventionally-used
    key — drives the device-picker dropdown grouping), and a Decimal
    ``unit_cost`` aligned with the project's money-column convention
    (``Numeric(12, 2)``, see ``usage_event.cost``). Soft-deleted; a
    deleted model's name can be reused.
    """

    __tablename__ = "device_models"
    __table_args__ = (
        # Partial unique index: at most one *live* model per name. Soft-deleted
        # rows keep their name but are exempt, so names can be reused after
        # deletion. Mirrored PG/SQLite — see Group.uq_groups_code_active.
        Index(
            "uq_device_models_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Unit procurement cost. Decimal to match project money-column convention
    # (usage_event.cost / model_pricing.*); NOT StorePilot's cents INTEGER.
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Free-form physical specs. ``form_factor`` is the only key the device
    # picker dropdown relies on; everything else is up to the catalogue editor.
    # PUT semantics = whole-replace (no jsonb_set partial update).
    specs: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        default=dict,
        server_default=text("'{}'"),
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<DeviceModel {self.id} {self.name}>"


# Re-export for callers that need it.
__all__ = ["DeviceModel"]
