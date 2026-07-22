#!/usr/bin/env python
"""One-shot backfill: grant ``devices`` / ``menu:devices`` permissions to every
existing tenant's system roles (devices-crud-ui slice 02).

What changed in slice 02 (why this script exists):
  * ``devices`` is a brand-new object. New tenants get the perm set via
    ``seed_tenant_defaults`` automatically, but every tenant created BEFORE
    slice 02 shipped is missing ``devices:create/read/update/delete`` (owner),
    the matching subset for admin/member, and the ``menu:devices`` nav entry.
  * Without this backfill, the devices feature is broken on day one for every
    existing store: even the owner gets 403 on ``GET /api/v1/devices``.

What the script does, per tenant, idempotently:
  1. Upserts ``devices:<act>`` permission catalogue rows (one per unit).
  2. Grants owner/admin/member the role-permission rows listed in
     ``DEFAULT_OWNER_PERMS`` / ``DEFAULT_ADMIN_PERMS`` / ``DEFAULT_MEMBER_PERMS``
     (devices-only subset).
  3. Upserts + grants ``menu:devices`` for each system role.
  4. Re-syncs casbin from the SCD2 current state per role.

Scope guardrail: ONLY ``devices`` and ``menu:devices`` are touched. Re-running
it never touches other perms (``customers:read`` etc.). Idempotent at three
layers (catalogue upsert / grant no-op / casbin rebuild).

Usage:
    python scripts/backfill_devices_perms.py
    python scripts/backfill_devices_perms.py --dry-run   # report only, no writes

Run AFTER deploying slice 02 code (no schema change — this is a data migration).
Safe to run multiple times: second run is a no-op (everything already granted).
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
    backfill_devices_perms_for_existing_tenants,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
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
            print(f"[dry-run] Would backfill devices perms across {len(tenants)} tenant(s):")
            for t in tenants:
                print(f"  - {t.id} ({t.name})")
            print(
                "\n[dry-run] No writes performed. Re-run without --dry-run to apply."
            )
            return

        stats = await backfill_devices_perms_for_existing_tenants(session)
        await session.commit()

        total = sum(stats.values())
        for t in tenants:
            print(f"  tenant {t.id} ({t.name}): +{stats.get(t.id, 0)} new grants")
        print(
            f"\nBackfill complete across {len(tenants)} tenant(s): "
            f"+{total} new role×permission grants."
        )


if __name__ == "__main__":
    asyncio.run(main())
