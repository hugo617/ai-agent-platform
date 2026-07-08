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
from app.models.tenant import Tenant, User, UserTenant  # noqa: E402
from app.services.permission_service import permission_service  # noqa: E402

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
        if user is None:
            user = User(
                id=uuid.uuid4().hex,
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password=hash_password(ADMIN_PASSWORD),
                status="active",
            )
            db.add(user)
            await db.flush()
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

        # 3. Link as owner (idempotent).
        membership = (
            await db.execute(
                select(UserTenant).where(
                    UserTenant.user_id == user.id,
                    UserTenant.tenant_id == tenant.id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            db.add(UserTenant(user_id=user.id, tenant_id=tenant.id, role="owner"))
            await db.flush()
            print(f"linked {user.username} as owner of {tenant.name}")
        else:
            membership.role = "owner"
            await db.flush()
            print("membership exists (role=owner)")

        # 4. Seed casbin policies for the tenant (idempotent).
        await permission_service.seed_tenant_defaults(tenant.id, user.id)

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
