"""Conversation + message repositories (tenant-scoped)."""

from sqlalchemy import select

from app.models.agent import Conversation
from app.models.message import Message
from app.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation

    async def list_for_user(self, tenant_id: str, user_id: str, limit: int = 50) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class MessageRepository(TenantScopedRepository[Message]):
    model = Message

    async def list_for_conversation(self, conversation_id: str, tenant_id: str) -> list[Message]:
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
