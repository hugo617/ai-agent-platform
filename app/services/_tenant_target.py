"""Shared helper for resolving the target tenant of a devices/bookings write.

Platform writer roles (super_admin / hq_staff) cross-tenant WRITE on devices +
bookings. They have no ``user.tenant_id`` to scope to, so the write action's
*target* tenant must come from the request body (``payload.tenant_id``). Store
roles (owner / admin / member / customer) always write to their own tenant; the
target is ``user.tenant_id``, and carrying ``payload.tenant_id`` would be a
cross-tenant forgery attempt.

This helper centralises the resolution + the two BizError guards (platform
writer missing tenant_id → 400, store role carrying tenant_id → 400 anti-
forgery) so devices and bookings services cannot drift on the rule. See
``plan-platform-cross-tenant-write.md`` §4.5.2 for the design rationale.
"""

from app.services.errors import BizError
from app.services.permission_service import is_platform_writer


def resolve_target_tenant(
    user_tenant_id: str | None,
    payload_tenant_id: str | None,
    platform_role: str | None,
) -> str:
    """Resolve the tenant a devices/bookings write action targets.

    - Platform writers: MUST carry ``payload.tenant_id`` (the target store);
      missing → 400. ``user_tenant_id`` is ignored (platform principals have no
      store-side tenant).
    - Store roles: MUST NOT carry ``payload.tenant_id`` (anti-forgery); present
      → 400. Effective tenant is always ``user_tenant_id``.

    The ``user_tenant_id`` missing-store-tenant case is defensive — store
    principals always have a tenant, this only fires on misconfigured tokens.

    Internal: called by Principal (``app.services.principal.Principal.for_write``
    delegates tenant resolution + the two BizError guards here so the error
    messages stay byte-identical with the pre-Principal behaviour). The
    out-of-scope callers (booking read variants ``get_tenant_schedule`` +
    ``list_my_bookings`` + non-adopting services) are intentionally retained
    and pinned by **ADR-0001**
    (``docs/adr/0001-principal-scope-boundary.md``); **do NOT extend Principal
    without superseding that ADR**.
    """
    if is_platform_writer(platform_role):
        if not payload_tenant_id:
            raise BizError("平台角色跨店写必须指定目标门店(tenant_id)")
        return payload_tenant_id
    # store role
    if payload_tenant_id is not None:
        raise BizError("门店角色不可指定目标租户(tenant_id)")
    if not user_tenant_id:
        raise BizError("缺少门店归属,无法执行写操作")
    return user_tenant_id
