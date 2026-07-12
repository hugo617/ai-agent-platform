#!/usr/bin/env python
"""Seed a rich demo dataset for the 大健康连锁 (wellness/TCM/physio chain) scenario.

Usage:
    python scripts/seed_demo.py

Creates (idempotent — safe to re-run):
  - 3 stores (tenants): 朝阳理疗中心 / 海淀中医门诊 / 王府井理疗馆
  - 6 store staff + 1 hq_staff (all password Demo@123456)
  - 2 groups (business orgs): 颐和堂中医馆 / 独立养生馆
  - 5 customer profiles across 3 stores (2 customers are cross-store)
  - 4 agents (3 store-level + 1 platform-level)

Demo-only. ⚠️ All passwords are weak (Demo@123456) — never use in production.

This script mirrors scripts/init_admin.py's pattern: async + AsyncSessionLocal +
idempotent select-then-add + calls real Service/Repository layers so casbin/SCD2
side-effects fire correctly. Run AFTER init_admin.py (super_admin must exist).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

# Ensure the project root is on sys.path when run as `python scripts/seed_demo.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.password import hash_password  # noqa: E402
from app.models.customer import CustomerProfile  # noqa: E402
from app.models.tenant import Tenant, User  # noqa: E402
from app.repositories.tenant import UserTenantRepository  # noqa: E402
from app.schemas.agent import AgentCreate  # noqa: E402
from app.schemas.customer import CustomerProfileCreate  # noqa: E402
from app.schemas.group import GroupCreate  # noqa: E402
from app.services.agent_service import AgentService  # noqa: E402
from app.services.customer_service import CustomerService  # noqa: E402
from app.services.group_service import GroupService  # noqa: E402
from app.services.permission_service import permission_service  # noqa: E402
from app.services.rbac_service import RbacService  # noqa: E402

# ----------------------------------------------------------------------- config
# ⚠️ DEMO-ONLY WEAK PASSWORD. Never reuse in production.
DEMO_PASSWORD = "Demo@123456"

# (store_name, [(username, display_name, role), ...])
STORES: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "朝阳理疗中心",
        [
            ("chen_guanzhang", "陈馆长", "owner"),
            ("li_shifu", "李师傅", "member"),
            ("wang_shifu", "王师傅", "member"),
        ],
    ),
    (
        "海淀中医门诊",
        [
            ("zhao_guanzhang", "赵馆长", "owner"),
            ("sun_shifu", "孙师傅", "member"),
        ],
    ),
    (
        "王府井理疗馆",
        [
            ("wu_guanzhang", "吴馆长", "owner"),
        ],
    ),
]

# hq_staff: cross-tenant read-only HQ business staff.
HQ_STAFF = ("hq_dudao", "总部督导员")

# Groups (platform-level business orgs): (name, code, [store_names to attach]).
GROUPS: list[tuple[str, str, list[str]]] = [
    ("颐和堂中医馆", "yihe_tcm", ["朝阳理疗中心", "海淀中医门诊"]),
    ("独立养生馆", "duli_wellness", ["王府井理疗馆"]),
]

# Customer profiles: (store_name, identity_key=phone, name, gender, remark).
# Cross-store reuse: 张先生 (138...) in 朝阳+海淀; 刘女士 (139...) in 朝阳+王府井.
CUSTOMERS: list[tuple[str, str, str, str, str]] = [
    ("朝阳理疗中心", "13800000001", "张先生", "男", "颈椎理疗老客户,偏好下午时段"),
    ("朝阳理疗中心", "13900000002", "刘女士", "女", "艾灸调理,对烟味敏感"),
    ("海淀中医门诊", "13800000001", "张先生", "男", "同朝阳店客户,转诊做针灸"),
    ("海淀中医门诊", "13700000003", "周先生", "男", "推拿新客,腰部劳损"),
    ("王府井理疗馆", "13900000002", "刘女士", "女", "同朝阳店客户,周末来调理"),
]

# Agents: (store_name or "PLATFORM", name, system_prompt, model).
AGENTS: list[tuple[str, str, str, str]] = [
    (
        "朝阳理疗中心",
        "朝阳店健康顾问",
        "你是朝阳理疗中心的健康顾问助手。擅长颈椎理疗、推拿按摩咨询,语气亲切专业。",
        "deepseek-chat",
    ),
    (
        "海淀中医门诊",
        "海淀店健康顾问",
        "你是海淀中医门诊的健康顾问助手。擅长针灸、中药调理咨询,注意中医辨证。",
        "deepseek-chat",
    ),
    (
        "王府井理疗馆",
        "王府井店健康顾问",
        "你是王府井理疗馆的健康顾问助手。擅长艾灸、养生保健咨询。",
        "deepseek-chat",
    ),
    (
        "PLATFORM",
        "颐和堂总部督导",
        "你是颐和堂大健康连锁的总部督导助手。可汇总各门店经营概况、客户分布,辅助总部决策。",
        "deepseek-chat",
    ),
]


# --------------------------------------------------------------------- helpers
async def _get_or_create_tenant(db, name: str) -> tuple[Tenant, bool]:
    """Return (tenant, created). Idempotent by name."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.name == name))
    ).scalar_one_or_none()
    if tenant is not None:
        return tenant, False
    tenant = Tenant(id=uuid.uuid4().hex, name=name, status="active")
    db.add(tenant)
    await db.flush()
    return tenant, True


async def _get_or_create_user(
    db, username: str, display_name: str, platform_role: str | None = None
) -> tuple[User, bool]:
    """Return (user, created). Idempotent by username. Resets password to DEMO."""
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is not None:
        # Keep demo password in sync on re-runs.
        user.password = hash_password(DEMO_PASSWORD)
        if platform_role and user.platform_role != platform_role:
            user.platform_role = platform_role
        await db.flush()
        return user, False
    user = User(
        id=uuid.uuid4().hex,
        username=username,
        email=f"{username}@demo.local",
        display_name=display_name,
        password=hash_password(DEMO_PASSWORD),
        status="active",
        platform_role=platform_role,
    )
    db.add(user)
    await db.flush()
    return user, True


async def _ensure_membership(
    db, user_id: str, tenant_id: str, role: str
) -> str:
    """Idempotent SCD2 role assignment. Returns 'created' | 'exists' | 'changed'."""
    memberships = UserTenantRepository(db)
    before = await memberships.current_role(user_id, tenant_id)
    if before is not None and before.role == role:
        return "exists"
    await memberships.assign_role(user_id, tenant_id, role)
    return "created" if before is None else "changed"


async def _seed_tenant_rbac(db, tenant: Tenant, owner: User) -> None:
    """Seed display roles + casbin policies + permission SCD2 for a tenant."""
    await RbacService(db).seed_defaults(tenant.id)
    await permission_service.seed_tenant_defaults(tenant.id, owner.id, db=db)


# ------------------------------------------------------------------------ main
async def main() -> int:
    async with AsyncSessionLocal() as db:
        # ---- 0. super_admin must already exist (init_admin.py creates it).
        super_admin = (
            await db.execute(
                select(User).where(User.platform_role == "super_admin")
            )
        ).scalar_one_or_none()
        if super_admin is None:
            print(
                "❌ No super_admin found. Run `python scripts/init_admin.py` first."
            )
            return 1
        print(f"super_admin present: {super_admin.username} ({super_admin.id})")

        # ---- 1. Stores (tenants) + staff + RBAC.
        tenant_by_name: dict[str, Tenant] = {}
        owner_by_store: dict[str, User] = {}
        for store_name, staff in STORES:
            tenant, t_created = await _get_or_create_tenant(db, store_name)
            tenant_by_name[store_name] = tenant
            print(
                f"{'created' if t_created else 'exists '} store: {store_name} ({tenant.id})"
            )

            # Find or create the owner first so RBAC seed has an actor.
            owner_username, owner_display, _ = staff[0]  # first entry is owner
            owner, _ = await _get_or_create_user(db, owner_username, owner_display)
            owner_by_store[store_name] = owner

            # Seed RBAC for this tenant before any permission-gated Service call.
            await _seed_tenant_rbac(db, tenant, owner)

            # Bind all staff (owner + members) via SCD2.
            for username, display_name, role in staff:
                user, u_created = await _get_or_create_user(
                    db, username, display_name
                )
                if u_created:
                    print(f"  created staff: {username} ({display_name})")
                status = await _ensure_membership(db, user.id, tenant.id, role)
                if status != "exists":
                    print(f"  ~ {username} → {role} ({status})")

            await db.flush()

        # ---- 2. hq_staff (platform-level, cross-tenant read-only).
        hq_username, hq_display = HQ_STAFF
        hq_user, hq_created = await _get_or_create_user(
            db, hq_username, hq_display, platform_role="hq_staff"
        )
        print(
            f"{'created' if hq_created else 'exists '} hq_staff: {hq_username} ({hq_display})"
        )

        await db.flush()

        # ---- 3. Groups (platform-level business orgs).
        group_svc = GroupService(db)
        for gname, gcode, store_names in GROUPS:
            # Idempotent: find by code first.
            from app.models.group import Group  # local import to avoid cycle

            existing = (
                await db.execute(select(Group).where(Group.code == gcode))
            ).scalar_one_or_none()
            if existing is not None:
                print(f"exists  group: {gname} ({existing.id})")
            else:
                tenant_ids = [tenant_by_name[s].id for s in store_names]
                await group_svc.create(
                    GroupCreate(
                        name=gname,
                        code=gcode,
                        description=f"演示组织:{gname}",
                        tenant_ids=tenant_ids,
                    )
                )
                print(f"created group: {gname}")

        # ---- 4. Customer profiles (cross-store identity reuse).
        cust_svc = CustomerService(db)
        for store_name, identity_key, cname, cgender, cremark in CUSTOMERS:
            tenant = tenant_by_name[store_name]
            owner = owner_by_store[store_name]
            # Duplicate check: skip if a live profile already exists for this
            # (customer, tenant) — re-runs should not raise BizError.
            from app.models.customer import Customer  # local import

            cust = (
                await db.execute(
                    select(Customer).where(Customer.identity_key == identity_key)
                )
            ).scalar_one_or_none()
            if cust is not None:
                existing_profile = (
                    await db.execute(
                        select(CustomerProfile).where(
                            CustomerProfile.customer_id == cust.id,
                            CustomerProfile.tenant_id == tenant.id,
                            CustomerProfile.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existing_profile is not None:
                    print(f"exists  profile: {cname} @ {store_name}")
                    continue
            await cust_svc.create_profile(
                owner.id,
                tenant.id,
                CustomerProfileCreate(
                    identity_key=identity_key,
                    name=cname,
                    gender=cgender,
                    remark=cremark,
                ),
                platform_role=None,  # owner acts in-store; casbin has the policy
            )
            cross = " (跨店复用)" if cust is not None else ""
            print(f"created profile: {cname} @ {store_name}{cross}")

        # ---- 5. Agents (3 store-level + 1 platform-level).
        agent_svc = AgentService(db)
        for scope, aname, aprompt, amodel in AGENTS:
            # Idempotent: skip if an agent with this name already exists in scope.
            from app.models.agent import Agent  # local import

            if scope == "PLATFORM":
                # Platform-level agent: attach to the first tenant (owner =
                # super_admin bypasses per-tenant permission via platform_role).
                tenant = tenant_by_name[STORES[0][0]]
                actor = super_admin
                existing = (
                    await db.execute(
                        select(Agent).where(
                            Agent.name == aname,
                            Agent.tenant_id == tenant.id,
                        )
                    )
                ).scalar_one_or_none()
            else:
                tenant = tenant_by_name[scope]
                actor = owner_by_store[scope]
                existing = (
                    await db.execute(
                        select(Agent).where(
                            Agent.name == aname,
                            Agent.tenant_id == tenant.id,
                        )
                    )
                ).scalar_one_or_none()
            if existing is not None:
                print(f"exists  agent: {aname} @ {scope}")
                continue
            await agent_svc.create(
                actor.id,
                tenant.id,
                AgentCreate(
                    name=aname,
                    system_prompt=aprompt,
                    model=amodel,
                    description=f"演示智能体:{aname}",
                ),
                platform_role=actor.platform_role,
            )
            print(f"created agent: {aname} @ {scope}")

        await db.commit()

    # ---- Summary.
    print("\n✅ demo seed complete.")
    print(f"   password (all demo accounts): {DEMO_PASSWORD}  ⚠️ demo-only")
    print("   accounts:")
    print("     super_admin : admin            (from init_admin.py)")
    print("     hq_staff    : hq_dudao")
    for store_name, staff in STORES:
        for username, display_name, role in staff:
            print(f"     {role:<7}    : {username:<16} ({display_name} @ {store_name})")
    print("   cross-store customers: 张先生(138) 朝阳+海淀, 刘女士(139) 朝阳+王府井")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
