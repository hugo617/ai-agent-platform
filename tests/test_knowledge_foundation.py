"""Knowledge-tiered foundation slice 01 — data-model ground tests.

Plan: ``harness/docs/plan-knowledge-tiered-foundation.md`` slice 01.

This slice lays the schema ground for the 3-level knowledge permissions:
``Group`` gains a headquarters pointer, ``GroupTenant`` collapses to 1:1,
``Document`` gains ``scope``/``group_id``/``category_id``, and two new tables
(``knowledge_categories`` / ``knowledge_distribution``) are introduced.

Tests use ``create_all`` (not the migration), so the migration's seeded
platform Categories are absent unless a test inserts them — this isolates the
*model definition* (what this slice delivers) from the *migration runtime*
(covered by ``alembic upgrade head && alembic check`` on Postgres).

Chapter layout (matches slice 01 AC checklist):

- G. Group — ``headquarters_tenant_id`` FK nullable read/write (AC1).
- T. GroupTenant — tenant_id unique index collapses M2M to 1:1 (AC2).
- D. Document — ``scope`` default 'store' NOT NULL + group_id/category_id
  nullable FKs (AC3).
- C. knowledge_categories — create/query + partial unique active index (AC4).
- X. knowledge_distribution — create + UniqueConstraint(source, target) (AC5).
- S. migration seed idempotency — 5 platform Categories via INSERT WHERE NOT
  EXISTS, re-runnable (AC7, exercised at SQL level since create_all skips it).
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.smoke

# The JWT is mocked by the test client (conftest's _build_client), so any bearer
# token string suffices for the Authorization header — mirrors test_tenants_api.
AUTH = {"Authorization": "Bearer fake"}


# --------------------------------------------------------------------- helpers


def _uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


# --------------------------------------------------------------------- G. Group


@pytest.mark.asyncio
async def test_group_headquarters_tenant_id_is_nullable_by_default(db_session):
    """AC1: Group.headquarters_tenant_id FK tenants.id, nullable; defaults None."""
    from app.models.group import Group

    g = Group(name=_uuid("grp"))
    db_session.add(g)
    await db_session.commit()
    await db_session.refresh(g)

    assert g.headquarters_tenant_id is None


@pytest.mark.asyncio
async def test_group_headquarters_tenant_id_references_tenant(db_session):
    """AC1: headquarters_tenant_id accepts a real tenant id and persists."""
    from app.models.group import Group
    from app.models.tenant import Tenant

    tenant = Tenant(id=_uuid("tnt"), name="HQ Store")
    db_session.add(tenant)
    await db_session.flush()

    g = Group(name=_uuid("grp"), headquarters_tenant_id=tenant.id)
    db_session.add(g)
    await db_session.commit()
    await db_session.refresh(g)

    assert g.headquarters_tenant_id == tenant.id


# ----------------------------------------------------------------- T. GroupTenant


@pytest.mark.asyncio
async def test_group_tenant_unique_index_collapses_m2m_to_one(db_session):
    """AC2: a tenant attached to one group cannot attach to another (1:1).

    The tenant_id unique index enforces D8's collapse of the many-to-many into
    a one-store-one-group relationship. A second GroupTenant row for the same
    tenant — even under a different group — must violate the constraint.
    """
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant

    tenant = Tenant(id=_uuid("tnt"), name="Store")
    db_session.add(tenant)
    await db_session.flush()

    g1 = Group(name=_uuid("grp"))
    g2 = Group(name=_uuid("grp"))
    db_session.add_all([g1, g2])
    await db_session.flush()

    db_session.add(GroupTenant(group_id=g1.id, tenant_id=tenant.id))
    await db_session.flush()

    # Second attachment of the same tenant to a different group must fail.
    db_session.add(GroupTenant(group_id=g2.id, tenant_id=tenant.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_group_tenant_table_args_declares_tenant_id_unique_index():
    """AC2: GroupTenant ORM __table_args__ declares tenant_id as a unique index.

    The collapse-to-1:1 is enforced by a *unique* index on tenant_id (not just
    the (group_id, tenant_id) pair-uniqueness). This names it so the migration
    can mirror it and so grep finds the intent.
    """
    from app.models.group import GroupTenant

    table = GroupTenant.__table__
    unique_tenant_indexes = [
        idx
        for idx in table.indexes
        if "tenant_id" in idx.columns and idx.unique
    ]
    assert len(unique_tenant_indexes) == 1, (
        "GroupTenant must declare a unique index on tenant_id to collapse M2M "
        "to one-store-one-group (D8). Found indexes: "
        f"{[(i.name, [c.name for c in i.columns], i.unique) for i in table.indexes]}"
    )


# ------------------------------------------------------------------- D. Document


@pytest.mark.asyncio
async def test_document_scope_defaults_to_store(db_session):
    """AC3: Document.scope defaults to 'store' and is NOT NULL.

    The default encodes the pre-tiering reality: every existing store-level
    document is scope='store'. New documents inherit it unless a caller sets
    platform/group explicitly (Feature B enforces the caller's permission).
    """
    from app.models.document import Document
    from app.models.tenant import Tenant

    tenant = Tenant(id=_uuid("tnt"), name="Store")
    db_session.add(tenant)
    await db_session.flush()

    doc = Document(tenant_id=tenant.id, name="doc", content="")
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    assert doc.scope == "store"


@pytest.mark.asyncio
async def test_document_group_id_and_category_id_are_nullable(db_session):
    """AC3: Document.group_id and category_id are nullable FKs.

    scope='store' documents carry neither; scope='group' documents set group_id
    (Feature B enforces); any document may pick a platform/group/store Category
    or none. At the model layer both default to None.
    """
    from app.models.document import Document
    from app.models.tenant import Tenant

    tenant = Tenant(id=_uuid("tnt"), name="Store")
    db_session.add(tenant)
    await db_session.flush()

    doc = Document(tenant_id=tenant.id, name="doc", content="")
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    assert doc.group_id is None
    assert doc.category_id is None


@pytest.mark.asyncio
async def test_document_scope_can_be_set_to_group_or_platform(db_session):
    """AC3: scope accepts 'group' / 'platform' values (Feature B gates writes).

    The model layer holds any of platform/group/store; permission gating is a
    service-layer concern (Feature B). This test just confirms the column is a
    free String that stores what's given.
    """
    from app.models.document import Document
    from app.models.group import Group
    from app.models.tenant import Tenant

    tenant = Tenant(id=_uuid("tnt"), name="HQ Store")
    group = Group(name=_uuid("grp"), headquarters_tenant_id=None)
    db_session.add_all([tenant, group])
    await db_session.flush()

    doc = Document(
        tenant_id=tenant.id, name="group doc", content="", scope="group",
        group_id=group.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    assert doc.scope == "group"
    assert doc.group_id == group.id


# ------------------------------------------------------- C. knowledge_categories


@pytest.mark.asyncio
async def test_knowledge_category_create_platform_scope(db_session):
    """AC4: a platform-scope Category (group_id/tenant_id both null) persists."""
    from app.models.knowledge_category import KnowledgeCategory

    cat = KnowledgeCategory(name="产品手册", scope="platform", sort_order=10)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    assert cat.scope == "platform"
    assert cat.group_id is None
    assert cat.tenant_id is None
    assert cat.is_deleted is False


@pytest.mark.asyncio
async def test_knowledge_category_create_store_scope_with_tenant(db_session):
    """AC4: a store-scope Category carries a tenant_id."""
    from app.models.knowledge_category import KnowledgeCategory
    from app.models.tenant import Tenant

    tenant = Tenant(id=_uuid("tnt"), name="Store")
    db_session.add(tenant)
    await db_session.flush()

    cat = KnowledgeCategory(
        name="门店自定义", scope="store", tenant_id=tenant.id, sort_order=0,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    assert cat.scope == "store"
    assert cat.tenant_id == tenant.id


def test_knowledge_category_table_args_has_scope_index_and_active_unique():
    """AC4: scope index + partial unique index on (scope, name, group_id,
    tenant_id) among *live* rows.

    The partial unique index prevents same-named active Categories within a
    scope while allowing soft-deleted duplicates (mirrors User/Group convention).
    Mirrored PG/SQLite via dialect-specific WHERE clauses.
    """
    from app.models.knowledge_category import KnowledgeCategory

    table = KnowledgeCategory.__table__
    scope_indexes = [i for i in table.indexes if "scope" in i.columns]
    assert scope_indexes, "knowledge_categories must index scope"

    # At least one unique index covering (scope, name, group_id, tenant_id).
    colnames = lambda idx: {c.name for c in idx.columns}  # noqa: E731
    active_unique = [
        i
        for i in table.indexes
        if i.unique
        and {"scope", "name", "group_id", "tenant_id"}.issubset(colnames(i))
    ]
    assert active_unique, (
        "knowledge_categories must declare a unique index over "
        "(scope, name, group_id, tenant_id) to prevent same-named active "
        "Categories within a scope. Found: "
        f"{[(i.name, sorted(colnames(i)), i.unique) for i in table.indexes]}"
    )


# ---------------------------------------------------- X. knowledge_distribution


@pytest.mark.asyncio
async def test_knowledge_distribution_create_links_doc_to_target(db_session):
    """AC5: a distribution row links a source doc to a target tenant.

    The reference model (D4): distribution is a pointer, not a copy. One row =
    "doc X is visible to store Y". is_active defaults True; distributed_at and
    distributed_by carry the audit trail.
    """
    from app.models.document import Document
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.models.tenant import Tenant, User

    src_tenant = Tenant(id=_uuid("tnt"), name="HQ")
    tgt_tenant = Tenant(id=_uuid("tnt"), name="Store")
    user = User(id=_uuid("user"), email="h@example.com", status="active")
    db_session.add_all([src_tenant, tgt_tenant, user])
    await db_session.flush()

    doc = Document(tenant_id=src_tenant.id, name="manual", content="")
    db_session.add(doc)
    await db_session.flush()

    dist = KnowledgeDistribution(
        source_doc_id=doc.id,
        target_tenant_id=tgt_tenant.id,
        distributed_by=user.id,
    )
    db_session.add(dist)
    await db_session.commit()
    await db_session.refresh(dist)

    assert dist.is_active is True
    assert dist.distributed_at is not None


@pytest.mark.asyncio
async def test_knowledge_distribution_unique_constraint_source_target(db_session):
    """AC5: UniqueConstraint(source_doc_id, target_tenant_id) blocks re-distribute.

    Distributing the same doc to the same store twice is a duplicate
    relationship (D4 reference model). The constraint enforces "at most one row
    per (doc, target)" regardless of is_active, so revoking + re-distributing
    must re-enable the existing row rather than insert a new one (Feature B's
    concern; this test only pins the DB-level guard).
    """
    from app.models.document import Document
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.models.tenant import Tenant

    src_tenant = Tenant(id=_uuid("tnt"), name="HQ")
    tgt_tenant = Tenant(id=_uuid("tnt"), name="Store")
    db_session.add_all([src_tenant, tgt_tenant])
    await db_session.flush()

    doc = Document(tenant_id=src_tenant.id, name="manual", content="")
    db_session.add(doc)
    await db_session.flush()

    db_session.add(
        KnowledgeDistribution(source_doc_id=doc.id, target_tenant_id=tgt_tenant.id)
    )
    await db_session.flush()

    # Second row for the same (doc, target) must violate the unique constraint.
    db_session.add(
        KnowledgeDistribution(source_doc_id=doc.id, target_tenant_id=tgt_tenant.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_knowledge_distribution_table_args_has_target_index_and_unique():
    """AC5: target_tenant_id index + a uniqueness guard over (source, target).

    The uniqueness may be declared either as a UniqueConstraint or as a unique
    Index — both are valid SQLAlchemy and both render the same DB-level guard.
    This test checks the union of ``table.indexes`` and ``table.constraints``
    so it accepts either form (GroupTenant uses UniqueConstraint; Group uses a
    unique Index — both idioms are in-repo).
    """
    from app.models.knowledge_distribution import KnowledgeDistribution

    table = KnowledgeDistribution.__table__
    colnames = lambda item: {c.name for c in item.columns}  # noqa: E731

    target_indexes = [i for i in table.indexes if "target_tenant_id" in colnames(i)]
    assert target_indexes, "knowledge_distribution must index target_tenant_id"

    # Uniqueness may live in indexes (unique=True) or in constraints
    # (UniqueConstraint — which has no .unique attr, hence the isinstance check).
    # Search both for the (source_doc_id, target) pair.
    from sqlalchemy import UniqueConstraint as _UQ

    def _is_unique(item) -> bool:
        if isinstance(item, _UQ):
            return True
        return bool(getattr(item, "unique", False))

    unique_guards = [
        item
        for item in (*table.indexes, *table.constraints)
        if _is_unique(item)
        and {"source_doc_id", "target_tenant_id"}.issubset(colnames(item))
    ]
    assert unique_guards, (
        "knowledge_distribution must declare a unique guard over "
        "(source_doc_id, target_tenant_id) — as UniqueConstraint or unique "
        "Index. Indexes: "
        f"{[(i.name, sorted(colnames(i)), i.unique) for i in table.indexes]}; "
        "Constraints: "
        f"{[(type(c).__name__, getattr(c,'name',None), sorted(colnames(c))) for c in table.constraints]}"
    )


# ----------------------------------------------------- M. migration behaviors
#
# These exercise the migration's runtime logic (M2M pre-check AC9 + seed
# idempotency AC7) at the SQL level against real SQLite. The full migration
# runs on Postgres in CI/docker (plan §10 AC6/AC10); these tests pin the
# *logic* the migration relies on (the exact SQL it executes) so a careless
# edit to the migration is caught in-repo without needing Postgres here.


def test_migration_m2m_pre_check_sql_detects_dirty_data():
    """AC9: the pre-check SQL the migration runs detects dirty M2M data.

    Mirrors the exact query the migration's pre-check uses (see
    alembic/versions/2026_08_06_1000_..._foundation.py step 1) against real
    SQLite data, both dirty (a tenant in 2 groups → count 1) and clean (count 0).
    D8 requires one-tenant-one-group; dirty data must abort (E7), never be
    silently de-duped.
    """
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE group_tenants (id TEXT, group_id TEXT, tenant_id TEXT);"
        "INSERT INTO group_tenants VALUES ('1','g1','t1'),('2','g2','t2'),"
        "('3','g1','t3'),('4','g2','t3');"  # t3 in g1 AND g2 = dirty
    )
    dirty = conn.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT tenant_id FROM group_tenants GROUP BY tenant_id HAVING COUNT(*) > 1"
        ") AS _dup"
    ).fetchone()[0]
    assert dirty == 1

    conn.execute("DELETE FROM group_tenants WHERE id IN ('3','4')")
    dirty_clean = conn.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT tenant_id FROM group_tenants GROUP BY tenant_id HAVING COUNT(*) > 1"
        ") AS _dup"
    ).fetchone()[0]
    assert dirty_clean == 0


def test_migration_seed_is_idempotent():
    """AC7: the 5 platform Categories are re-insertable without duplication.

    The migration guards each seed INSERT with ``WHERE NOT EXISTS`` (mirrors
    booking_configs). This test runs the exact INSERT...WHERE NOT EXISTS pattern
    the migration emits, twice, against a real SQLite knowledge_categories table,
    and asserts exactly 5 rows survive — the second pass adds nothing.

    The 5 (id, name, sort_order) tuples mirror the migration module's
    _PLATFORM_CATEGORIES verbatim (kept in sync by name+scope assertions below).
    """
    import sqlite3

    platform_categories = [
        ("cat-platform-product-manual", "产品手册", 10),
        ("cat-platform-faq", "FAQ", 20),
        ("cat-platform-sales-script", "话术脚本", 30),
        ("cat-platform-service-standard", "服务规范", 40),
        ("cat-platform-promo-copy", "促销文案", 50),
    ]

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE knowledge_categories ("
        " id TEXT, name TEXT, scope TEXT, group_id TEXT, tenant_id TEXT,"
        " sort_order INTEGER, is_deleted INTEGER, "
        " created_at DATETIME, updated_at DATETIME)"
    )
    conn.commit()

    def _seed_pass() -> None:
        for cat_id, name, sort_order in platform_categories:
            conn.execute(
                "INSERT INTO knowledge_categories "
                "(id, name, scope, group_id, tenant_id, sort_order, is_deleted) "
                f"SELECT '{cat_id}', '{name}', 'platform', NULL, NULL, {sort_order}, 0 "
                "WHERE NOT EXISTS ("
                f"SELECT 1 FROM knowledge_categories WHERE id = '{cat_id}'"
                ")"
            )
        conn.commit()

    _seed_pass()
    _seed_pass()  # idempotent second pass — must add nothing

    rows = conn.execute(
        "SELECT name FROM knowledge_categories WHERE scope='platform' "
        "ORDER BY sort_order"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "产品手册", "FAQ", "话术脚本", "服务规范", "促销文案"
    ]


def test_migration_seed_categories_match_repo_constant():
    """AC7 contract: the migration's _PLATFORM_CATEGORIES names match this test.

    The seed-idempotency test above hardcodes the 5 Category names to avoid
    importing the migration module (whose ``from alembic import op`` is masked
    by the repo's own ``alembic/`` dir under importlib). This test reads the
    migration source and asserts the names appear, so a rename in the migration
    without a matching test update is caught here rather than slipping into a
    silent drift.
    """
    from pathlib import Path

    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "2026_08_06_1000_05fa069297cc_add_knowledge_tiered_foundation.py"
    )
    assert migration_path.exists(), f"migration file missing: {migration_path}"
    source = migration_path.read_text(encoding="utf-8")
    for expected_name in ("产品手册", "FAQ", "话术脚本", "服务规范", "促销文案"):
        assert expected_name in source, (
            f"migration {migration_path.name} must seed platform Category "
            f"'{expected_name}' (D5). If you renamed it, update both the "
            f"migration's _PLATFORM_CATEGORIES and this test + the "
            f"seed-idempotency test's expected list."
        )
    # All 5 must live in the _PLATFORM_CATEGORIES block (not just anywhere in
    # the docstring). Confirm the constant is defined and non-empty.
    assert "_PLATFORM_CATEGORIES = [" in source


# ===========================================================================
# Slice 02 — permission derivation + single-store auto-grouping
# (plan-knowledge-tiered-foundation.md §切片 02)
#
# Three chapters:
# - P. is_group_admin derived identity (AC1-3) — 6 boundary cases.
# - B. check() knowledge bypass (AC4-6) — 3 cases (allow knowledge / reject
#   devices / safe-degrade when tenant has no group).
# - A. create_tenant auto-grouping step 7 (AC7-8) — single-store becomes its
#   own one-member group at creation.
#
# These tests exercise the *service-layer* derivation logic, so they build
# real Group/GroupTenant/UserTenant rows against the same in-memory SQLite
# ``db_session`` fixture (create_all, not the migration).
# ===========================================================================


# ---------------------------------------------------------------- P. is_group_admin
#
# AC1: ``is_group_admin`` is a module-level async helper taking (db, user_id,
# group_id) and returning bool — siblings of ``is_cross_tenant_viewer`` /
# ``is_platform_writer`` (the only difference: it queries the DB, hence
# async+db).
# AC2: judgement = look up ``group.headquarters_tenant_id`` → the user's
# *current* (SCD2 valid_to IS NULL) role on that tenant → role in (owner, admin).
# AC3: six boundaries — member=False, no headquarters=None→False, cross-group
# =False, user not on that tenant=False, group absent=False (and the positive
# owner/admin=True).


async def _seed_group_with_hq(
    db_session,
    *,
    group_name: str,
    hq_tenant_id: str,
):
    """Build a Group whose headquarters is ``hq_tenant_id`` and return it.

    Used by the is_group_admin matrix: the group_admin identity derives from
    the owner/admin of the headquarters tenant, so each case wires a Group →
    HQ tenant → user membership and then asserts the derivation.
    """
    from app.models.group import Group

    group = Group(name=group_name, headquarters_tenant_id=hq_tenant_id)
    db_session.add(group)
    await db_session.flush()
    return group


async def _seed_user_role(db_session, *, user_id: str, tenant_id: str, role: str):
    """Insert an *active* UserTenant row (SCD2 current state) for a user.

    Mirrors what ``UserTenantRepository.assign_role`` ends up persisting, but
    inline so the test is explicit about the exact row that drives the
    derivation (no hidden helper behavior).
    """
    from app.models.tenant import UserTenant

    db_session.add(
        UserTenant(
            user_id=user_id, tenant_id=tenant_id, role=role, valid_to=None
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_is_group_admin_true_for_headquarters_owner(db_session):
    """AC2/AC3: owner of the headquarters tenant derives group_admin."""
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin

    hq = Tenant(id=_uuid("tnt"), name="HQ Store")
    db_session.add(hq)
    await db_session.flush()
    group = await _seed_group_with_hq(
        db_session, group_name="Chain", hq_tenant_id=hq.id
    )
    await _seed_user_role(
        db_session, user_id="u-owner", tenant_id=hq.id, role="owner"
    )
    await db_session.commit()

    assert await is_group_admin(db_session, "u-owner", group.id) is True


@pytest.mark.asyncio
async def test_is_group_admin_true_for_headquarters_admin(db_session):
    """AC2/AC3: admin of the headquarters tenant also derives group_admin."""
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin

    hq = Tenant(id=_uuid("tnt"), name="HQ Store")
    db_session.add(hq)
    await db_session.flush()
    group = await _seed_group_with_hq(
        db_session, group_name="Chain", hq_tenant_id=hq.id
    )
    await _seed_user_role(
        db_session, user_id="u-admin", tenant_id=hq.id, role="admin"
    )
    await db_session.commit()

    assert await is_group_admin(db_session, "u-admin", group.id) is True


@pytest.mark.asyncio
async def test_is_group_admin_false_for_headquarters_member(db_session):
    """AC3 boundary: a member of the headquarters tenant is NOT group_admin
    (D1 edge rule 1 — only owner/admin of the HQ store derive the identity)."""
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin

    hq = Tenant(id=_uuid("tnt"), name="HQ Store")
    db_session.add(hq)
    await db_session.flush()
    group = await _seed_group_with_hq(
        db_session, group_name="Chain", hq_tenant_id=hq.id
    )
    await _seed_user_role(
        db_session, user_id="u-member", tenant_id=hq.id, role="member"
    )
    await db_session.commit()

    assert await is_group_admin(db_session, "u-member", group.id) is False


@pytest.mark.asyncio
async def test_is_group_admin_false_when_group_has_no_headquarters(db_session):
    """AC3 boundary: a group with headquarters_tenant_id=None yields False
    (no HQ tenant → nobody can derive group_admin from it)."""
    from app.models.group import Group
    from app.services.permission_service import is_group_admin

    group = Group(name=_uuid("grp"), headquarters_tenant_id=None)
    db_session.add(group)
    await db_session.commit()

    assert await is_group_admin(db_session, "u-anyone", group.id) is False


@pytest.mark.asyncio
async def test_is_group_admin_false_for_cross_group_user(db_session):
    """AC3 boundary: owner of tenant B's group is NOT group_admin of tenant A's
    group (cross-group isolation — D1 edge rule 2)."""
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin

    hq_a = Tenant(id=_uuid("tnt"), name="HQ A")
    hq_b = Tenant(id=_uuid("tnt"), name="HQ B")
    db_session.add_all([hq_a, hq_b])
    await db_session.flush()
    group_a = await _seed_group_with_hq(
        db_session, group_name="Chain A", hq_tenant_id=hq_a.id
    )
    await _seed_group_with_hq(
        db_session, group_name="Chain B", hq_tenant_id=hq_b.id
    )
    # user is owner of B's HQ — must NOT count as admin of A's group.
    await _seed_user_role(
        db_session, user_id="u-b-owner", tenant_id=hq_b.id, role="owner"
    )
    await db_session.commit()

    assert await is_group_admin(db_session, "u-b-owner", group_a.id) is False


@pytest.mark.asyncio
async def test_is_group_admin_false_when_user_not_in_headquarters_tenant(
    db_session,
):
    """AC3 boundary: user with no active membership on the HQ tenant → False
    (the derivation looks for a *current* SCD2 row; absent → None → False)."""
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin

    hq = Tenant(id=_uuid("tnt"), name="HQ Store")
    db_session.add(hq)
    await db_session.flush()
    group = await _seed_group_with_hq(
        db_session, group_name="Chain", hq_tenant_id=hq.id
    )
    await db_session.commit()
    # No UserTenant row seeded for "u-stranger" on hq.id.

    assert await is_group_admin(db_session, "u-stranger", group.id) is False


@pytest.mark.asyncio
async def test_is_group_admin_false_when_group_absent(db_session):
    """AC3 boundary: a non-existent group id → False (never raises)."""
    from app.services.permission_service import is_group_admin

    assert await is_group_admin(db_session, "u-anyone", "no-such-group") is False


# -------------------------------------------------------- B. check() knowledge bypass
#
# AC4: ``check()`` gains a bypass branch — when ``obj=='knowledge'`` and the
# caller is NOT already short-circuited by super_admin/hq_staff, it derives the
# group context from ``tenant_id`` (group_tenants 1:1 after D8) and, if the
# user is that group's admin (``is_group_admin``), returns True. When the
# tenant has no group the reverse lookup yields None and the check safely
# degrades to the casbin path.
# AC5: the bypass is strictly scoped to ``obj=='knowledge'`` — a group_admin
# asking for devices/bookings/etc. still goes through casbin (D9 scope guard).
# AC6: ``check()`` signature is unchanged for the 60+ existing callers; the db
# needed for the reverse lookup is an OPTIONAL trailing param (defaults None),
# so callers that don't pass it never trigger the bypass (zero behavior change).


async def _seed_grouped_tenant_with_owner(db_session, *, tenant_name, user_id):
    """Build a self-grouped tenant (HQ of its own group) + an owner membership.

    Returns ``(tenant, group)``. This is exactly the shape ``create_tenant``
    will produce after slice 02's step 7 (single-store = its own group), so the
    check() bypass tests operate on realistic data.
    """
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant, UserTenant

    tenant = Tenant(id=_uuid("tnt"), name=tenant_name)
    db_session.add(tenant)
    await db_session.flush()
    group = Group(name=tenant_name, headquarters_tenant_id=tenant.id)
    db_session.add(group)
    await db_session.flush()
    db_session.add(GroupTenant(group_id=group.id, tenant_id=tenant.id))
    db_session.add(
        UserTenant(
            user_id=user_id, tenant_id=tenant.id, role="owner", valid_to=None
        )
    )
    await db_session.commit()
    return tenant, group


@pytest.mark.asyncio
async def test_check_bypasses_casbin_for_group_admin_on_knowledge(db_session):
    """AC4: a group_admin (HQ owner) acting on obj=knowledge is allowed even
    without any casbin knowledge policy (the bypass short-circuits casbin)."""
    from app.services.permission_service import permission_service

    tenant, _group = await _seed_grouped_tenant_with_owner(
        db_session, tenant_name="HQ Store", user_id="u-hq-owner"
    )

    # No casbin knowledge policy seeded for this user → without the bypass the
    # check would fall through to casbin and return False. The group_admin
    # derivation must let the HQ owner through on knowledge.
    allowed = await permission_service.check(
        "u-hq-owner", tenant.id, "knowledge", "create", db=db_session
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_check_does_not_bypass_for_group_admin_on_devices(db_session):
    """AC5 (D9 scope guard): the group_admin bypass is knowledge-only. The same
    HQ owner hitting devices still goes through casbin — which has no policy
    for them here, so the result is False (not silently elevated)."""
    from app.services.permission_service import permission_service

    tenant, _group = await _seed_grouped_tenant_with_owner(
        db_session, tenant_name="HQ Store", user_id="u-hq-owner"
    )

    allowed = await permission_service.check(
        "u-hq-owner", tenant.id, "devices", "create", db=db_session
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_check_safe_degrades_when_tenant_has_no_group(db_session):
    """AC4 boundary: when the tenant belongs to no group (reverse lookup None),
    the knowledge bypass cannot fire and the check degrades to casbin. With no
    casbin policy, the result is False — never an error."""
    from app.models.tenant import Tenant, UserTenant
    from app.services.permission_service import permission_service

    # A lone tenant with an owner but NO group attached (the pre-automation
    # shape, or a tenant created before slice 02's step 7 existed).
    tenant = Tenant(id=_uuid("tnt"), name="Lone Store")
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        UserTenant(
            user_id="u-lone", tenant_id=tenant.id, role="owner", valid_to=None
        )
    )
    await db_session.commit()

    allowed = await permission_service.check(
        "u-lone", tenant.id, "knowledge", "read", db=db_session
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_check_without_db_arg_preserves_legacy_behavior(db_session):
    """AC6: callers that don't pass ``db`` get the pre-slice-02 behavior — the
    group_admin bypass never fires, so a HQ owner with no casbin knowledge
    policy is denied (zero behavior change for the 60+ existing callers)."""
    from app.services.permission_service import permission_service

    tenant, _group = await _seed_grouped_tenant_with_owner(
        db_session, tenant_name="HQ Store", user_id="u-hq-owner"
    )

    # db omitted → bypass cannot run → falls through to casbin → False.
    allowed = await permission_service.check(
        "u-hq-owner", tenant.id, "knowledge", "create"
    )
    assert allowed is False


# -------------------------------------------------- A. create_tenant auto-grouping
#
# AC7: ``create_tenant`` gains a 7th step — ALWAYS create a Group
# (name=tenant.name, headquarters_tenant_id=tenant.id) and attach the new
# tenant to it, in the SAME transaction (after the wallet step, before commit).
# So every store is born as its own one-member group (single-store = its own
# chain, knowledge-tiered D8+D10+E2).
# AC8: transactional consistency — if step 7 fails the whole create_tenant
# rolls back (no orphan tenant without a group).
#
# These go through the real HTTP path (super_admin_client) so the full 7-step
# pipeline runs including casbin seeding, then assert the group side-effects
# on ``db_session``.


@pytest.mark.asyncio
async def test_create_tenant_auto_creates_self_group(super_admin_client, db_session):
    """AC7: creating a tenant also creates a Group acting as its own chain HQ.

    The group's name mirrors the tenant's name and its headquarters_tenant_id
    points back at the new tenant — the single-store = its-own-group invariant.
    """
    from sqlalchemy import select

    from app.models.group import Group

    resp = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Auto Group Store"}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    tenant_id = resp.json()["id"]

    # Exactly one group whose headquarters is this tenant.
    groups = (
        await db_session.execute(
            select(Group).where(Group.headquarters_tenant_id == tenant_id)
        )
    ).scalars().all()
    assert len(groups) == 1, f"expected 1 self-group, got {len(groups)}"
    assert groups[0].name == "Auto Group Store"


@pytest.mark.asyncio
async def test_create_tenant_auto_attaches_tenant_to_self_group(
    super_admin_client, db_session
):
    """AC7: the new tenant is attached (GroupTenant row) to its self-group.

    This is what makes ``GroupRepository.list_for_tenant`` resolve the tenant →
    its group, which the check() knowledge bypass relies on.
    """
    from sqlalchemy import select

    from app.models.group import Group, GroupTenant

    resp = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Attach Store"}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    tenant_id = resp.json()["id"]

    group = (
        await db_session.execute(
            select(Group).where(Group.headquarters_tenant_id == tenant_id)
        )
    ).scalar_one()
    links = (
        await db_session.execute(
            select(GroupTenant).where(GroupTenant.tenant_id == tenant_id)
        )
    ).scalars().all()
    assert len(links) == 1
    assert links[0].group_id == group.id


@pytest.mark.asyncio
async def test_create_tenant_auto_group_is_unique_per_tenant(
    super_admin_client, db_session
):
    """AC7 boundary: two different tenants get two different self-groups
    (the D8 1:1 collapse is not violated by the automation — each tenant is
    the sole member of its own group)."""
    from sqlalchemy import select

    from app.models.group import Group

    r1 = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Store One"}, headers=AUTH
    )
    r2 = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Store Two"}, headers=AUTH
    )
    assert r1.status_code == 201 and r2.status_code == 201

    groups = (
        await db_session.execute(select(Group).order_by(Group.created_at))
    ).scalars().all()
    # Each tenant's headquarters pointer is distinct — no two tenants share a
    # self-group HQ, and each tenant appears in exactly one GroupTenant.
    hq_ids = [g.headquarters_tenant_id for g in groups if g.headquarters_tenant_id]
    assert len(set(hq_ids)) == len(hq_ids), (
        "auto-grouping must not collapse two tenants into one group's HQ"
    )


@pytest.mark.asyncio
async def test_create_tenant_step7_failure_rolls_back_whole_tenant(
    db_session, test_env, monkeypatch
):
    """AC8: if step 7 (auto-grouping) fails, the entire create_tenant rolls
    back — no orphan tenant (or wallet, or membership) is left behind.

    Drives ``TenantService.create_tenant`` directly (not via HTTP) and injects
    a failure into ``GroupTenantRepository.attach`` — the last write of step 7.
    The raise propagates before the single ``commit()``, and because all seven
    steps share one session, SQLAlchemy rolls back steps 1-6 too. We then
    assert the tenant/group/group_tenant rows never landed.

    The global casbin enforcer is patched to the file-backed test enforcer
    (mirroring ``_build_client``) so step 5's ``seed_tenant_defaults`` writes
    policies to the temp file instead of needing a ``casbin_rule`` table that
    ``create_all`` doesn't build.
    """
    from unittest.mock import patch

    from sqlalchemy import select

    from app.core import casbin_enforcer as casbin_mod
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant
    from app.repositories import group as group_repo_mod
    from app.schemas.tenant import TenantCreate
    from app.services.tenant_service import TenantService

    async def _boom(self, group_id, tenant_id):  # noqa: ANN001
        raise RuntimeError("simulated step-7 failure")

    monkeypatch.setattr(group_repo_mod.GroupTenantRepository, "attach", _boom)

    svc = TenantService(db_session)
    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        with pytest.raises(RuntimeError, match="simulated step-7 failure"):
            await svc.create_tenant("u-rollback", TenantCreate(name="Rollback Store"))
    # create_tenant's commit never ran; expunge any uncommitted adds from steps
    # 1-6 so the audit queries see a clean state.
    await db_session.rollback()

    # AC8: nothing committed — tenant, group, and group_tenant all absent.
    assert (
        await db_session.execute(
            select(Tenant).where(Tenant.name == "Rollback Store")
        )
    ).scalars().all() == []
    assert (
        await db_session.execute(select(Group).where(Group.name == "Rollback Store"))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(GroupTenant))
    ).scalars().all() == []


# ===========================================================================
# Slice 03 — integration verification + feature wrap-up
# (plan-knowledge-tiered-foundation.md §切片 03, the closing slice)
#
# Four end-to-end integration tests confirm slices 01+02 cooperate: the data
# model (schema) and the permission derivation (service logic) work together
# through the real create_tenant pipeline and the manual chain-building path.
# No source change is expected unless these expose a bug (plan §切片 03).
#
# - I1. full pipeline (AC1) — create_tenant (auto-group) → is_group_admin=True
#   → check(knowledge) allows → check(devices) denies. One assertion chain per
#   the three behaviors the foundation must exhibit end to end.
# - I2. cross-group isolation (AC2) — group_admin of chain A is NOT group_admin
#   of chain B (the derivation is group-scoped, not global).
# - I3. manual chain (AC3) — a hand-built chain (HQ store + branch store under
#   one group) yields group_admin only for the HQ store's owner/admin; the
#   branch store's owner does NOT derive group_admin.
# - I4. distribution reference semantics (AC4) — a distribution row links a
#   source doc to a target tenant; soft-deleting the source doc leaves the row
#   in place (audit intact) but the row is_active=True is no longer "effective"
#   because the source is gone. This slice only asserts the relation-table
#   semantics; Feature B implements the actual list/retrieve filtering.
# ===========================================================================


@pytest.mark.asyncio
async def test_integration_full_pipeline_auto_group_to_check_bypass(
    super_admin_client, db_session
):
    """AC1: end-to-end — create_tenant auto-builds the self-group, the HQ owner
    derives group_admin, and ``check()`` lets them act on knowledge but not on
    devices.

    This is the single test that ties slice 01 (Group.headquarters_tenant_id +
    GroupTenant 1:1) to slice 02 (step-7 automation + is_group_admin + check
    bypass): the auto-grouped tenant produced by the real HTTP pipeline is
    exactly the shape the bypass expects, so the whole foundation composes.

    The HQ owner is seeded via ``_seed_user_role`` rather than read from
    ``create_tenant``'s own ``assign_role`` output: the caller of the HTTP
    pipeline here is super_admin, which ``check()`` short-circuits before the
    group_admin bypass branch can run. To exercise the bypass we need a *plain*
    HQ-tenant owner, so the membership is added explicitly — this targets the
    SCD2-read path of ``is_group_admin`` (``current_role`` over a ``valid_to IS
    NULL`` row) the same way ``_seed_user_role`` does for the unit tests.
    """
    from sqlalchemy import select

    from app.models.group import Group, GroupTenant
    from app.services.permission_service import is_group_admin, permission_service

    # 1) Real create_tenant pipeline — step 7 auto-builds the self-group.
    resp = await super_admin_client.post(
        "/api/v1/tenants/", json={"name": "Integration HQ"}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    tenant_id = resp.json()["id"]

    # The auto-group has its headquarters pointing back at this tenant.
    group = (
        await db_session.execute(
            select(Group).where(Group.headquarters_tenant_id == tenant_id)
        )
    ).scalar_one()

    # 2) Seed a plain HQ-tenant owner (SCD2 active row) for the bypass target.
    await _seed_user_role(
        db_session, user_id="u-int-owner", tenant_id=tenant_id, role="owner"
    )
    await db_session.commit()

    # 3) is_group_admin derives True for the HQ owner on this group.
    assert await is_group_admin(db_session, "u-int-owner", group.id) is True

    # 4) check() bypass lets the HQ owner through on knowledge, not on devices.
    assert (
        await permission_service.check(
            "u-int-owner", tenant_id, "knowledge", "create", db=db_session
        )
        is True
    )
    assert (
        await permission_service.check(
            "u-int-owner", tenant_id, "devices", "create", db=db_session
        )
        is False
    )

    # Sanity: the auto-group attached the tenant (the bypass's reverse lookup
    # depends on this GroupTenant row existing).
    links = (
        await db_session.execute(
            select(GroupTenant).where(GroupTenant.tenant_id == tenant_id)
        )
    ).scalars().all()
    assert len(links) == 1 and links[0].group_id == group.id


@pytest.mark.asyncio
async def test_integration_cross_group_isolation(db_session):
    """AC2: a group_admin of chain A is NOT a group_admin of chain B.

    Builds two fully-independent chains (each a self-grouped HQ tenant) and
    asserts the owner of A's HQ derives group_admin only on A's group — the
    derivation keys off group.headquarters_tenant_id, so cross-chain elevation
    must never happen. Mirrors the D1 cross-group isolation edge rule.
    """
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin, permission_service

    # Chain A — HQ tenant that is the headquarters of group A.
    hq_a = Tenant(id=_uuid("tnt"), name="HQ A")
    hq_b = Tenant(id=_uuid("tnt"), name="HQ B")
    db_session.add_all([hq_a, hq_b])
    await db_session.flush()
    group_a = Group(name="Chain A", headquarters_tenant_id=hq_a.id)
    group_b = Group(name="Chain B", headquarters_tenant_id=hq_b.id)
    db_session.add_all([group_a, group_b])
    await db_session.flush()
    db_session.add_all(
        [
            GroupTenant(group_id=group_a.id, tenant_id=hq_a.id),
            GroupTenant(group_id=group_b.id, tenant_id=hq_b.id),
        ]
    )
    # Owner of A's HQ only — no membership on B.
    await _seed_user_role(
        db_session, user_id="u-a-owner", tenant_id=hq_a.id, role="owner"
    )
    await db_session.commit()

    # Positive: A's owner is group_admin of A.
    assert await is_group_admin(db_session, "u-a-owner", group_a.id) is True
    # Negative: A's owner is NOT group_admin of B.
    assert await is_group_admin(db_session, "u-a-owner", group_b.id) is False

    # And the bypass reflects this: acting on A's tenant, knowledge is allowed;
    # acting on B's tenant (where the user has no membership at all), it is not.
    assert (
        await permission_service.check(
            "u-a-owner", hq_a.id, "knowledge", "create", db=db_session
        )
        is True
    )
    assert (
        await permission_service.check(
            "u-a-owner", hq_b.id, "knowledge", "create", db=db_session
        )
        is False
    )


@pytest.mark.asyncio
async def test_integration_manual_chain_only_hq_owner_is_group_admin(db_session):
    """AC3: a hand-built chain (HQ store + branch store under one group) grants
    group_admin only to the HQ store's owner/admin — the branch store's owner
    does NOT derive it.

    ``GroupService.create`` does not accept ``headquarters_tenant_id`` (the
    schema has no such field), so a multi-tenant chain is wired directly via ORM
    rows: one Group whose headquarters is the HQ tenant, with both the HQ and a
    branch tenant attached. This is the realistic "chain with branches" shape
    that the single-store automation generalizes to once a group grows.

    Known gap (not this slice's scope): a group created via the production
    ``GroupService.create`` API lands with ``headquarters_tenant_id=None``, so
    nobody would derive group_admin from it. Giving the create-group API a way
    to set the headquarters pointer is Feature B's territory (the chain-building
    UX lives there); this foundation slice only verifies the derivation logic on
    the shape such a chain will eventually have.
    """
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant
    from app.services.permission_service import is_group_admin

    hq = Tenant(id=_uuid("tnt"), name="Chain HQ")
    branch = Tenant(id=_uuid("tnt"), name="Branch 1")
    db_session.add_all([hq, branch])
    await db_session.flush()

    # The chain group: headquarters is the HQ tenant (not the branch).
    chain = Group(name="Manual Chain", headquarters_tenant_id=hq.id)
    db_session.add(chain)
    await db_session.flush()
    db_session.add_all(
        [
            GroupTenant(group_id=chain.id, tenant_id=hq.id),
            GroupTenant(group_id=chain.id, tenant_id=branch.id),
        ]
    )
    # HQ owner and branch owner — both "owners" but only the HQ one derives.
    await _seed_user_role(
        db_session, user_id="u-hq-owner", tenant_id=hq.id, role="owner"
    )
    await _seed_user_role(
        db_session, user_id="u-branch-owner", tenant_id=branch.id, role="owner"
    )
    await db_session.commit()

    # HQ owner IS the group_admin (derives from headquarters_tenant_id = hq).
    assert await is_group_admin(db_session, "u-hq-owner", chain.id) is True
    # Branch owner is NOT — being a branch owner does not make one a chain admin.
    assert await is_group_admin(db_session, "u-branch-owner", chain.id) is False


@pytest.mark.asyncio
async def test_integration_distribution_reference_semantics(db_session):
    """AC4: knowledge_distribution is a reference-model link (D4) — it points at
    a source doc + target tenant, not a copy.

    Two relation-table invariants this slice pins down (the *actual*
    list/retrieve filtering — the ``is_active=True AND doc.is_deleted=False``
    combined predicate — lands in Feature B; this test deliberately does NOT
    encode that query, to avoid pinning Feature B's list semantics here):

      1. A live distribution row (is_active=True) links doc↔target.
      2. The audit row survives a source soft-delete — ``is_active`` is NOT
         auto-flipped (the revoke is an explicit Feature B write, kept separate
         from the source's own lifecycle so the audit trail stays intact).
    """
    from sqlalchemy import select

    from app.models.document import Document
    from app.models.group import GroupTenant  # noqa: F401  (register for create_all)
    from app.models.knowledge_distribution import KnowledgeDistribution
    from app.models.tenant import Tenant

    src_tenant = Tenant(id=_uuid("tnt"), name="Source Tenant")
    target = Tenant(id=_uuid("tnt"), name="Target Store")
    db_session.add_all([src_tenant, target])
    await db_session.flush()

    doc = Document(
        id=_uuid("doc"),
        tenant_id=src_tenant.id,
        name="HQ Product Manual",
        scope="platform",
    )
    db_session.add(doc)
    await db_session.flush()

    dist = KnowledgeDistribution(
        source_doc_id=doc.id, target_tenant_id=target.id, distributed_by=None
    )
    db_session.add(dist)
    await db_session.commit()

    # 1) Live distribution: the row is active and resolves back to the doc.
    live = (
        await db_session.execute(
            select(KnowledgeDistribution).where(
                KnowledgeDistribution.target_tenant_id == target.id
            )
        )
    ).scalar_one()
    assert live.is_active is True
    assert live.source_doc_id == doc.id

    # 2) Soft-delete the source — the audit row stays (is_active unchanged).
    #    The revoke is an explicit Feature B write (is_active=False); this
    #    foundation asserts the source's own soft-delete does NOT silently flip
    #    the distribution row, so the audit trail is preserved.
    doc.is_deleted = True
    await db_session.commit()
    retained = (
        await db_session.execute(
            select(KnowledgeDistribution).where(
                KnowledgeDistribution.source_doc_id == doc.id
            )
        )
    ).scalar_one()
    assert retained.is_active is True, (
        "soft-deleting the source must not auto-flip the distribution row; the "
        "revoke is an explicit Feature B write that keeps the audit trail intact"
    )
