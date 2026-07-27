"""Device service — tenant-scoped CRUD over device instances.

Reads branch on the caller's platform role:
- **Within-store** (owner / admin / member): ``require_permission("devices",
  "read")`` then ``DeviceRead`` scoped to the caller's tenant (member is
  read-only — the casbin grant only includes ``devices:read``).
- **HQ panorama** (super_admin / hq_staff): no per-tenant permission check
  (hq_staff has no tenant role at all) — instead the bypass lives in
  ``permission_service.check`` (``platform_role == "hq_staff" and act ==
  "read"`` short-circuits to True, ``super_admin`` bypasses everything).
  Returns ``DeviceHqRead`` across every tenant with tenant/model/customer
  names pre-loaded (selectinload, see ``DeviceRepository.list_all_with_meta``).

Writes (create / update / delete / bind / unbind) branch on the caller's
platform role (platform-cross-tenant-write slice 01):
- **Within-store** (owner / admin / member): ``require_permission("devices",
  "<act>")`` in the caller's tenant. ``effective_tenant_id = user.tenant_id``.
- **Platform writer** (super_admin / hq_staff): skip the casbin ``require``
  (hq_staff has no tenant role) and resolve the target from
  ``payload.tenant_id`` via ``resolve_target_tenant``. Store roles that carry
  ``payload.tenant_id`` are refused with 400 (anti-forgery, see
  ``_tenant_target``). Bind / unbind use the same branch — they're within-store
  business actions that platform writers may perform on a target store's
  device. The HQ viewer is no longer read-only by construction.

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
- ``_assert_customer_in_tenant`` — the bind guard (slice 04). Customer is
  platform-level, so the check is "live ``CustomerProfile`` in this tenant"
  via ``get_by_customer_tenant``; nonexistent + cross-tenant both collapse
  to one BizError 400 (no customer enumeration, same logic as the device
  cross-tenant → 404 defence).
- ``_get_live_device`` — uses ``get_for_tenant`` so a cross-tenant lookup
  returns NotFoundError (404) instead of leaking "exists but not yours"
  (prevents enumeration).
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.repositories.customer import CustomerProfileRepository
from app.repositories.device import DeviceRepository
from app.repositories.device_model import DeviceModelRepository
from app.schemas.device import (
    DeviceCreate,
    DeviceHqRead,
    DeviceRead,
    DeviceUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import permission_service
from app.services.principal import Principal


class DeviceService:
    OBJECT = "devices"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DeviceRepository(db)
        self.models = DeviceModelRepository(db)
        self.customers = CustomerProfileRepository(db)
        # Principal absorbs the role + tenant + scope reasoning that used to be
        # inlined as ``resolve_target_tenant`` / ``is_platform_writer`` /
        # ``is_cross_tenant_viewer`` calls in each method. Holds the same db
        # session object — no duplicate lifecycle (plan-principal-module.md §4.1).
        self.principal = Principal(db)

    # ------------------------------------------------------------- helpers

    async def _to_read(self, device: Device) -> DeviceRead:
        data = {c.name: getattr(device, c.name) for c in device.__table__.columns}
        return DeviceRead.model_validate(data)

    async def _to_hq_read(self, device: Device) -> DeviceHqRead:
        """Build the HQ panorama DTO from a device whose tenant/model/customer
        relationships are already loaded (by ``list_all_with_meta`` /
        ``get_all_with_meta``). Reading ``device.tenant.name`` here is safe
        because the repository ``selectinload``-ed them — no lazy load, no
        ``MissingGreenlet``.

        ``*_name`` fall back to None if the relationship is unloaded or the
        related row is gone (soft-deleted tenant/model, or no customer
        binding) — the HQ view still shows the device.
        """
        data = {c.name: getattr(device, c.name) for c in device.__table__.columns}
        tenant = getattr(device, "tenant", None)
        model = getattr(device, "model", None)
        customer = getattr(device, "customer", None)
        data["tenant_name"] = getattr(tenant, "name", None)
        data["model_name"] = getattr(model, "name", None)
        data["customer_name"] = getattr(customer, "name", None)
        return DeviceHqRead.model_validate(data)

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

    async def _assert_customer_in_tenant(
        self, tenant_id: str, customer_id: str
    ) -> None:
        """Raise BizError if ``customer_id`` has no *live* profile in this tenant.

        Customer is a platform-level table (no ``tenant_id``); the same person
        may have profiles in many stores. So the bind check is "does this
        customer have a live ``CustomerProfile`` in *my* tenant", via
        ``CustomerProfileRepository.get_by_customer_tenant``. A nonexistent
        customer and a customer that exists only in another tenant both return
        None here and collapse to the same BizError 400 — no enumeration leak
        (mirrors the device cross-tenant → 404 defence).
        """
        profile = await self.customers.get_by_customer_tenant(
            customer_id, tenant_id
        )
        if profile is None:
            raise BizError(f"客户在本门店不存在: {customer_id}")

    # ----------------------------------------------------------------- read

    async def list(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[DeviceRead] | list[DeviceHqRead]:
        """Live devices for the caller.

        Cross-tenant viewers (super_admin / hq_staff) get the HQ panorama
        — every tenant's devices as ``DeviceHqRead`` with tenant/model/
        customer names. No per-tenant ``require`` runs for them: hq_staff
        has no tenant role, and the read bypass lives in
        ``permission_service.check`` (``hq_staff`` + ``read`` → True).

        Tenant roles (owner / admin / member) get their own tenant's
        devices as ``DeviceRead`` after ``require("devices", "read")``
        (member passes because the default perms grant ``devices:read``).
        """
        access = await self.principal.for_read(
            actor_id=actor_id, user_tenant_id=tenant_id,
            obj=self.OBJECT, act="read", platform_role=platform_role,
        )
        if access.is_panorama:
            devices = await self.repo.list_all_with_meta()
            return [await self._to_hq_read(d) for d in devices]
        assert access.require is not None  # store branch always sets it
        await permission_service.require(
            actor_id, access.effective_tenant,
            access.require.obj, access.require.act,
            platform_role=platform_role,
        )
        devices = await self.repo.list_for_tenant(access.effective_tenant)
        return [await self._to_read(d) for d in devices]

    async def get(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        platform_role: str | None = None,
    ) -> DeviceRead | DeviceHqRead:
        """One device for the caller.

        Cross-tenant viewers (super_admin / hq_staff) read any tenant's
        device via ``get_all_with_meta`` → ``DeviceHqRead``; a missing or
        soft-deleted device collapses to NotFoundError (404), same surface
        as the within-store path (no enumeration leak).

        Tenant roles go through ``require("devices", "read")`` +
        ``_get_live_device`` (tenant-scoped, so a foreign device is 404).
        """
        access = await self.principal.for_read(
            actor_id=actor_id, user_tenant_id=tenant_id,
            obj=self.OBJECT, act="read", platform_role=platform_role,
        )
        if access.is_panorama:
            device = await self.repo.get_all_with_meta(device_id)
            if device is None:
                raise NotFoundError(f"设备不存在: {device_id}")
            return await self._to_hq_read(device)
        assert access.require is not None  # store branch always sets it
        await permission_service.require(
            actor_id, access.effective_tenant,
            access.require.obj, access.require.act,
            platform_role=platform_role,
        )
        device = await self._get_live_device(device_id, access.effective_tenant)
        return await self._to_read(device)

    # ---------------------------------------------------------------- write

    async def create(
        self,
        actor_id: str,
        tenant_id: str,
        payload: DeviceCreate,
        platform_role: str | None = None,
    ) -> DeviceRead:
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=payload.tenant_id,
            obj=self.OBJECT, act="create", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        await self._assert_model_live(payload.model_id)
        await self._assert_serial_unique(effective_tenant, payload.serial_number)
        # Platform writers cross-tenant bind at create time must point at a
        # customer that has a live profile in the *target* tenant (D2-ii).
        # Store roles historically treat ``customer_id`` as an unchecked create-
        # time hint (the real guard is the bind endpoint) — keep that path
        # unchanged to avoid a within-store behaviour shift outside this slice.
        # ``access.require is None`` is the platform-writer signal — the
        # Principal invariant (plan §4.0 Q3') makes it equivalent to the old
        # ``is_platform_writer(platform_role)`` check.
        if access.require is None and payload.customer_id is not None:
            await self._assert_customer_in_tenant(
                effective_tenant, payload.customer_id
            )
        device = Device(
            tenant_id=effective_tenant,
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
        fresh = await self.repo.get_for_tenant(device.id, effective_tenant)
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
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=payload.tenant_id,
            obj=self.OBJECT, act="update", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        device = await self._get_live_device(device_id, effective_tenant)
        data = payload.model_dump(exclude_unset=True)
        # ``tenant_id`` is a request-scoped routing field (which store to write
        # into), NOT an updatable column — drop it before setattr loop. The
        # device's tenant is already locked by ``_get_live_device`` above.
        data.pop("tenant_id", None)
        if "model_id" in data:
            await self._assert_model_live(data["model_id"])
        if "serial_number" in data:
            await self._assert_serial_unique(
                effective_tenant, data["serial_number"], exclude_id=device_id
            )
        # ``status`` Literal + DB CHECK constraint both enforce the 3-state
        # invariant; setattr is safe because schema rejected anything else.
        for key, value in data.items():
            setattr(device, key, value)
        await self.db.flush()
        await self.db.commit()
        fresh = await self.repo.get_for_tenant(device_id, effective_tenant)
        assert fresh is not None
        return await self._to_read(fresh)

    async def delete(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        *,
        target_tenant_id: str | None = None,
        platform_role: str | None = None,
    ) -> None:
        """Soft-delete. The row stays so historical references (bookings,
        audits) remain resolvable; the serial becomes reusable via the
        partial unique index."""
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=target_tenant_id,
            obj=self.OBJECT, act="delete", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        device = await self._get_live_device(device_id, effective_tenant)
        device.is_deleted = True
        device.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()

    # ---------------------------------------------------------- bind (slice 04)

    async def bind(
        self,
        device_id: str,
        tenant_id: str,
        customer_id: str,
        actor_id: str,
        *,
        target_tenant_id: str | None = None,
        platform_role: str | None = None,
    ) -> tuple[Device, bool]:
        """Assign ``customer_id`` to a device. Returns ``(device, already_bound)``.

        - ``already_bound=True``: the device was already bound to this exact
          customer → **idempotent no-op, no DB write** (POST-to-sub-resource
          is an assignment; re-assigning the same value is a 200, not a 201).
        - ``already_bound=False``: a new binding was written (first bind, or
          an overwrite of a previously different customer — overwrite is legal
          because the assignment semantics are "set", like PUT).

        Guard: ``require("devices", "update")`` (NOT ``require_super_admin``).
        devices is a tenant-level resource (``tenant_id`` FK); binding a
        customer is a within-store business action. group attach/detach uses
        ``require_super_admin`` only because group is platform-level (no
        ``tenant_id``) — do not conflate the two.

        Platform writers (super_admin / hq_staff) skip the casbin require and
        operate on ``target_tenant_id``; store roles are anti-forgery guarded
        against carrying it (see ``resolve_target_tenant``).
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=target_tenant_id,
            obj=self.OBJECT, act="update", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        await self._assert_customer_in_tenant(effective_tenant, customer_id)
        device = await self._get_live_device(device_id, effective_tenant)
        if device.customer_id == customer_id:
            return device, True
        device.customer_id = customer_id
        await self.db.flush()
        await self.db.commit()
        return device, False

    async def unbind(
        self,
        device_id: str,
        tenant_id: str,
        actor_id: str,
        *,
        target_tenant_id: str | None = None,
        platform_role: str | None = None,
    ) -> None:
        """Clear a device's ``customer_id``. Idempotent: a device with no
        binding is a no-op, NOT an error (DELETE is idempotent by REST
        convention — saves the client a GET-then-DELETE round-trip).

        Platform writers pass ``target_tenant_id`` (the store whose device to
        unbind); store roles omit it (anti-forgery).
        """
        access = await self.principal.for_write(
            actor_id=actor_id, user_tenant_id=tenant_id,
            payload_tenant_id=target_tenant_id,
            obj=self.OBJECT, act="update", platform_role=platform_role,
        )
        if access.require:
            await permission_service.require(
                actor_id, access.effective_tenant,
                access.require.obj, access.require.act,
                platform_role=platform_role,
            )
        effective_tenant = access.effective_tenant
        device = await self._get_live_device(device_id, effective_tenant)
        if device.customer_id is None:
            return
        device.customer_id = None
        await self.db.flush()
        await self.db.commit()
