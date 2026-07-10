"""Conversation + message service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Conversation
from app.models.message import Message
from app.repositories.conversation import ConversationRepository, MessageRepository
from app.schemas.conversation import ConversationRead, MessageRead
from app.services.errors import NotFoundError
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
                raise NotFoundError(
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
        # Bump the conversation's updated_at so the list ordering reflects
        # recent activity. Refresh from the loaded conversation (if available
        # in this session) to keep onupdate in sync.
        conv = await self.conversations.get_for_tenant(conversation_id, tenant_id)
        if conv is not None:
            conv.updated_at = msg.created_at
        await self.db.commit()
        return msg

    async def delete(
        self, user_id: str, tenant_id: str, conversation_id: str
    ) -> None:
        """Hard-delete a conversation owned by the caller.

        Conversations are private per-user: even within the same tenant, only
        the owner may delete theirs. (Messages cascade via the FK ondelete.)
        """
        await permission_service.require(user_id, tenant_id, self.OBJECT, "delete")
        conv = await self.conversations.get_for_tenant(conversation_id, tenant_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError(
                f"conversation {conversation_id} not found in tenant {tenant_id}"
            )
        await self.conversations.delete(conv)
        await self.db.commit()
