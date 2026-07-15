"""Conversation + message repositories (tenant-scoped)."""

from datetime import datetime

from sqlalchemy import func, or_, select

from app.models.agent import Conversation
from app.models.message import Message
from app.repositories.base import TenantScopedRepository


def _tags_contain(tags_col, tag: str, dialect_name: str):
    """Build a "tags JSON array contains ``tag``" predicate for either dialect.

    Postgres JSONB supports the ``@>`` containment operator (``tags @> ['x']``),
    which is indexable by a future GIN index. SQLite has no ``@>``: we use the
    JSON1 ``json_each`` table-valued function (``EXISTS (SELECT 1 FROM
    json_each(tags) WHERE value = :tag)``), which the in-memory test suite
    relies on. The returned element is a boolean SQL expression.
    """
    if dialect_name == "postgresql":
        return tags_col.contains([tag])
    # SQLite (tests) — EXISTS over json_each.
    je = func.json_each(tags_col).table_valued("value")
    return select(1).select_from(je).where(je.c.value == tag).exists()


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation

    async def list_for_user(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 50,
        *,
        search: str | None = None,
        tag: str | None = None,
    ) -> list[Conversation]:
        """List a user's conversations, most-recently-active first.

        conversation-management (priority 50) optional filters:

        - ``search``: case-insensitive substring against the title OR any message
          content (a subquery over messages joined by conversation_id). Empty/
          None search is a no-op (matches all).
        - ``tag``: conversations whose ``tags`` JSON array contains the tag
          (``@> ['x']`` on Postgres JSONB, ``json_each`` on SQLite tests).

        Ordering is pinned-first (``is_pinned DESC``) then ``updated_at DESC``
        so important chats stay on top of the recency list.
        """
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
            .limit(limit)
        )
        if search:
            like = f"%{search}%"
            # Subquery over messages: any message in this conversation whose
            # content matches the search term. Combined with the title ILIKE via
            # OR so a chat matches if either its title or any message hits.
            msg_subq = (
                select(Message.conversation_id)
                .where(Message.content.ilike(like))
                .scalar_subquery()
            )
            stmt = stmt.where(
                or_(
                    Conversation.title.ilike(like),
                    Conversation.id.in_(msg_subq),
                )
            )
        if tag:
            stmt = stmt.where(
                _tags_contain(Conversation.tags, tag, self.db.bind.dialect.name)
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_all(self, *, keyword: str, limit: int = 5) -> list[Conversation]:
        """Cross-tenant title search (super_admin global search aggregator).

        Ignores ``tenant_id`` and ``user_id`` — super_admin runs across the
        whole platform in the overview endpoints, so the global search mirrors
        that scope. Matches the title only (not message content) to keep the
        aggregator query cheap; the per-user ``list_for_user`` already does the
        full title+message search for the chat page.
        """
        like = f"%{keyword}%"
        stmt = (
            select(Conversation)
            .where(Conversation.title.ilike(like))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def count_for_tenant(
        self, tenant_id: str, since: datetime | None = None
    ) -> int:
        """Conversation count for a tenant, optionally bounded by ``since``.

        ``since=None`` → all-time total; ``since=<N days ago>`` → last_N_d count.
        Used by the dashboard conversation stat card.
        """
        stmt = select(func.count()).select_from(Conversation).where(
            Conversation.tenant_id == tenant_id
        )
        if since is not None:
            stmt = stmt.where(Conversation.created_at >= since)
        return int((await self.db.execute(stmt)).scalar_one())

    async def count_all(self, since: datetime | None = None) -> int:
        """Conversation count across every tenant (super_admin overview)."""
        stmt = select(func.count()).select_from(Conversation)
        if since is not None:
            stmt = stmt.where(Conversation.created_at >= since)
        return int((await self.db.execute(stmt)).scalar_one())

    async def daily_trend_for_tenant(
        self, tenant_id: str, since: datetime
    ) -> list[tuple[str, int, int]]:
        """Daily (conversations_created, messages_sent) for a tenant since ``since``.

        Returns ``[(date_iso, conv_count, msg_count), ...]`` ordered oldest →
        newest. Days with zero activity are filled by the service so the chart
        stays a continuous timeline. ``func.date()`` works on both SQLite and
        Postgres (casts the timestamptz to a calendar date for grouping).
        """
        conv_stmt = (
            select(
                func.date(Conversation.created_at).label("d"),
                func.count().label("c"),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.created_at >= since,
            )
            .group_by("d")
            .order_by("d")
        )
        conv_rows = {str(r.d): int(r.c) for r in (await self.db.execute(conv_stmt)).all()}

        msg_stmt = (
            select(
                func.date(Message.created_at).label("d"),
                func.count().label("c"),
            )
            .where(
                Message.tenant_id == tenant_id,
                Message.created_at >= since,
            )
            .group_by("d")
            .order_by("d")
        )
        msg_rows = {str(r.d): int(r.c) for r in (await self.db.execute(msg_stmt)).all()}

        days = sorted(set(conv_rows) | set(msg_rows))
        return [(d, conv_rows.get(d, 0), msg_rows.get(d, 0)) for d in days]

    async def daily_trend_all(
        self, since: datetime
    ) -> list[tuple[str, int, int]]:
        """Daily (conversations_created, messages_sent) across all tenants
        (super_admin aggregate). Same shape as ``daily_trend_for_tenant``."""
        conv_stmt = (
            select(
                func.date(Conversation.created_at).label("d"),
                func.count().label("c"),
            )
            .where(Conversation.created_at >= since)
            .group_by("d")
            .order_by("d")
        )
        conv_rows = {str(r.d): int(r.c) for r in (await self.db.execute(conv_stmt)).all()}

        msg_stmt = (
            select(
                func.date(Message.created_at).label("d"),
                func.count().label("c"),
            )
            .where(Message.created_at >= since)
            .group_by("d")
            .order_by("d")
        )
        msg_rows = {str(r.d): int(r.c) for r in (await self.db.execute(msg_stmt)).all()}

        days = sorted(set(conv_rows) | set(msg_rows))
        return [(d, conv_rows.get(d, 0), msg_rows.get(d, 0)) for d in days]

    async def conversation_count_by_tenant(
        self, since: datetime
    ) -> list[tuple[str, str, int]]:
        """Per-tenant conversation counts since ``since`` (super_admin overview).

        Returns ``[(tenant_id, tenant_name, conv_count), ...]`` ordered by
        conv_count DESC. Used for the "store activity Top N" panel.
        """
        # Lazy import avoids a circular import at module load time (the tenant
        # model is also imported by repositories that this module's siblings
        # pull in early).
        from app.models.tenant import Tenant

        stmt = (
            select(
                Conversation.tenant_id.label("tid"),
                Tenant.name.label("tname"),
                func.count().label("c"),
            )
            .join(Tenant, Tenant.id == Conversation.tenant_id)
            .where(Conversation.created_at >= since)
            .group_by(Conversation.tenant_id, Tenant.name)
            .order_by(func.count().desc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [(str(r.tid), str(r.tname) if r.tname is not None else "", int(r.c)) for r in rows]


class MessageRepository(TenantScopedRepository[Message]):
    model = Message

    async def list_for_conversation(
        self, conversation_id: str, tenant_id: str, limit: int = 200
    ) -> list[Message]:
        # ``limit`` is a defensive cap (not the truncation logic — token-based
        # truncation happens in ``token_budget.truncate_history`` before the
        # messages reach the LLM). 200 is well above any realistic single chat
        # yet stops a pathological conversation from pulling thousands of rows.
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.tenant_id == tenant_id,
            )
            .order_by(Message.created_at)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
