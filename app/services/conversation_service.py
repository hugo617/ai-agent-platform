"""Conversation + message service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Conversation
from app.models.message import Message
from app.repositories.conversation import ConversationRepository, MessageRepository
from app.schemas.conversation import ConversationRead, MessageRead
from app.services.permission_service import permission_service


class ConversationService:
    OBJECT = "conversations"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.conversations = ConversationRepository(db)
        self.messages = MessageRepository(db)

    async def create_or_get(
        self,
        user_id: str,
        tenant_id: str,
        agent_id: str,
        title: str | None = None,
        conversation_id: str | None = None,
    ) -> Conversation:
        """Return an existing conversation or create a new one (after permission check)."""
        await permission_service.require(user_id, tenant_id, self.OBJECT, "create")

        if conversation_id:
            conv = await self.conversations.get_for_tenant(conversation_id, tenant_id)
            if conv is None:
                raise ValueError(
                    f"conversation {conversation_id} not found in tenant {tenant_id}"
                )
            return conv

        conv = Conversation(
            tenant_id=tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            title=title,
        )
        await self.conversations.add(conv)
        await self.db.commit()
        return conv

    async def list_for_user(
        self, user_id: str, tenant_id: str
    ) -> list[ConversationRead]:
        await permission_service.require(user_id, tenant_id, self.OBJECT, "read")
        convs = await self.conversations.list_for_user(tenant_id, user_id)
        return [ConversationRead.model_validate(c) for c in convs]

    async def history(
        self, user_id: str, tenant_id: str, conversation_id: str
    ) -> list[MessageRead]:
        await permission_service.require(user_id, tenant_id, self.OBJECT, "read")
        msgs = await self.messages.list_for_conversation(conversation_id, tenant_id)
        return [MessageRead.model_validate(m) for m in msgs]

    async def append_message(
        self, tenant_id: str, conversation_id: str, role: str, content: str
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
        )
        await self.messages.add(msg)
        await self.db.commit()
        return msg
