"""Principal: the unified identity module for read/write access resolution.

This is the deep module that absorbs the role + tenant + scope reasoning that
was previously scattered across ``booking_service`` / ``device_service`` /
``customer_service`` as 31 helper calls (``resolve_target_tenant`` +
``is_platform_writer`` + ``is_cross_tenant_viewer`` + ``DataScopeService``).
See ``plan-principal-module.md`` for the full design rationale.

Two methods cover the full surface:

- :meth:`Principal.for_write` — resolve the *effective tenant* for a write and
  whether the platform-writer bypass is in effect (``require=None`` ⇔ bypass;
  service must skip the casbin ``require`` in that case).
- :meth:`Principal.for_read` — resolve the *scope* (panorama vs tenant-scoped)
  and the effective tenant (``None`` for panorama) for a read, again with the
  ``require=None`` bypass signal.

**Service layer should use ``Principal.for_*``.** The four internal helpers
(``resolve_target_tenant`` / ``is_platform_writer`` / ``is_cross_tenant_viewer``
/ ``DataScopeService``) are retained as Principal's own implementation details
plus for the **explicitly out-of-scope callers** pinned by **ADR-0001**
(``docs/adr/0001-principal-scope-boundary.md``) — these intentionally bypass
Principal; **do NOT extend Principal to them without superseding that ADR**.
The full scope decision (non-migrating methods + non-adopting services) lives
in ``harness/docs/plan-principal-module.md`` §4.2.

Invariant: ``WriteAccess.require is None ⇔ is_platform_writer(platform_role)``
and ``ReadAccess.require is None ⇔ is_cross_tenant_viewer(platform_role)``.
Services MUST check ``if access.require:`` before calling casbin ``require`` —
skipping that check on a ``None`` require is a behaviour change.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services._tenant_target import resolve_target_tenant
from app.services.data_scope import DataScopeService, ResolvedScope
from app.services.permission_service import is_cross_tenant_viewer, is_platform_writer


@dataclass(frozen=True)
class RequireCall:
    """The (obj, act) pair a service must pass to ``permission_service.require``.

    ``None`` instances (on :class:`WriteAccess` / :class:`ReadAccess`) signal
    that the platform-writer / panorama bypass is in effect and the service
    MUST skip the casbin ``require`` call entirely.
    """

    obj: str
    act: str


@dataclass(frozen=True)
class WriteAccess:
    """Result of :meth:`Principal.for_write`.

    ``effective_tenant`` is the tenant the write targets (resolves to
    ``payload.tenant_id`` for platform writers, ``user_tenant_id`` for store
    roles). ``require`` is ``None`` when the platform-writer bypass applies
    (the service must skip ``permission_service.require``); otherwise it is the
    (obj, act) pair the service must require.
    """

    effective_tenant: str
    require: RequireCall | None


@dataclass(frozen=True)
class ReadAccess:
    """Result of :meth:`Principal.for_read`.

    ``is_panorama`` is ``True`` when the caller is a cross-tenant viewer
    (super_admin / hq_staff) and should read the panorama view (no tenant
    filter, no casbin require). In that case ``effective_tenant`` is ``None``
    and ``require`` is ``None``. For store roles ``is_panorama`` is ``False``,
    ``effective_tenant`` is the caller's tenant, ``scope`` is the
    :class:`ResolvedScope` from :class:`DataScopeService`, and ``require`` is
    the (obj, ``"read"``) pair the service must require.
    """

    effective_tenant: str | None
    scope: ResolvedScope
    require: RequireCall | None
    is_panorama: bool


class Principal:
    """Resolve the current request's read/write access in one place.

    Holds the db session (same object as the service's ``self.db`` — no
    duplicate lifecycle). The four helpers it composes are kept as private
    import-level dependencies; services consume only the two ``for_*`` methods.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def for_write(
        self,
        *,
        actor_id: str,
        user_tenant_id: str | None,
        payload_tenant_id: str | None,
        obj: str,
        act: str,
        platform_role: str | None = None,
    ) -> WriteAccess:
        """Resolve the effective tenant + require-or-skip for a write action.

        Decision table (zero-behaviour-change with ``resolve_target_tenant``):

        - Platform writer (super_admin / hq_staff) + ``payload_tenant_id``
          → effective=payload, require=None (bypass).
        - Platform writer missing ``payload_tenant_id`` → BizError 400
          ("平台角色跨店写必须指定目标门店(tenant_id)").
        - Store role without ``payload_tenant_id`` → effective=user, require=(obj, act).
        - Store role carrying ``payload_tenant_id`` → BizError 400
          ("门店角色不可指定目标租户(tenant_id)").

        ``actor_id`` is accepted for symmetry with :meth:`for_read` (and so the
        service signature is uniform across the two methods) but is not used
        here: write-path tenant resolution does not branch on the actor id.
        """
        # Delegates the tenant resolution + the two 400 BizError guards to the
        # existing helper, so the error messages stay byte-identical with the
        # pre-Principal behaviour (不可违反契约 §2 in plan-principal-module.md).
        effective_tenant = resolve_target_tenant(
            user_tenant_id=user_tenant_id,
            payload_tenant_id=payload_tenant_id,
            platform_role=platform_role,
        )
        # The require=None ⇔ platform-writer-bypass invariant (docstring 钉死,
        # plan §4.0 Q3'). Store roles get a RequireCall so the service runs
        # the normal casbin require.
        require: RequireCall | None = (
            None
            if is_platform_writer(platform_role)
            else RequireCall(obj=obj, act=act)
        )
        return WriteAccess(effective_tenant=effective_tenant, require=require)

    async def for_read(
        self,
        *,
        actor_id: str,
        user_tenant_id: str | None,
        obj: str,
        act: str,
        platform_role: str | None = None,
    ) -> ReadAccess:
        """Resolve the scope + effective tenant + require-or-skip for a read.

        Decision table (mirrors the ``if is_cross_tenant_viewer: panorama else:
        require + scope`` pattern currently inlined in each service method):

        - Cross-tenant viewer (super_admin / hq_staff) → is_panorama=True,
          effective_tenant=None, scope=ResolvedScope("all"), require=None.
          The service should read the panorama view (no tenant filter, no
          casbin require).
        - Store role → is_panorama=False, effective_tenant=user_tenant_id,
          scope=DataScopeService.resolve(...), require=RequireCall(obj, act).

        The panorama branch short-circuits before touching ``DataScopeService``
        so a viewer read needs no db round-trip — matching the current
        ``permission_service.check`` bypass for super_admin / hq_staff.

        ``act`` is required (no default): the §4.1 table pins it to ``"read"``
        for the booking/device/customer read paths today, but Principal stays
        generic — services pass the act that matches their casbin policy.
        """
        if is_cross_tenant_viewer(platform_role):
            return ReadAccess(
                effective_tenant=None,
                scope=ResolvedScope(scope="all"),
                require=None,
                is_panorama=True,
            )

        # Store role: scope is resolved by the existing DataScopeService
        # (call signature unchanged — see plan §4.4 contract §4). A missing
        # user_tenant_id on a store principal is a misconfigured-token case;
        # DataScopeService.resolve surfaces it on its own (no extra guard here
        # — adding one would be an un-specced third branch per §4.1's 2-row
        # table).
        scope = await DataScopeService(self.db).resolve(
            user_id=actor_id,
            tenant_id=user_tenant_id,
            platform_role=platform_role,
        )
        return ReadAccess(
            effective_tenant=user_tenant_id,
            scope=scope,
            require=RequireCall(obj=obj, act=act),
            is_panorama=False,
        )
