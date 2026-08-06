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
