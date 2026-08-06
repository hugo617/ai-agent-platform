"""add knowledge-tiered foundation (scope/category/distribution + HQ pointer)

Revision ID: 05fa069297cc
Revises: aa7a88a8e643
Create Date: 2026-08-06 10:00:00.000000+00:00

knowledge-tiered-foundation slice 01 — the schema ground for the 3-level
knowledge permissions (plan: harness/docs/plan-knowledge-tiered-foundation.md).
One cohesive migration, atomic by design (E3): the tiered ground either lands
whole or rolls back whole. Six changes, ordered to satisfy FK dependencies:

1. **group_tenants M2M-collapse pre-check (E7, AC9).** Before adding the
   tenant_id unique index, scan for any tenant attached to >1 group. If dirty
   data exists the migration refuses to proceed (a tenant must belong to at
   most one group, D8). Refusing over silently de-duping keeps the data-safe
   choice. Detection is a plain Python COUNT over the live bind so it works on
   both PG and SQLite (SQL RAISE syntax differs).

2. **knowledge_categories table (AC4).** Built first because documents gains a
   FK to it. Tiered by scope (platform/group/store); partial unique index on
   (scope, name, group_id, tenant_id) among live rows (mirrors User/Group).

3. **groups.headquarters_tenant_id (AC1, E1).** Nullable FK tenants. Nullable
   so chain groups can predate their HQ store and so pre-existing groups
   migrate cleanly (the column lands NULL until an HQ is designated).

4. **documents scope/group_id/category_id (AC3, E4, AC8).** scope is NOT NULL
   with server_default 'store' so ADD COLUMN back-fills existing rows on both
   PG and SQLite; a defensive UPDATE ... WHERE scope IS NULL is belt-and-braces
   (mirrors composite-chat conversations.kind). group_id/category_id are
   nullable FKs (ondelete SET NULL).

5. **group_tenants tenant_id unique index (AC2).** Enforces the 1:1 collapse
   the pre-check guarded against. SQLite's ALTER limitations don't apply (an
   index is independent of the table shape), so a plain create_index works on
   both backends.

6. **knowledge_distribution table (AC5).** Reference-model link (D4): source
   doc → target store, never a copy. UniqueConstraint(source_doc_id,
   target_tenant_id) so re-distributing re-enables the existing row (Feature B
   upsert). is_active default True; revoke is a soft flip, not a hard delete.

7. **Seed 5 platform Categories (AC7, D5).** 产品手册 / FAQ / 话术脚本 /
   服务规范 / 促销文案 — the standard business vocabulary. Idempotent: each
   INSERT is guarded by WHERE NOT EXISTS so re-running after a partial upgrade
   or a hand-seeded deploy doesn't duplicate (mirrors booking_configs seed).

All new tables are pure-scalar columns (String/Integer/Boolean/DateTime) so PG
and SQLite accept the same migration and ``alembic check`` does not drift on
either backend. Partial unique indexes use the dual ``postgresql_where`` /
``sqlite_where`` form (mirrors uq_groups_code_active / uq_user_tenants_active).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "05fa069297cc"
down_revision: str | Sequence[str] | None = "aa7a88a8e643"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The 5 platform-wide Categories every tenant starts with (knowledge-tiered D5).
# Ids are stable strings so Feature B's "list visible Categories" can reference
# them deterministically and so re-seeds are idempotent by id, not just by name.
_PLATFORM_CATEGORIES = [
    ("cat-platform-product-manual", "产品手册", 10),
    ("cat-platform-faq", "FAQ", 20),
    ("cat-platform-sales-script", "话术脚本", 30),
    ("cat-platform-service-standard", "服务规范", 40),
    ("cat-platform-promo-copy", "促销文案", 50),
]


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1) group_tenants M2M-collapse pre-check (E7). Refuse to proceed if any
    #    tenant is attached to more than one group — D8 requires 1:1.
    # ------------------------------------------------------------------
    dirty = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM ("
        "  SELECT tenant_id FROM group_tenants GROUP BY tenant_id HAVING COUNT(*) > 1"
        ") AS _dup"
    ).scalar()
    if dirty:
        raise RuntimeError(
            "Refusing to add the tenant_id unique index: found %d tenant(s) "
            "attached to more than one group. knowledge-tiered requires a "
            "tenant to belong to at most one group (D8). Detach the extra "
            "group_tenants rows before re-running this migration." % dirty
        )

    # ------------------------------------------------------------------
    # 2) knowledge_categories table (built first; documents references it).
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_categories",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column(
            "group_id",
            sa.String(length=32),
            sa.ForeignKey("groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=32),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_categories_scope", "knowledge_categories", ["scope"]
    )
    op.create_index(
        "ix_knowledge_categories_is_deleted",
        "knowledge_categories",
        ["is_deleted"],
    )
    op.create_index(
        "uq_knowledge_categories_scope_name_active",
        "knowledge_categories",
        ["scope", "name", "group_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )

    # ------------------------------------------------------------------
    # 3) groups.headquarters_tenant_id (nullable FK tenants).
    # ------------------------------------------------------------------
    op.add_column(
        "groups",
        sa.Column(
            "headquarters_tenant_id",
            sa.String(length=32),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 4) documents: scope (NOT NULL default 'store') + group_id + category_id.
    #    ADD COLUMN with NOT NULL + server_default back-fills existing rows on
    #    both PG and SQLite; the UPDATE is defensive belt-and-braces (E4).
    # ------------------------------------------------------------------
    op.add_column(
        "documents",
        sa.Column(
            "scope",
            sa.String(length=20),
            nullable=False,
            server_default="store",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "group_id",
            sa.String(length=32),
            sa.ForeignKey("groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "category_id",
            sa.String(length=32),
            sa.ForeignKey("knowledge_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute("UPDATE documents SET scope='store' WHERE scope IS NULL")

    # ------------------------------------------------------------------
    # 5) group_tenants tenant_id unique index — enforces the 1:1 collapse the
    #    pre-check guarded. The prior non-unique index (idx_group_tenants_
    #    tenant_id, from migration 574391d912fc) is now subsumed by this unique
    #    one, so DROP it first to keep alembic check drift-free (mirrors the
    #    drop-then-create pattern in ce505ae8a1bd for users' username/email
    #    indexes). A plain index op (no ALTER of the table shape) works on both
    #    PG and SQLite without batch mode.
    # ------------------------------------------------------------------
    op.drop_index("idx_group_tenants_tenant_id", table_name="group_tenants")
    op.create_index(
        "uq_group_tenants_tenant_id",
        "group_tenants",
        ["tenant_id"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # 6) knowledge_distribution table (reference model, D4).
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_distribution",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "source_doc_id",
            sa.String(length=32),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_tenant_id",
            sa.String(length=32),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "distributed_by",
            sa.String(length=32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "distributed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_doc_id", "target_tenant_id", name="uq_knowledge_distribution"
        ),
    )
    op.create_index(
        "ix_knowledge_distribution_target_tenant_id",
        "knowledge_distribution",
        ["target_tenant_id"],
    )

    # ------------------------------------------------------------------
    # 7) Seed 5 platform Categories (D5). Idempotent per-row via
    #    WHERE NOT EXISTS (mirrors booking_configs seed).
    # ------------------------------------------------------------------
    for cat_id, name, sort_order in _PLATFORM_CATEGORIES:
        op.execute(
            "INSERT INTO knowledge_categories "
            "(id, name, scope, group_id, tenant_id, sort_order, is_deleted) "
            f"SELECT '{cat_id}', '{name}', 'platform', NULL, NULL, {sort_order}, false "
            "WHERE NOT EXISTS ("
            f"SELECT 1 FROM knowledge_categories WHERE id = '{cat_id}'"
            ")"
        )


def downgrade() -> None:
    # Reverse order of upgrade (drop FK children before parents).
    op.drop_index(
        "ix_knowledge_distribution_target_tenant_id", table_name="knowledge_distribution"
    )
    op.drop_table("knowledge_distribution")

    op.drop_index("uq_group_tenants_tenant_id", table_name="group_tenants")
    # Restore the non-unique tenant_id index that upgrade dropped (was created
    # by migration 574391d912fc; symmetric rollback).
    op.create_index(
        "idx_group_tenants_tenant_id", "group_tenants", ["tenant_id"], unique=False
    )

    op.drop_column("documents", "category_id")
    op.drop_column("documents", "group_id")
    op.drop_column("documents", "scope")

    op.drop_column("groups", "headquarters_tenant_id")

    op.drop_index(
        "uq_knowledge_categories_scope_name_active", table_name="knowledge_categories"
    )
    op.drop_index(
        "ix_knowledge_categories_is_deleted", table_name="knowledge_categories"
    )
    op.drop_index("ix_knowledge_categories_scope", table_name="knowledge_categories")
    op.drop_table("knowledge_categories")
