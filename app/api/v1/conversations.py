"""Conversation history endpoints — list, view messages, delete.

These complement the SSE streaming chat (``app/api/v1/chat.py``). The chat
endpoint creates conversations + persists messages; these endpoints let the
client browse and manage that history. All operations are tenant-scoped and
guarded by casbin (``conversations`` object), and history is additionally
private per-user (only the owner sees/deletes their conversations).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.conversation import ConversationRead, MessageRead
from app.services.conversation_service import ConversationService
from app.services.errors import NotFoundError

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _http_exc(e: ValueError) -> HTTPException:
    """Map a service ValueError to the right HTTP status by exception type."""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/",
    response_model=list[ConversationRead],
    dependencies=[Depends(require_permission("conversations", "read"))],
)
async def list_conversations(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationRead]:
    """List the caller's conversations, most-recently-active first."""
    service = ConversationService(db)
    return await service.list_for_user(user.user_id, user.tenant_id)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageRead],
    dependencies=[Depends(require_permission("conversations", "read"))],
)
async def list_messages(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageRead]:
    """List the messages in a conversation (oldest first)."""
    service = ConversationService(db)
    return await service.history(user.user_id, user.tenant_id, conversation_id)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("conversations", "delete"))],
)
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a conversation (hard delete; messages cascade)."""
    service = ConversationService(db)
    try:
        await service.delete(user.user_id, user.tenant_id, conversation_id)
    except ValueError as e:
        raise _http_exc(e) from e
