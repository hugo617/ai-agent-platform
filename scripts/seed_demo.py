#!/usr/bin/env python
"""Seed a rich demo dataset for the 大健康连锁 (wellness/TCM/physio chain) scenario.

Usage:
    python scripts/seed_demo.py            # idempotent upsert (safe to re-run)
    python scripts/seed_demo.py --reset    # wipe demo data then full rebuild

Creates (all demo-only — ⚠️ weak password Demo@123456, never use in production):
  - 3 stores (tenants): 朝阳理疗中心 / 海淀中医门诊 / 王府井理疗馆
  - 7 store/hq staff (1 owner + members per store + 1 hq_staff) + super_admin (from init_admin)
  - 2 groups (business orgs): 颐和堂中医馆 / 独立养生馆
  - 5 customer profiles across 3 stores (2 customers are cross-store)
  - 4 agents (3 store-level + 1 platform-level) — each with distinct reasoning params
  - 1 custom role (资深理疗师) with differentiated permissions in 朝阳 store
  - conversations + messages (AI core artifacts, 4-6 segments, 20-30 messages)
  - LLM configs (1 platform-level + 1 tenant-level override → demo 3-tier fallback)
  - API tokens (2 store owners, demo AtoA)
  - audit logs (SystemLog rows naturally produced by Service calls)
  - extra login methods (phone login for 朝阳 owner, demo multi-login)

This script mirrors scripts/init_admin.py's pattern: async + AsyncSessionLocal +
idempotent select-then-add + calls real Service/Repository layers so casbin/SCD2
audit side-effects fire correctly. Run AFTER init_admin.py (super_admin must exist).

``--reset`` wipes ONLY demo-marked rows (by tenant name / username / group code /
customer identity / agent name / role code white-lists), never touches super_admin
or non-demo data. Cascade follows FK reverse order.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

# Ensure the project root is on sys.path when run as `python scripts/seed_demo.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.password import hash_password  # noqa: E402
from app.models.agent import Agent, Conversation  # noqa: E402
from app.models.api_token import ApiToken  # noqa: E402
from app.models.customer import Customer, CustomerProfile  # noqa: E402
from app.models.group import Group, GroupTenant  # noqa: E402
from app.models.llm_config import LlmConfig  # noqa: E402
from app.models.log import SystemLog  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.models.rbac import Role, RolePermission  # noqa: E402
from app.models.security import UserLoginMethod  # noqa: E402
from app.models.tenant import Tenant, User, UserTenant  # noqa: E402
from app.repositories.tenant import UserTenantRepository  # noqa: E402
from app.schemas.agent import AgentCreate  # noqa: E402
from app.schemas.api_token import ApiTokenCreate  # noqa: E402
from app.schemas.customer import CustomerProfileCreate  # noqa: E402
from app.schemas.group import GroupCreate  # noqa: E402
from app.schemas.llm_config import LlmConfigUpdate  # noqa: E402
from app.schemas.rbac import RoleCreate, RolePermissionGrant  # noqa: E402
from app.services.agent_service import AgentService  # noqa: E402
from app.services.api_token_service import api_token_service  # noqa: E402
from app.services.conversation_service import ConversationService  # noqa: E402
from app.services.customer_service import CustomerService  # noqa: E402
from app.services.group_service import GroupService  # noqa: E402
from app.services.llm_config_service import llm_config_service  # noqa: E402
from app.services.permission_service import permission_service  # noqa: E402
from app.services.rbac_service import RbacService  # noqa: E402

# ----------------------------------------------------------------------- config
# ⚠️ DEMO-ONLY WEAK PASSWORD. Never reuse in production.
DEMO_PASSWORD = "Demo@123456"

# Store definitions: (store_name, [(username, display_name, role), ...]).
# First entry per store is the owner.
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

# Agents with distinct reasoning params:
# (store_name or "PLATFORM", name, system_prompt, model,
#  temperature, max_tokens|None, top_p|None).
# Different temperatures demo "different agents have different reasoning styles".
AGENTS: list[tuple[str, str, str, str, float, int | None, float | None]] = [
    (
        "朝阳理疗中心",
        "朝阳店健康顾问",
        "你是朝阳理疗中心的健康顾问助手。擅长颈椎理疗、推拿按摩咨询,语气亲切专业。",
        "deepseek-chat",
        0.3, 2048, 0.9,  # 严谨
    ),
    (
        "海淀中医门诊",
        "海淀店健康顾问",
        "你是海淀中医门诊的健康顾问助手。擅长针灸、中药调理咨询,注意中医辨证。",
        "deepseek-chat",
        0.7, None, None,  # 默认
    ),
    (
        "王府井理疗馆",
        "王府井店健康顾问",
        "你是王府井理疗馆的健康顾问助手。擅长艾灸、养生保健咨询。",
        "deepseek-chat",
        0.9, 4096, 0.95,  # 发散
    ),
    (
        "PLATFORM",
        "颐和堂总部督导",
        "你是颐和堂大健康连锁的总部督导助手。可汇总各门店经营概况、客户分布,辅助总部决策。",
        "deepseek-chat",
        0.2, 8192, 0.85,  # 保守汇总
    ),
]

# Custom role in 朝阳 store: (tenant_name, role_name, role_code,
#   [(obj, act), ...] permissions to grant, member_username_to_rebind).
# 李师傅 gets rebound from member → senior_therapist to demo "custom role works".
# Permissions: 客户读写 + 对话(资深理疗师要能和顾问对话咨询),不能删客户/建客户。
CUSTOM_ROLE: tuple[str, str, str, list[tuple[str, str]], str] = (
    "朝阳理疗中心",
    "资深理疗师",
    "senior_therapist",
    [
        ("customers", "read"),
        ("customers", "update"),
        ("conversations", "read"),
        ("conversations", "create"),
        ("conversations", "chat"),
    ],
    "li_shifu",
)

# LLM configs: platform-level + one tenant-level override (朝阳 → deepseek-reasoner).
# api_key is a DEMO PLACEHOLDER — real key must be set in the settings page.
LLM_DEMO_API_KEY = "sk-demo-placeholder"
LLM_PLATFORM_MODELS = ["deepseek-chat", "deepseek-reasoner"]
LLM_TENANT_OVERRIDE_STORE = "朝阳理疗中心"
LLM_TENANT_OVERRIDE_MODEL = "deepseek-reasoner"

# API tokens: [(store_name, token_name), ...]. Owner of the store issues each.
API_TOKENS: list[tuple[str, str]] = [
    ("朝阳理疗中心", "朝阳店 AtoA 集成"),
    ("海淀中医门诊", "海淀店 AtoA 集成"),
]

# Extra login methods (phone): [(username, phone), ...].
# Demo "one user, multiple login methods" (email + phone).
EXTRA_LOGIN_METHODS: list[tuple[str, str]] = [
    ("chen_guanzhang", "13800001111"),
]

# Conversation scripts: (store_name or "PLATFORM", agent_name, actor_username,
#   [(role, content), ...]).
# Each segment is 4-6 user/assistant alternating turns. Content is 大健康-themed.
# assistant text is hard-coded (no real LLM call).
CONVERSATIONS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    (
        "朝阳理疗中心",
        "朝阳店健康顾问",
        "chen_guanzhang",
        [
            ("user", "你好,最近颈椎不舒服,有什么理疗建议?"),
            ("assistant", "您好!根据您的描述,建议先做颈椎推拿放松,配合艾灸温通经络。"
                          "请问您的不适持续多久了?是否有手臂发麻的情况?"),
            ("user", "大概两周了,偶尔有点手麻。"),
            ("assistant", "建议您预约颈椎推拿(45分钟)+ 艾灸(30分钟)的组合疗程,"
                          "一周两次。注意日常保持正确坐姿,避免长时间低头看手机。"),
            ("user", "好的,帮我约明天下午的。"),
            ("assistant", "已为您预约明天下午 14:00 的颈椎推拿 + 艾灸套餐,由王师傅为您服务。"
                          "到店请提前 10 分钟,祝您理疗顺利!"),
        ],
    ),
    (
        "朝阳理疗中心",
        "朝阳店健康顾问",
        "li_shifu",
        [
            ("user", "刘女士来店做艾灸,她对烟味敏感,怎么处理?"),
            ("assistant", "建议安排在通风良好的独立房间,使用无烟艾条或艾灸盒,"
                          "提前开启空气净化器。预约时备注「对烟味敏感」,优先安排 3 号理疗室。"),
            ("user", "明白了,谢谢顾问。"),
            ("assistant", "不客气!如有其他疑问随时咨询。"),
        ],
    ),
    (
        "海淀中医门诊",
        "海淀店健康顾问",
        "zhao_guanzhang",
        [
            ("user", "张先生转诊过来做针灸,请告知注意事项。"),
            ("assistant", "张先生在朝阳店做了颈椎理疗,转诊做针灸巩固。"
                          "建议针灸前避免空腹,治疗后注意保暖,勿立即洗澡。"
                          "首次针灸需评估体质,建议安排李医师接诊。"),
            ("user", "好,约了李医师下周二。"),
            ("assistant", "已记录。下周二 10:00 李医师针灸初诊,届时请带既往理疗记录。"),
        ],
    ),
    (
        "王府井理疗馆",
        "王府井店健康顾问",
        "wu_guanzhang",
        [
            ("user", "周末刘女士来做艾灸调理,需要准备什么?"),
            ("assistant", "刘女士偏好周末调理,建议准备无烟艾条(她对烟味敏感)。"
                          "可推荐养生保健套餐:艾灸 + 足浴,缓解疲劳效果好。"),
            ("user", "推荐好了,谢谢。"),
            ("assistant", "祝刘女士调理愉快!如需调整方案随时沟通。"),
        ],
    ),
    (
        "PLATFORM",
        "颐和堂总部督导",
        "admin",  # super_admin creates the platform-scoped summary conversation
        [
            ("user", "汇总一下各门店本周的经营概况。"),
            ("assistant", "本周经营概况:\n"
                          "• 朝阳理疗中心:颈椎推拿 + 艾灸为主,客户 2 名(张先生、刘女士),"
                          "到店理疗活跃度高。\n"
                          "• 海淀中医门诊:针灸 + 中药调理,张先生转诊过来巩固治疗。\n"
                          "• 王府井理疗馆:艾灸养生为主,刘女士周末调理。\n"
                          "跨店客户复用机制运转良好(张先生朝阳+海淀、刘女士朝阳+王府井)。"),
            ("user", "客户分布有什么特点?"),
            ("assistant", "客户画像偏中年(颈椎/腰肌劳损),女性客户偏好艾灸调理。"
                          "建议加强颈椎理疗与中医针灸的跨店协同,提升复购率。"),
        ],
    ),
]


# ----------------------------------------------------- demo whitelist (for --reset)
# Constants used by --reset to identify demo rows. Never use bare DELETE FROM.
DEMO_STORE_NAMES = [s[0] for s in STORES]
DEMO_USERNAMES = [u[0] for store in STORES for u in store[1]] + [HQ_STAFF[0]]
DEMO_GROUP_CODES = [g[1] for g in GROUPS]
DEMO_CUSTOMER_PHONES = sorted({c[1] for c in CUSTOMERS})
DEMO_AGENT_NAMES = [a[1] for a in AGENTS]
DEMO_CUSTOM_ROLE_CODES = [CUSTOM_ROLE[2]]
# Extra login method identifiers (phones).
DEMO_EXTRA_LOGIN_IDS = [p for _, p in EXTRA_LOGIN_METHODS]
# Demo API token names (for --reset cleanup).
DEMO_API_TOKEN_NAMES = [t[1] for t in API_TOKENS]


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
    """Idempotent SCD2 role assignment + casbin grouping sync.

    Writes both the SCD2 ``UserTenant`` row (history) and the casbin grouping
    policy (live enforcement). Returns 'created' | 'exists' | 'changed'.
    Without the casbin sync, members assigned here would have no ``g`` policy
    and fail ``require(...)`` on their first permission-gated Service call.
    """
    memberships = UserTenantRepository(db)
    before = await memberships.current_role(user_id, tenant_id)
    if before is not None and before.role == role:
        # SCD2 already current — still ensure casbin grouping is present
        # (reset wipes casbin but keeps SCD2 rows only if they predate the wipe;
        # a missing ``g`` row would silently break enforcement).
        await permission_service.add_role_for_user_in_domain(
            user_id, role, tenant_id
        )
        return "exists"
    await memberships.assign_role(user_id, tenant_id, role)
    await permission_service.set_role_for_user_in_domain(
        user_id, role, tenant_id
    )
    return "created" if before is None else "changed"


async def _seed_tenant_rbac(db, tenant: Tenant, owner: User) -> None:
    """Seed display roles + casbin policies + permission SCD2 for a tenant."""
    await RbacService(db).seed_defaults(tenant.id)
    await permission_service.seed_tenant_defaults(tenant.id, owner.id, db=db)


# ----------------------------------------------------------- --reset cleanup
async def _reset_demo_data(db) -> None:
    """Wipe all demo-marked rows in FK-reverse order. Never touches super_admin.

    Uses the demo white-list (tenant names / usernames / group codes / customer
    identity keys / agent names / role codes) to look up row IDs first, then
    deletes by those IDs. Never runs a bare ``DELETE FROM table``.
    """
    print("\n🧹 --reset: wiping demo data (white-list scoped, FK-reverse order)...")

    # ---- Look up demo row IDs first (everything keyed off these).
    demo_tenant_ids = [
        r for r in (
            await db.execute(
                select(Tenant.id).where(Tenant.name.in_(DEMO_STORE_NAMES))
            )
        ).scalars()
    ]
    demo_user_ids = [
        r for r in (
            await db.execute(
                select(User.id).where(User.username.in_(DEMO_USERNAMES))
            )
        ).scalars()
    ]
    demo_group_ids = [
        r for r in (
            await db.execute(
                select(Group.id).where(Group.code.in_(DEMO_GROUP_CODES))
            )
        ).scalars()
    ]
    demo_customer_ids = [
        r for r in (
            await db.execute(
                select(Customer.id).where(
                    Customer.identity_key.in_(DEMO_CUSTOMER_PHONES)
                )
            )
        ).scalars()
    ]
    demo_agent_ids = [
        r for r in (
            await db.execute(
                select(Agent.id).where(Agent.name.in_(DEMO_AGENT_NAMES))
            )
        ).scalars()
    ]
    demo_custom_role_ids = [
        r for r in (
            await db.execute(
                select(Role.id).where(
                    Role.code.in_(DEMO_CUSTOM_ROLE_CODES),
                    Role.is_system.is_(False),
                )
            )
        ).scalars()
    ]

    # ---- 1. Messages + Conversations (by demo agent_ids; conversations FK→agents).
    if demo_agent_ids:
        demo_conv_ids = [
            r for r in (
                await db.execute(
                    select(Conversation.id).where(
                        Conversation.agent_id.in_(demo_agent_ids)
                    )
                )
            ).scalars()
        ]
        if demo_conv_ids:
            await db.execute(
                delete(Message).where(Message.conversation_id.in_(demo_conv_ids))
            )
            await db.execute(
                delete(Conversation).where(Conversation.id.in_(demo_conv_ids))
            )
            print(f"  deleted conversations ({len(demo_conv_ids)}) + messages")

    # ---- 2. API tokens (by demo tenant + demo token names; soft-deleted rows too).
    if demo_tenant_ids:
        await db.execute(
            delete(ApiToken).where(
                ApiToken.tenant_id.in_(demo_tenant_ids),
                ApiToken.name.in_(DEMO_API_TOKEN_NAMES),
            )
        )
        print("  deleted api tokens")

    # ---- 3. LLM configs (tenant-level overrides for demo tenants only;
    #          platform-level demo config keyed by api_key_hint placeholder).
    if demo_tenant_ids:
        await db.execute(
            delete(LlmConfig).where(LlmConfig.tenant_id.in_(demo_tenant_ids))
        )
    # Platform-level demo config: identify by the masked placeholder hint.
    # crypto.mask_api_key("sk-demo-placeholder") → "sk-***lace".
    platform_hint = "sk-***lace"
    await db.execute(
        delete(LlmConfig).where(
            LlmConfig.tenant_id.is_(None),
            LlmConfig.api_key_hint == platform_hint,
        )
    )
    print("  deleted llm configs")

    # ---- 4. Customer profiles + customers (by demo customer ids).
    if demo_customer_ids:
        await db.execute(
            delete(CustomerProfile).where(
                CustomerProfile.customer_id.in_(demo_customer_ids)
            )
        )
        await db.execute(
            delete(Customer).where(Customer.id.in_(demo_customer_ids))
        )
        print(f"  deleted customers ({len(demo_customer_ids)}) + profiles")

    # ---- 5. Custom-role permission grants (SCD2 rows) + custom roles.
    #       System default roles (is_system=True) are kept (seed_defaults owns them).
    if demo_custom_role_ids:
        await db.execute(
            delete(RolePermission).where(
                RolePermission.role_id.in_(demo_custom_role_ids)
            )
        )
        await db.execute(
            delete(Role).where(Role.id.in_(demo_custom_role_ids))
        )
        print(f"  deleted custom roles ({len(demo_custom_role_ids)}) + grants")

    # ---- 6. Agents (by demo agent ids).
    if demo_agent_ids:
        await db.execute(delete(Agent).where(Agent.id.in_(demo_agent_ids)))
        print(f"  deleted agents ({len(demo_agent_ids)})")

    # ---- 7. Extra login methods (by demo user + phone identifier).
    if demo_user_ids:
        await db.execute(
            delete(UserLoginMethod).where(
                UserLoginMethod.identifier.in_(DEMO_EXTRA_LOGIN_IDS)
            )
        )
        print("  deleted extra login methods")

    # ---- 8. UserTenant SCD2 rows + demo users (keep super_admin — not in list).
    if demo_user_ids:
        await db.execute(
            delete(UserTenant).where(UserTenant.user_id.in_(demo_user_ids))
        )
        await db.execute(delete(User).where(User.id.in_(demo_user_ids)))
        print(f"  deleted users ({len(demo_user_ids)}) + memberships")

    # ---- 9. GroupTenant + Groups (by demo group ids).
    if demo_group_ids:
        await db.execute(
            delete(GroupTenant).where(GroupTenant.group_id.in_(demo_group_ids))
        )
        await db.execute(delete(Group).where(Group.id.in_(demo_group_ids)))
        print(f"  deleted groups ({len(demo_group_ids)})")

    # ---- 10. SystemLog rows produced during demo (by demo tenant ids).
    # NOTE: must run BEFORE deleting tenants — SystemLog.tenant_id is
    # FK(ondelete="SET NULL"), so deleting tenants first would NULL out
    # tenant_id and this in_(...) match would silently miss every row.
    if demo_tenant_ids:
        await db.execute(
            delete(SystemLog).where(SystemLog.tenant_id.in_(demo_tenant_ids))
        )
        print("  deleted demo audit logs")

    # ---- 11. Demo tenants.
    if demo_tenant_ids:
        await db.execute(delete(Tenant).where(Tenant.id.in_(demo_tenant_ids)))
        print(f"  deleted tenants ({len(demo_tenant_ids)})")

    # ---- 12. Casbin rows for demo users + demo tenants (grouping + policy).
    from app.core import casbin_enforcer as _casbin_mod  # local import to avoid cycle

    def _do_casbin() -> None:
        e = _casbin_mod.get_enforcer()
        with _casbin_mod.enforcer_lock():
            # g (grouping): g, <user_id>, <role_code>, <tenant_id>
            for uid in demo_user_ids:
                for pol in list(e.get_filtered_policy(0, "g", uid)):
                    e.remove_policy(pol)
            # p (policy): p, <role_code>, <tenant_id>, <obj>, <act>
            for tid in demo_tenant_ids:
                for pol in list(_filtered_policies_for_tenant(e, tid)):
                    e.remove_policy(pol)

    from starlette.concurrency import run_in_threadpool

    await run_in_threadpool(_do_casbin)
    print("  cleared casbin grouping + policies for demo scope")

    await db.commit()
    print("✅ demo data wiped.\n")


def _filtered_policies_for_tenant(enforcer, tenant_id: str):
    """Yield casbin ``p`` policies whose v2 == tenant_id (tenant binding slot)."""
    for pol in list(enforcer.get_filtered_policy(0, "p")):
        # pol = ['p', role_code, tenant_id, obj, act]
        if len(pol) > 2 and pol[2] == tenant_id:
            yield pol


# ----------------------------------------------------------------- new entities
async def _seed_custom_role(
    db, tenant: Tenant, owner: User, member: User
) -> str:
    """Seed the custom role + grant permissions + rebind member. Returns 'created'|'exists'.

    On re-runs the role already exists (skip grant), but the target member must
    still be rebound — step 1 resets staff memberships and would otherwise leave
    the member on their original role, losing the demo of "custom role works".
    """
    _, role_name, role_code, perms, member_username = CUSTOM_ROLE
    svc = RbacService(db)
    existing = (
        await db.execute(
            select(Role).where(
                Role.tenant_id == tenant.id, Role.code == role_code
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        role = await svc.create(
            owner.id,
            tenant.id,
            RoleCreate(name=role_name, code=role_code, description="演示自定义角色:资深理疗师"),
            platform_role=None,
        )
        for obj, act in perms:
            await svc.grant_permission(
                owner.id,
                tenant.id,
                role.id,
                RolePermissionGrant(obj=obj, act=act),
                platform_role=None,
            )
        print(
            f"created custom role: {role_name} ({role_code}) @ {tenant.name} "
            f"with perms {perms}"
        )
    else:
        print(f"exists  custom role: {role_name} @ {tenant.name}")

    # Always ensure the member is bound to the custom role (idempotent).
    # On re-runs step 1 resets staff to their STORES role; this rebind keeps
    # the demo of "custom role actually takes effect" stable across re-runs.
    status = await _ensure_membership(db, member.id, tenant.id, role_code)
    if status != "exists":
        print(f"  ~ {member_username} → {role_code} ({status})")
    return "exists" if existing is not None else "created"


async def _seed_llm_configs(db, tenant_by_name: dict[str, Tenant]) -> None:
    """Seed platform-level config + one tenant-level override (demo 3-tier fallback)."""
    # Platform-level: default deepseek-chat + reasoner; api_key is placeholder.
    existing_platform = (
        await db.execute(
            select(LlmConfig).where(
                LlmConfig.tenant_id.is_(None), LlmConfig.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    # Only (re)seed the demo platform config if none exists OR the existing one
    # is our demo placeholder (don't clobber a real key the user configured).
    need_platform = existing_platform is None or existing_platform.api_key_hint == "sk-***lace"
    if need_platform:
        await llm_config_service.upsert_platform(
            db,
            LlmConfigUpdate(
                api_key=LLM_DEMO_API_KEY,
                base_url="https://api.deepseek.com/v1",
                default_model="deepseek-chat",
                available_models=LLM_PLATFORM_MODELS,
            ),
        )
        print("created/refreshed platform llm config (demo placeholder key)")
    else:
        print("exists  platform llm config (real key present, left untouched)")

    # Tenant-level override: 朝阳 store → deepseek-reasoner.
    chaoyang = tenant_by_name[LLM_TENANT_OVERRIDE_STORE]
    existing_tenant = (
        await db.execute(
            select(LlmConfig).where(
                LlmConfig.tenant_id == chaoyang.id, LlmConfig.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if existing_tenant is None:
        await llm_config_service.upsert_tenant(
            db,
            chaoyang.id,
            LlmConfigUpdate(
                api_key=LLM_DEMO_API_KEY,
                base_url="https://api.deepseek.com/v1",
                default_model=LLM_TENANT_OVERRIDE_MODEL,
                available_models=LLM_PLATFORM_MODELS,
            ),
        )
        print(
            f"created tenant llm override: {LLM_TENANT_OVERRIDE_STORE} → {LLM_TENANT_OVERRIDE_MODEL}"
        )
    else:
        print(
            f"exists  tenant llm override @ {LLM_TENANT_OVERRIDE_STORE} (left untouched)"
        )


async def _seed_conversations(
    db,
    tenant_by_name: dict[str, Tenant],
    owner_by_store: dict[str, User],
    agent_id_by_name: dict[tuple[str, str], str],
    user_by_username: dict[str, User],
) -> None:
    """Seed conversation history (user/assistant turns, hard-coded assistant text)."""
    conv_svc = ConversationService(db)
    for scope, agent_name, actor_username, turns in CONVERSATIONS:
        if scope == "PLATFORM":
            # Platform agent lives in the first store's tenant_id slot; use the
            # hq_staff user as the conversation owner.
            tenant = tenant_by_name[STORES[0][0]]
        else:
            tenant = tenant_by_name[scope]
        agent_id = agent_id_by_name.get((scope, agent_name))
        if agent_id is None:
            print(f"  ⚠️ agent not found, skipping conversations: {agent_name} @ {scope}")
            continue
        actor = user_by_username[actor_username]
        first_msg = next((c for r, c in turns if r == "user"), None) or "新对话"
        title = first_msg[:20] + "…" if len(first_msg) > 20 else first_msg
        # Idempotency: skip if a conversation with this (tenant, agent, user, title) exists.
        existing = (
            await db.execute(
                select(Conversation).where(
                    Conversation.tenant_id == tenant.id,
                    Conversation.agent_id == agent_id,
                    Conversation.user_id == actor.id,
                    Conversation.title == title,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"exists  conversation: {title[:24]} ({agent_name})")
            continue
        conv = await conv_svc.create_or_get(
            user_id=actor.id,
            tenant_id=tenant.id,
            agent_id=agent_id,
            title=title,
            platform_role=actor.platform_role,
        )
        for role, content in turns:
            await conv_svc.append_message(tenant.id, conv.id, role, content)
        print(f"created conversation: {title[:24]} ({len(turns)} msgs, {agent_name})")


async def _seed_api_tokens(
    db, tenant_by_name: dict[str, Tenant], owner_by_store: dict[str, User]
) -> list[tuple[str, str]]:
    """Seed 2 API tokens (store owners). Returns [(store_name, plaintext_token)]."""
    issued: list[tuple[str, str]] = []
    for store_name, token_name in API_TOKENS:
        tenant = tenant_by_name[store_name]
        owner = owner_by_store[store_name]
        # Idempotency: skip if a live token with this name exists.
        existing = (
            await db.execute(
                select(ApiToken).where(
                    ApiToken.tenant_id == tenant.id,
                    ApiToken.name == token_name,
                    ApiToken.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"exists  api token: {token_name} @ {store_name}")
            continue
        resp = await api_token_service.issue(
            db,
            owner.id,
            tenant.id,
            ApiTokenCreate(name=token_name),
            platform_role=None,
        )
        issued.append((store_name, resp.token))
        print(f"created api token: {token_name} @ {store_name} ({resp.token_prefix}***)")
    return issued


async def _seed_extra_login_methods(db, user_by_username: dict[str, User]) -> None:
    """Seed phone login methods (demo 'one user, multiple login methods')."""
    for username, phone in EXTRA_LOGIN_METHODS:
        user = user_by_username[username]
        existing = (
            await db.execute(
                select(UserLoginMethod).where(
                    UserLoginMethod.user_id == user.id,
                    UserLoginMethod.login_type == "phone",
                    UserLoginMethod.identifier == phone,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"exists  login method: {username} phone={phone}")
            continue
        db.add(
            UserLoginMethod(
                user_id=user.id,
                login_type="phone",
                identifier=phone,
                is_verified=True,
                is_primary=False,
            )
        )
        await db.flush()
        print(f"created login method: {username} phone={phone}")


# ------------------------------------------------------------------------ main
async def main(reset: bool = False) -> int:
    async with AsyncSessionLocal() as db:
        # ---- 0. super_admin must already exist (init_admin.py creates it).
        super_admin = (
            await db.execute(
                select(User).where(User.platform_role == "super_admin")
            )
        ).scalar_one_or_none()
        if super_admin is None:
            print("❌ No super_admin found. Run `python scripts/init_admin.py` first.")
            return 1
        print(f"super_admin present: {super_admin.username} ({super_admin.id})")

        if reset:
            await _reset_demo_data(db)

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
            # Staff listed in CUSTOM_ROLE are bound in step 6 (custom-role rebind),
            # so skip them here to avoid SCD2 churn on re-runs.
            custom_role_members = {CUSTOM_ROLE[4]}  # usernames rebound by step 6
            for username, display_name, role in staff:
                if (
                    store_name == CUSTOM_ROLE[0]
                    and username in custom_role_members
                ):
                    # Still create the user, but defer role binding to step 6.
                    user, u_created = await _get_or_create_user(
                        db, username, display_name
                    )
                    if u_created:
                        print(f"  created staff: {username} ({display_name})")
                    continue
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

        # Build a username → User index (used by conversations/login-methods).
        user_by_username: dict[str, User] = {}
        for _store_name, staff in STORES:
            for username, _, _ in staff:
                u = (
                    await db.execute(select(User).where(User.username == username))
                ).scalar_one()
                user_by_username[username] = u
        user_by_username[hq_username] = hq_user
        # super_admin is referenced by the PLATFORM summary conversation actor.
        user_by_username[super_admin.username] = super_admin

        # ---- 3. Groups (platform-level business orgs).
        group_svc = GroupService(db)
        for gname, gcode, store_names in GROUPS:
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

        # ---- 5. Agents (3 store-level + 1 platform-level) with reasoning params.
        agent_svc = AgentService(db)
        agent_id_by_name: dict[tuple[str, str], str] = {}
        for scope, aname, aprompt, amodel, atemp, amax_tok, atop_p in AGENTS:
            if scope == "PLATFORM":
                # Platform-level agent: attach to the first tenant (owner =
                # super_admin bypasses per-tenant permission via platform_role).
                tenant = tenant_by_name[STORES[0][0]]
                actor = super_admin
            else:
                tenant = tenant_by_name[scope]
                actor = owner_by_store[scope]
            existing = (
                await db.execute(
                    select(Agent).where(
                        Agent.name == aname, Agent.tenant_id == tenant.id
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                print(f"exists  agent: {aname} @ {scope}")
                agent_id_by_name[(scope, aname)] = existing.id
                continue
            created = await agent_svc.create(
                actor.id,
                tenant.id,
                AgentCreate(
                    name=aname,
                    system_prompt=aprompt,
                    model=amodel,
                    description=f"演示智能体:{aname}",
                    temperature=atemp,
                    max_tokens=amax_tok,
                    top_p=atop_p,
                ),
                platform_role=actor.platform_role,
            )
            agent_id_by_name[(scope, aname)] = created.id
            print(
                f"created agent: {aname} @ {scope} "
                f"(temp={atemp}, max_tok={amax_tok}, top_p={atop_p})"
            )

        # ---- 6. Custom role + differentiated permissions (demo RBAC flexibility).
        _, _, _, _, member_username = CUSTOM_ROLE
        # 朝阳 store: owner 陈馆长 creates the role; 李师傅 rebound to it.
        custom_tenant = tenant_by_name[CUSTOM_ROLE[0]]
        custom_owner = owner_by_store[CUSTOM_ROLE[0]]
        custom_member = user_by_username[member_username]
        await _seed_custom_role(db, custom_tenant, custom_owner, custom_member)

        # ---- 7. LLM configs (platform-level + 朝阳 tenant-level override).
        await _seed_llm_configs(db, tenant_by_name)

        # ---- 8. Conversation history (AI core artifacts).
        await _seed_conversations(
            db, tenant_by_name, owner_by_store, agent_id_by_name, user_by_username
        )

        # ---- 9. API tokens (demo AtoA).
        issued_tokens = await _seed_api_tokens(db, tenant_by_name, owner_by_store)

        # ---- 10. Extra login methods (multi-login demo).
        await _seed_extra_login_methods(db, user_by_username)

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
    print("   agent reasoning params: 朝阳 temp=0.3 / 海淀 0.7 / 王府井 0.9 / 总部 0.2")
    print(
        "   llm fallback: 朝阳→deepseek-reasoner(租户级), 海淀/王府井→deepseek-chat(平台级)"
    )
    print("   custom role: 资深理疗师(朝阳店, customers:read+update) ← 李师傅")
    if issued_tokens:
        print("   api tokens (⚠️ shown ONCE, demo-only):")
        for store_name, tok in issued_tokens:
            print(f"     {store_name}: {tok}")
    print("   SystemLog 审计行由 Service 调用自然产生(role.create/role.grant 等)")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed the 大健康连锁 demo dataset (idempotent).",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Wipe demo-marked data (white-list scoped) then full rebuild.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    raise SystemExit(asyncio.run(main(reset=args.reset)))
