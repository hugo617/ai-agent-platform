#!/usr/bin/env python
"""Create the first local super-admin so you can log in without Logto.

Usage:
    python scripts/init_admin.py

Reads ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD from the environment
(defaults: admin / admin@example.com / Admin@123456) and:
  1. creates a tenant "Platform" (if missing),
  2. creates the local user with a bcrypt password (if missing),
  3. links them as the tenant ``owner`` (mirrored into casbin),
  4. commits.

Idempotent — safe to re-run. Mirrors health_admin's ``pnpm init:admin``.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

# Ensure the project root is on sys.path when run as `python scripts/init_admin.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.password import hash_password  # noqa: E402
from app.models.tenant import Tenant, User  # noqa: E402
from app.repositories.tenant import UserTenantRepository  # noqa: E402
from app.services.permission_service import permission_service  # noqa: E402
from app.services.rbac_service import RbacService  # noqa: E402

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123456")
TENANT_NAME = os.environ.get("ADMIN_TENANT_NAME", "Platform")


async def main() -> int:
    async with AsyncSessionLocal() as db:
        # 1. Tenant (idempotent).
        stmt = select(Tenant).where(Tenant.name == TENANT_NAME)
        tenant = (await db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(id=uuid.uuid4().hex, name=TENANT_NAME)
            db.add(tenant)
            await db.flush()
            print(f"created tenant: {tenant.name} ({tenant.id})")
        else:
            print(f"tenant exists: {tenant.name} ({tenant.id})")

        # 2. User (idempotent by username).
        user = (
            await db.execute(select(User).where(User.username == ADMIN_USERNAME))
        ).scalar_one_or_none()
        is_new = False
        if user is None:
            user = User(
                id=uuid.uuid4().hex,
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password=hash_password(ADMIN_PASSWORD),
                status="active",
                platform_role="super_admin",
            )
            db.add(user)
            await db.flush()
            is_new = True
            print(f"created admin user: {user.username} ({user.id})")
        else:
            # Re-hash the password if the env override changed.
            from app.core.password import verify_password

            if not verify_password(ADMIN_PASSWORD, user.password):
                user.password = hash_password(ADMIN_PASSWORD)
                await db.flush()
                print(f"reset password for existing admin: {user.username}")
            else:
                print(f"admin user exists: {user.username} ({user.id})")

        # Ensure the admin has platform_role="super_admin" (idempotent).
        if user.platform_role != "super_admin":
            user.platform_role = "super_admin"
            await db.flush()
            if not is_new:
                print(f"upgraded {user.username} to super_admin")

        # 3. Seed the owner/admin/member display roles FIRST so the
        #    role_permissions SCD2 seed can resolve the role ids (idempotent).
        await RbacService(db).seed_defaults(tenant.id)

        # 4. Link as owner via the SCD2 write path (idempotent): assign_role
        #    reuses the current row if it already carries "owner", otherwise
        #    closes the old row and opens a new one — history preserved.
        memberships = UserTenantRepository(db)
        before = await memberships.current_role(user.id, tenant.id)
        await memberships.assign_role(user.id, tenant.id, "owner")
        print("linked owner" if before is None else "membership exists (role=owner)")

        # 5. Seed casbin policies + permissions + role_permissions SCD2 rows for
        #    the tenant (idempotent). Pass ``db`` so the SCD2 tables are seeded
        #    in lockstep with casbin.
        await permission_service.seed_tenant_defaults(tenant.id, user.id, db=db)

        await db.commit()

    # Don't echo the full password — it ends up in shell/CI logs. Show only a
    # length hint; the operator knows the value (they set ADMIN_PASSWORD).
    print("\n✅ admin ready.")
    print(f"   username : {ADMIN_USERNAME}")
    print(f"   password : {'*' * len(ADMIN_PASSWORD)} ({len(ADMIN_PASSWORD)} chars)")
    print("   login at : POST /api/v1/auth/login  {username, password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
