#!/usr/bin/env python
"""One-shot backfill: bring every tenant's permission catalogue + system-role
grants in line with the unified catalogue (permission-unified-model).

What changed in that task (why this script exists):
  * ``settings``/``api_tokens`` used to carry only a coarse ``manage`` action,
    now split into read/update (settings) and read/create/delete (api_tokens).
  * ``conversations:delete``/``conversations:update`` and ``export`` actions
    were added for agents/customers.
  * Permission.name is now a Chinese friendly label (e.g. ``"智能体-查看"``).

Existing tenants created before the change still carry the old ``manage`` grants
and English names. This script, run once after deploying the new code:

  1. Grants every missing ``(obj, act)`` from the new ``DEFAULT_*_PERMS`` to
     each system role (owner/admin/member) — via ``rbac_service.grant_permission``
     so SCD2 + casbin + audit all stay consistent.
  2. Revokes the legacy ``settings:manage`` / ``api_tokens:manage`` grants that
     no longer exist in the new catalogue (so the matrix drops the stale
     columns). A super_admin platform_role bypasses the require() guard.
  3. Rewrites every Permission row's ``name`` to the Chinese label sourced from
     ``OBJ_CN``/``ACT_CN`` (the single source of truth).

Idempotent: grant is a no-op on already-granted pairs, revoke is a no-op when
the pair was never granted, and the name rewrite converges. Safe to re-run.

Usage:
    python scripts/backfill_permissions.py
    python scripts/backfill_permissions.py --dry-run   # report only, no writes

Run AFTER ``alembic upgrade head`` (the schema is unchanged, but this is a data
migration). No DB schema change — the Permission table keeps its ``code``
encoding (``"<obj>:<act>"``).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Ensure the project root is on sys.path when run as `python scripts/...`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.rbac import Permission  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.repositories.rbac import RolePermissionRepository, RoleRepository  # noqa: E402
from app.schemas.rbac import RolePermissionGrant  # noqa: E402
from app.services.permission_service import (  # noqa: E402
    ACT_CN,
    DEFAULT_ADMIN_PERMS,
    DEFAULT_MEMBER_PERMS,
    DEFAULT_OWNER_PERMS,
    OBJ_CN,
)
from app.services.rbac_service import RbacService  # noqa: E402

# Role code → the new default perm list. System roles only — custom roles are
# left untouched (their grants stay as-is; admins can adjust them in the UI).
SYSTEM_ROLE_PERMS: dict[str, list[tuple[str, str]]] = {
    "owner": DEFAULT_OWNER_PERMS,
    "admin": DEFAULT_ADMIN_PERMS,
    "member": DEFAULT_MEMBER_PERMS,
}

# Legacy coarse actions that were split: any ``<obj>:manage`` grant still held
# by a system role is revoked so the matrix drops the stale column. The split
# replacements (read/update or read/create/delete) are granted above.
LEGACY_COARSE: dict[str, list[str]] = {
    "settings": ["manage"],
    "api_tokens": ["manage"],
}

# A stable identity for audit-log rows produced by grant/revoke. The platform
# super_admin bypasses every require(), so no real user row is needed.
BACKFILL_ACTOR = "system-backfill"
PLATFORM_ROLE = "super_admin"


async def _backfill_tenant(session, tenant_id: str, *, dry_run: bool) -> dict:
    """Backfill one tenant. Returns a small stats dict for the report."""
    stats = {"granted": 0, "revoked": 0, "renamed": 0}
    rbac = RbacService(session)
    role_repo = RoleRepository(session)
    rp_repo = RolePermissionRepository(session)

    for role_code, perms in SYSTEM_ROLE_PERMS.items():
        role = await role_repo.get_by_code(tenant_id, role_code)
        if role is None:
            # This tenant doesn't have this system role (e.g. member never
            # created) — nothing to backfill for it.
            continue

        # 1. Grant every missing (obj, act) from the new defaults.
        existing = await rp_repo.current_permissions(role.id, tenant_id)
        existing_codes: set[str] = set()
        for row in existing:
            perm = (
                await session.execute(
                    select(Permission.code).where(Permission.id == row.permission_id)
                )
            ).scalar_one_or_none()
            if perm:
                existing_codes.add(perm)

        for obj, act in perms:
            code = f"{obj}:{act}"
            if code in existing_codes:
                continue
            if dry_run:
                stats["granted"] += 1
            else:
                await rbac.grant_permission(
                    BACKFILL_ACTOR,
                    tenant_id,
                    role.id,
                    RolePermissionGrant(obj=obj, act=act),
                    platform_role=PLATFORM_ROLE,
                )
                stats["granted"] += 1

        # 2. Revoke legacy coarse ``manage`` grants no longer in the catalogue.
        # Re-read the current grants (step 1 may have just added rows) so the
        # legacy check reflects the post-grant state.
        existing = await rp_repo.current_permissions(role.id, tenant_id)
        existing_perm_ids = {r.permission_id for r in existing}
        for obj, acts in LEGACY_COARSE.items():
            for act in acts:
                code = f"{obj}:{act}"
                perm_id = (
                    await session.execute(
                        select(Permission.id).where(
                            Permission.tenant_id == tenant_id,
                            Permission.code == code,
                            Permission.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if perm_id is None or perm_id not in existing_perm_ids:
                    continue
                if dry_run:
                    stats["revoked"] += 1
                else:
                    await rbac.revoke_permission(
                        BACKFILL_ACTOR,
                        tenant_id,
                        role.id,
                        perm_id,
                        platform_role=PLATFORM_ROLE,
                    )
                    stats["revoked"] += 1

    # 3. Rewrite every Permission row's name to the Chinese label.
    rows = (
        await session.execute(
            select(Permission).where(
                Permission.tenant_id == tenant_id,
                Permission.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    for p in rows:
        if ":" in p.code:
            obj, act = p.code.split(":", 1)
        else:
            obj, act = p.code, ""
        new_name = f"{OBJ_CN.get(obj, obj)}-{ACT_CN.get(act, act)}"
        if p.name != new_name:
            if dry_run:
                stats["renamed"] += 1
            else:
                p.name = new_name
                stats["renamed"] += 1

    if not dry_run:
        await session.commit()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        tenants = (
            await session.execute(select(Tenant).where(Tenant.is_deleted.is_(False)))
        ).scalars().all()
        if not tenants:
            print("No tenants found — nothing to backfill.")
            return

        total = {"granted": 0, "revoked": 0, "renamed": 0}
        for t in tenants:
            stats = await _backfill_tenant(session, t.id, dry_run=args.dry_run)
            for k in total:
                total[k] += stats[k]
            print(
                f"  tenant {t.id} ({t.name}): "
                f"+{stats['granted']} granted, -{stats['revoked']} revoked, "
                f"{stats['renamed']} renamed"
            )

        prefix = "[dry-run] " if args.dry_run else ""
        print(
            f"\n{prefix}Backfill complete across {len(tenants)} tenant(s): "
            f"+{total['granted']} granted, -{total['revoked']} revoked, "
            f"{total['renamed']} permission names rewritten."
        )


if __name__ == "__main__":
    asyncio.run(main())
