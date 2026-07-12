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
        platform_role: str | None = None,
        first_message: str | None = None,
    ) -> Conversation:
        """Return an existing conversation or create a new one (after permission check).

        When creating a new conversation with no explicit ``title``, derive one
        from ``first_message`` (the first user turn) by taking its first 20
        chars + ellipsis. This keeps the conversation list legible without a
        separate title-generation step. Matches the frontend's
        ``conversationLabel`` snippet length.
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "create", platform_role=platform_role
        )

        if conversation_id:
            conv = await self.conversations.get_for_tenant(conversation_id, tenant_id)
            if conv is None:
                raise NotFoundError(
                    f"conversation {conversation_id} not found in tenant {tenant_id}"
                )
            return conv

        derived_title = title
        if derived_title is None and first_message:
            text = first_message.strip()
            snippet = text[:20]
            derived_title = f"{snippet}…" if len(snippet) < len(text) else snippet

        conv = Conversation(
            tenant_id=tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            title=derived_title,
        )
        await self.conversations.add(conv)
        await self.db.commit()
        return conv

    async def list_for_user(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[ConversationRead]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        convs = await self.conversations.list_for_user(tenant_id, user_id)
        return [ConversationRead.model_validate(c) for c in convs]

    async def history(
        self,
        user_id: str,
        tenant_id: str,
        conversation_id: str,
        platform_role: str | None = None,
    ) -> list[MessageRead]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
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
        self,
        user_id: str,
        tenant_id: str,
        conversation_id: str,
        platform_role: str | None = None,
    ) -> None:
        """Hard-delete a conversation owned by the caller.

        Conversations are private per-user: even within the same tenant, only
        the owner may delete theirs. (Messages cascade via the FK ondelete.)
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "delete", platform_role=platform_role
        )
        conv = await self.conversations.get_for_tenant(conversation_id, tenant_id)
        if conv is None or conv.user_id != user_id:
            raise NotFoundError(
                f"conversation {conversation_id} not found in tenant {tenant_id}"
            )
        await self.conversations.delete(conv)
        await self.db.commit()
