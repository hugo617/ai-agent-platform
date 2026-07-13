"""Conversation + message repositories (tenant-scoped)."""

from sqlalchemy import select

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
