"""Device service — tenant-scoped CRUD over device instances.

Slice 01 scope: within-store CRUD only. owner/admin can create/read/update/
delete devices in their own tenant; member is read-only; cross-tenant access
(HQ panorama for super_admin / hq_staff) and customer binding (bind/unbind)
land in slices 03 / 04.

Three integrity guards worth calling out (see plan-devices-crud-ui.md §3
关键边界 #1):

- ``_assert_model_live`` — the *real* model_id guard. The FK
  ``model_id → device_models.id ondelete=RESTRICT`` is a dead-bolt that
  never fires today (``DeviceModelService.delete`` is soft-delete only).
  This service-level check is what actually prevents a device from being
  created or re-pointed at a soft-deleted / nonexistent model.
- ``_assert_serial_unique`` — enforces the (tenant_id, serial_number)
  invariant among *live* rows. Mirrors the partial unique index in the DB;
  raising BizError here gives a clean 400 instead of letting the
  IntegrityError bubble up as a 500.
- ``_get_live_device`` — uses ``get_for_tenant`` so a cross-tenant lookup
  returns NotFoundError (404) instead of leaking "exists but not yours"
  (prevents enumeration).
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.repositories.device import DeviceRepository
from app.repositories.device_model import DeviceModelRepository
from app.schemas.device import (
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import permission_service


class DeviceService:
    OBJECT = "devices"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DeviceRepository(db)
        self.models = DeviceModelRepository(db)

    # ------------------------------------------------------------- helpers

    async def _to_read(self, device: Device) -> DeviceRead:
        data = {c.name: getattr(device, c.name) for c in device.__table__.columns}
        return DeviceRead.model_validate(data)

    async def _get_live_device(self, device_id: str, tenant_id: str) -> Device:
        """Fetch a device, enforcing tenancy + soft-delete.

        Cross-tenant / soft-deleted / nonexistent all collapse to the same
        NotFoundError so the API can't be probed for "does this id exist in
        another tenant" (enumeration defence).
        """
        device = await self.repo.get_for_tenant(device_id, tenant_id)
        if device is None:
            raise NotFoundError(f"设备不存在: {device_id}")
        return device

    async def _assert_serial_unique(
        self,
        tenant_id: str,
        serial_number: str,
        *,
        exclude_id: str | None = None,
    ) -> None:
        """Raise BizError if a *live* device in this tenant already uses serial."""
        existing = await self.repo.get_by_tenant_serial(
            tenant_id, serial_number, exclude_id=exclude_id
        )
        if existing is not None:
            raise BizError(f"设备序列号在本门店已存在: {serial_number}")

    async def _assert_model_live(self, model_id: str) -> None:
        """Raise BizError if the model is soft-deleted or doesn't exist.

        ``DeviceModelRepository.get`` already filters ``is_deleted=False``,
        so a soft-deleted model returns None here — same path as nonexistent.
        This is the *real* model_id integrity guard: the FK RESTRICT dead-
        bolt never fires under the current (soft-delete-only) model service.
        """
        model = await self.models.get(model_id)
        if model is None:
            raise BizError(f"设备型号不存在或已删除: {model_id}")

    # ----------------------------------------------------------------- read

    async def list(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[DeviceRead]:
        """All live devices in the caller's tenant.

        Cross-tenant viewers (super_admin / hq_staff) currently also land
        here — slice 01 keeps the router-level ``require_permission`` guard,
        so hq_staff is 403'd before reaching this method. Slice 03 will
        swap in the HQ panorama branch.
        """
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "read",
            platform_role=platform_role,
        )
        devices = await self.repo.list_for_tenant(tenant_id)
        return [await self._to_read(d) for d in devices]

    async def get(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        platform_role: str | None = None,
    ) -> DeviceRead:
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "read",
            platform_role=platform_role,
        )
        device = await self._get_live_device(device_id, tenant_id)
        return await self._to_read(device)

    # ---------------------------------------------------------------- write

    async def create(
        self,
        actor_id: str,
        tenant_id: str,
        payload: DeviceCreate,
        platform_role: str | None = None,
    ) -> DeviceRead:
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "create",
            platform_role=platform_role,
        )
        await self._assert_model_live(payload.model_id)
        await self._assert_serial_unique(tenant_id, payload.serial_number)
        device = Device(
            tenant_id=tenant_id,
            model_id=payload.model_id,
            serial_number=payload.serial_number,
            status=payload.status,
            customer_id=payload.customer_id,
            created_by=actor_id,
        )
        await self.repo.add(device)
        await self.db.commit()
        # Re-fetch so server defaults (created_at/updated_at) are loaded —
        # commit expires the ORM object and reading attributes directly
        # would trigger a lazy async load (MissingGreenlet).
        fresh = await self.repo.get_for_tenant(device.id, tenant_id)
        assert fresh is not None  # just created, must exist
        return await self._to_read(fresh)

    async def update(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        payload: DeviceUpdate,
        platform_role: str | None = None,
    ) -> DeviceRead:
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "update",
            platform_role=platform_role,
        )
        device = await self._get_live_device(device_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        if "model_id" in data:
            await self._assert_model_live(data["model_id"])
        if "serial_number" in data:
            await self._assert_serial_unique(
                tenant_id, data["serial_number"], exclude_id=device_id
            )
        # ``status`` Literal + DB CHECK constraint both enforce the 3-state
        # invariant; setattr is safe because schema rejected anything else.
        for key, value in data.items():
            setattr(device, key, value)
        await self.db.flush()
        await self.db.commit()
        fresh = await self.repo.get_for_tenant(device_id, tenant_id)
        assert fresh is not None
        return await self._to_read(fresh)

    async def delete(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        platform_role: str | None = None,
    ) -> None:
        """Soft-delete. The row stays so historical references (bookings,
        audits) remain resolvable; the serial becomes reusable via the
        partial unique index."""
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "delete",
            platform_role=platform_role,
        )
        device = await self._get_live_device(device_id, tenant_id)
        device.is_deleted = True
        device.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()
