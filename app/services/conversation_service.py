"""Conversation + message service."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Conversation
from app.models.message import Message
from app.repositories.conversation import ConversationRepository, MessageRepository
from app.schemas.conversation import ConversationRead, ConversationStatistics, MessageRead
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
        customer_id: str | None = None,
    ) -> Conversation:
        """Return an existing conversation or create a new one (after permission check).

        When creating a new conversation with no explicit ``title``, derive one
        from ``first_message`` (the first user turn) by taking its first 20
        chars + ellipsis. This keeps the conversation list legible without a
        separate title-generation step. Matches the frontend's
        ``conversationLabel`` snippet length.

        ``customer_id`` only applies when creating a NEW conversation — reusing
        an existing one (via ``conversation_id``) keeps its original attribution
        intact, so a follow-up turn never silently re-binds the chat to a
        different customer. Token 费用管理系列 3/4.
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
            customer_id=customer_id,
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

    async def statistics(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> ConversationStatistics:
        """Conversation counts (total + 7d/30d windows) for the dashboard card.

        Store users are scoped to their tenant; super_admin aggregates across
        every tenant. Windows are on ``created_at`` (when the chat started).
        """
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(
                user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
            )
        now = datetime.now(UTC)
        since_7d = now - timedelta(days=7)
        since_30d = now - timedelta(days=30)
        if is_super_admin:
            total = await self.conversations.count_all()
            last_7d = await self.conversations.count_all(since=since_7d)
            last_30d = await self.conversations.count_all(since=since_30d)
        else:
            total = await self.conversations.count_for_tenant(tenant_id)
            last_7d = await self.conversations.count_for_tenant(tenant_id, since=since_7d)
            last_30d = await self.conversations.count_for_tenant(tenant_id, since=since_30d)
        return ConversationStatistics(total=total, last_7d=last_7d, last_30d=last_30d)

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
        self,
        tenant_id: str,
        conversation_id: str,
        role: str,
        content: str,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        model: str | None = None,
    ) -> Message:
        """Append a message and optionally record its token usage.

        The token/model kwargs are only meaningful for assistant messages
        produced by an LLM call; user messages and older callers that don't
        pass them simply leave the columns NULL (backward compatible).
        """
        msg = Message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
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
