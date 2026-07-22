"""Repository for Device.

``Device`` is tenant-scoped (carries ``tenant_id``), so
``DeviceRepository`` extends ``TenantScopedRepository``. The base class's
``get_for_tenant`` / ``list_for_tenant`` would already enforce the
``tenant_id`` filter, but we override both to ALSO exclude soft-deleted
rows — mirroring the ``CustomerProfileRepository`` convention. The base
class can't know about ``is_deleted`` (it's a per-model convention), so
each tenant-scoped soft-delete repository re-states the filter explicitly.

Cross-tenant aggregation (HQ panorama, super_admin / hq_staff) lives in
``list_all_with_meta`` / ``get_all_with_meta``: they pre-load the tenant /
model / customer relationships via ``selectinload`` so the async session
never hits a lazy-load ``MissingGreenlet`` when the service reads
``device.tenant.name``. This is the SQLAlchemy-standard N+1 fix (a few IN
queries instead of N+1) and intentionally does NOT reuse
``customer.batch_tenant_info`` — that helper is customer-domain coupling
and only returns tenant names, whereas the HQ view also needs
model_name / customer_name.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import Base
from app.models.device import Device
from app.repositories.base import TenantScopedRepository


class DeviceRepository(TenantScopedRepository[Device]):
    """Tenant-scoped CRUD over devices, with soft-delete filtering."""

    model = Device

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_for_tenant(
        self, obj_id: str, tenant_id: str
    ) -> Device | None:
        """A store's live device by id (enforces tenant_id + is_deleted)."""
        stmt = select(Device).where(
            Device.id == obj_id,
            Device.tenant_id == tenant_id,
            Device.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: str) -> list[Device]:
        """All live devices in a store, newest first."""
        stmt = (
            select(Device)
            .where(
                Device.tenant_id == tenant_id,
                Device.is_deleted.is_(False),
            )
            .order_by(Device.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_by_tenant_serial(
        self,
        tenant_id: str,
        serial_number: str,
        *,
        exclude_id: str | None = None,
    ) -> Device | None:
        """Live device in a tenant matching a serial (uniqueness check).

        ``exclude_id`` lets ``update`` skip the row being renamed — same
        convention as ``CustomerProfileRepository`` / ``GroupRepository``.
        Only live rows are matched: a soft-deleted device's serial can be
        reused, so it must NOT surface here.
        """
        clauses = [
            Device.tenant_id == tenant_id,
            Device.serial_number == serial_number,
            Device.is_deleted.is_(False),
        ]
        if exclude_id is not None:
            clauses.append(Device.id != exclude_id)
        stmt = select(Device).where(*clauses)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # -------------------------------------------------- HQ panorama (slice 03)

    async def list_all_with_meta(self) -> list[Device]:
        """All live devices across every tenant, with tenant/model/customer
        pre-loaded for the HQ panorama DTO.

        ``selectinload`` issues one extra IN query per relationship (3 here)
        instead of N+1 lazy loads, and — critically for the async session —
        populates the relationship eagerly so reading
        ``device.tenant.name`` later does NOT trigger a lazy load
        (``MissingGreenlet`` under SQLAlchemy 2.0 async). Soft-deleted
        devices are excluded; the related rows are read as-is (a soft-
        deleted tenant/model/customer still has a name to display).
        """
        stmt = (
            select(Device)
            .where(Device.is_deleted.is_(False))
            .options(
                selectinload(Device.tenant),
                selectinload(Device.model),
                selectinload(Device.customer),
            )
            .order_by(Device.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_all_with_meta(self, device_id: str) -> Device | None:
        """One live device by id (any tenant) with relations pre-loaded.

        HQ ``GET /{id}`` path: unlike ``get_for_tenant`` this does NOT
        filter by tenant (the HQ viewer may read any tenant's device), but
        still excludes soft-deleted devices. Returns None if the id is
        absent or soft-deleted — the service turns that into a 404.
        """
        stmt = (
            select(Device)
            .where(
                Device.id == device_id,
                Device.is_deleted.is_(False),
            )
            .options(
                selectinload(Device.tenant),
                selectinload(Device.model),
                selectinload(Device.customer),
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


# Re-export Base for type hints in callers that need it.
__all__ = ["Base", "DeviceRepository"]
