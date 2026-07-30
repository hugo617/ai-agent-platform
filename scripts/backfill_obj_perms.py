#!/usr/bin/env python
"""One-shot backfill: grant ``<obj>`` / ``menu:<obj>`` permissions to every
existing tenant's system roles (perm-backfill-dedupe — the merged, parameterized
backfill that replaced the former per-obj script mirrors).

Why this script exists:
  * ``devices`` and ``bookings`` are tenant-scoped business records that shipped
    AFTER the first tenants existed. New tenants get the perm set via
    ``seed_tenant_defaults`` automatically, but every tenant created BEFORE the
    obj shipped is missing ``<obj>:create/read/update/delete`` (owner), the
    matching subset for admin/member, and the ``menu:<obj>`` nav entry.
  * Without this backfill, the obj's feature is broken on day one for every
    existing store: even the owner gets 403 on the list endpoint.

What the script does, per tenant, idempotently (delegated to
``backfill_perm_set_for_existing_tenants``):
  1. Upserts ``<obj>:<act>`` permission catalogue rows (one per unit).
  2. Grants owner/admin/member the role-permission rows listed in
     ``DEFAULT_OWNER_PERMS`` / ``DEFAULT_ADMIN_PERMS`` / ``DEFAULT_MEMBER_PERMS``
     (``<obj>``-only subset).
  3. Upserts + grants ``menu:<obj>`` for each system role.
  4. Re-syncs casbin from the SCD2 current state per role.

Scope guardrail: ONLY ``<obj>`` and ``menu:<obj>`` are touched (the function's
internal ``if perm_obj != obj: continue`` / ``if code != obj: continue``). Plus
a whitelist ``BACKFILLABLE_OBJS`` rejects unknown objs (the argparse choices
here is the first gate; the function's ValueError is the second gate for
non-script callers). Re-running never touches other perms (``customers:read``
etc.). Idempotent at three layers (catalogue upsert / grant no-op / casbin
rebuild).

Usage:
    python scripts/backfill_obj_perms.py --obj devices
    python scripts/backfill_obj_perms.py --obj bookings
    python scripts/backfill_obj_perms.py --obj devices --dry-run  # report only

Run AFTER deploying the obj's code (no schema change — this is a data
migration). Safe to run multiple times: second run is a no-op.
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
from app.models.tenant import Tenant  # noqa: E402
from app.services.permission_service import (  # noqa: E402
    BACKFILLABLE_OBJS,
    backfill_perm_set_for_existing_tenants,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--obj",
        required=True,
        choices=sorted(BACKFILLABLE_OBJS),
        help="The object whose perm set to backfill (must be in BACKFILLABLE_OBJS).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        tenants = (await session.execute(select(Tenant))).scalars().all()
        if not tenants:
            print("No tenants found — nothing to backfill.")
            return

        if args.dry_run:
            # Dry-run: just report how many tenants would be scanned, no writes.
            print(
                f"[dry-run] Would backfill {args.obj} perms across "
                f"{len(tenants)} tenant(s):"
            )
            for t in tenants:
                print(f"  - {t.id} ({t.name})")
            print(
                "\n[dry-run] No writes performed. Re-run without --dry-run to apply."
            )
            return

        stats = await backfill_perm_set_for_existing_tenants(session, args.obj)
        await session.commit()

        total = sum(stats.values())
        for t in tenants:
            print(f"  tenant {t.id} ({t.name}): +{stats.get(t.id, 0)} new grants")
        print(
            f"\nBackfill complete across {len(tenants)} tenant(s): "
            f"+{total} new role×permission grants for {args.obj}."
        )


if __name__ == "__main__":
    asyncio.run(main())
