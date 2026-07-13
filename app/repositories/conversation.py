"""Conversation + message repositories (tenant-scoped)."""

from datetime import datetime

from sqlalchemy import func, select

from app.models.agent import Conversation
from app.models.message import Message
from app.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation

    async def list_for_user(self, tenant_id: str, user_id: str, limit: int = 50) -> list[Conversation]:
        # Order by most-recently-active so a conversation with a new message
        # bubbles to the top of the user's list.
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_customer(
        self, tenant_id: str, customer_id: str, limit: int = 100
    ) -> list[Conversation]:
        """Conversations attributed to a customer in a tenant (customer 360).

        Token 费用管理系列 3/4: lets the customer detail show the chats where
        a staff member served them.
        """
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.customer_id == customer_id,
            )
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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
