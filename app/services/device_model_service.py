"""DeviceModel service — platform-level CRUD over the device catalogue.

Permission model differs from tenant-scoped services:
- **Writes** (create/update/delete) are guarded at the API layer by
  ``require_super_admin()`` — only the platform super admin can reshape the
  catalogue. The service does NOT re-check (avoids duplication).
- **Reads** (list/get) are open to any authenticated user. The service
  splits the view: super_admin / hq_staff (cross-tenant viewers) get the
  full DTO incl. ``unit_cost`` and complete ``specs``; tenant users get a
  minimal ``{id, name, specs.form_factor}`` DTO for the device-picker
  dropdown.

``device_models`` is intentionally absent from ``DEFAULT_*_PERMS`` — tenant
roles have no casbin grant for it, and reads don't consult casbin (they're
gated by authentication alone).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_model import DeviceModel
from app.repositories.device_model import DeviceModelRepository
from app.schemas.device_model import (
    DeviceModelCreate,
    DeviceModelPublicRead,
    DeviceModelRead,
    DeviceModelUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import is_cross_tenant_viewer


class DeviceModelService:
    OBJECT = "device_models"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DeviceModelRepository(db)

    # ------------------------------------------------------------- helpers

    async def _to_read(self, model: DeviceModel) -> DeviceModelRead:
        """Build the full read DTO (super_admin / hq_staff view)."""
        data = {c.name: getattr(model, c.name) for c in model.__table__.columns}
        return DeviceModelRead.model_validate(data)

    async def _to_public_read(self, model: DeviceModel) -> DeviceModelPublicRead:
        """Build the minimal read DTO for tenant users.

        Only ``id``, ``name`` and ``specs.form_factor`` are exposed — keeps
        procurement cost and unrelated specs private from store staff.
        """
        form_factor = (model.specs or {}).get("form_factor")
        return DeviceModelPublicRead(
            id=model.id,
            name=model.name,
            specs={"form_factor": form_factor} if form_factor else {},
        )

    async def _get_live(self, model_id: str) -> DeviceModel:
        model = await self.repo.get(model_id)
        if model is None:
            raise NotFoundError(f"device model {model_id} not found")
        return model

    async def _assert_name_unique(
        self, name: str | None, exclude_id: str | None
    ) -> None:
        """Raise BizError if a *live* device model already uses this name."""
        if not name:
            return
        existing = await self.repo.get_by_name(name)
        if existing is not None and existing.id != exclude_id:
            raise BizError(f"设备型号名称已存在: {name}")

    @staticmethod
    def _assert_unit_cost_nonnegative(unit_cost: Decimal | None) -> None:
        """Raise BizError if unit_cost is negative. Kept in the service layer
        (not as a Pydantic ``ge=0``) because Pydantic surfaces the raw Decimal
        in the 422 error detail, which starlette's JSONResponse can't
        serialize. Matches the project money-column convention."""
        if unit_cost is not None and unit_cost < 0:
            raise BizError(f"unit_cost 不能为负数: {unit_cost}")

    # ----------------------------------------------------------------- read

    async def list(
        self, platform_role: str | None = None
    ) -> list[DeviceModelRead] | list[DeviceModelPublicRead]:
        """Cross-tenant viewers (super_admin / hq_staff) → full read DTOs;
        tenant users → minimal public DTOs for the device-picker dropdown."""
        models = await self.repo.list_all()
        if is_cross_tenant_viewer(platform_role):
            return [await self._to_read(m) for m in models]
        return [await self._to_public_read(m) for m in models]

    async def get(
        self, model_id: str, platform_role: str | None = None
    ) -> DeviceModelRead | DeviceModelPublicRead:
        model = await self._get_live(model_id)
        if is_cross_tenant_viewer(platform_role):
            return await self._to_read(model)
        return await self._to_public_read(model)

    # ---------------------------------------------------------------- write

    async def create(self, payload: DeviceModelCreate) -> DeviceModelRead:
        self._assert_unit_cost_nonnegative(payload.unit_cost)
        await self._assert_name_unique(payload.name, exclude_id=None)
        model = DeviceModel(
            name=payload.name,
            brand=payload.brand,
            supplier=payload.supplier,
            unit_cost=payload.unit_cost,
            specs=payload.specs,
        )
        await self.repo.add(model)
        await self.db.commit()
        # Re-fetch so server defaults (created_at/updated_at) are loaded.
        fresh = await self.repo.get(model.id)
        assert fresh is not None  # just created, must exist
        return await self._to_read(fresh)

    async def update(
        self, model_id: str, payload: DeviceModelUpdate
    ) -> DeviceModelRead:
        model = await self._get_live(model_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data:
            await self._assert_name_unique(data["name"], exclude_id=model_id)
        if "unit_cost" in data:
            self._assert_unit_cost_nonnegative(data["unit_cost"])
        # ``specs`` whole-replace: include_unset means if the client sent a
        # specs dict, we set the column to that exact dict (no jsonb_set
        # partial update). If they didn't send specs, it stays untouched.
        for key, value in data.items():
            setattr(model, key, value)
        await self.db.flush()
        await self.db.commit()
        # Re-fetch: commit expires the ORM object, and reading its attributes
        # would otherwise trigger a lazy async load (MissingGreenlet).
        fresh = await self.repo.get(model_id)
        assert fresh is not None  # just updated, must exist
        return await self._to_read(fresh)

    async def delete(self, model_id: str) -> None:
        """Soft-delete. The row stays so historical references (devices that
        were instantiated from it) remain resolvable; the name becomes
        reusable via the partial unique index."""
        model = await self._get_live(model_id)
        model.is_deleted = True
        model.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()
