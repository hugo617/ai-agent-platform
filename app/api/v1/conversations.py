"""Conversation history endpoints — list, view messages, delete, manage.

These complement the SSE streaming chat (``app/api/v1/chat.py``). The chat
endpoint creates conversations + persists messages; these endpoints let the
client browse and manage that history. All operations are tenant-scoped and
guarded by casbin (``conversations`` object), and history is additionally
private per-user (only the owner sees/deletes their conversations).

conversation-management (priority 50) extends this module with search, rename,
tags, pin/star and batch-delete. Every management mutation reuses the same
ownership rule as delete: the conversation must belong to the caller.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.conversation import (
    BatchDelete,
    ConversationRead,
    ConversationStatistics,
    ConversationTitleUpdate,
    MessageRead,
    PinUpdate,
    StarUpdate,
    TagAdd,
)
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
    search: str | None = Query(
        None, description="Substring match on title OR any message content"
    ),
    tag: str | None = Query(None, description="Filter to conversations with this tag"),
) -> list[ConversationRead]:
    """List the caller's conversations, pinned-first then most-recently-active.

    Optional ``search`` matches the title (ILIKE) OR any message content; ``tag``
    filters to conversations whose ``tags`` array contains it.
    """
    service = ConversationService(db)
    return await service.list_for_user(
        user.user_id,
        user.tenant_id,
        platform_role=user.platform_role,
        search=search,
        tag=tag,
    )


@router.get(
    "/statistics",
    response_model=ConversationStatistics,
    dependencies=[Depends(require_permission("conversations", "read"))],
)
async def conversation_statistics(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationStatistics:
    """Aggregate conversation counts (total + 7d/30d) for the dashboard card.

    Store users are scoped to their tenant; super_admin aggregates across every
    tenant (the service splits on ``platform_role``).
    """
    service = ConversationService(db)
    return await service.statistics(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.post(
    "/batch-delete",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("conversations", "delete"))],
)
async def batch_delete_conversations(
    payload: BatchDelete,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Delete several of the caller's conversations at once.

    Every id must belong to the caller (same user within the tenant); a foreign
    id yields 404 instead of being silently skipped. Returns ``{"deleted": n}``.
    """
    service = ConversationService(db)
    try:
        deleted = await service.batch_delete(
            user.user_id,
            user.tenant_id,
            payload.conversation_ids,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e
    return {"deleted": deleted}


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
    return await service.history(
        user.user_id, user.tenant_id, conversation_id, platform_role=user.platform_role
    )


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
        await service.delete(
            user.user_id,
            user.tenant_id,
            conversation_id,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


# ------------------------------------- conversation-management (priority 50)
#
# Rename / tag / pin / star. All gated by ``conversations:update`` and routed
# through ``ConversationService._get_owned`` which enforces per-user ownership
# (same rule as delete). A wrong/foreign id yields 404 (no existence leak).


@router.patch(
    "/{conversation_id}/title",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversations", "update"))],
)
async def rename_conversation(
    conversation_id: str,
    payload: ConversationTitleUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """Rename a conversation owned by the caller."""
    service = ConversationService(db)
    try:
        return await service.rename(
            user.user_id,
            user.tenant_id,
            conversation_id,
            payload.title,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.post(
    "/{conversation_id}/tags",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversations", "update"))],
)
async def add_tag(
    conversation_id: str,
    payload: TagAdd,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """Append a tag to a conversation owned by the caller (idempotent)."""
    service = ConversationService(db)
    try:
        return await service.add_tag(
            user.user_id,
            user.tenant_id,
            conversation_id,
            payload.tag,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.delete(
    "/{conversation_id}/tags/{tag}",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversations", "update"))],
)
async def remove_tag(
    conversation_id: str,
    tag: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """Remove a tag from a conversation owned by the caller."""
    service = ConversationService(db)
    try:
        return await service.remove_tag(
            user.user_id,
            user.tenant_id,
            conversation_id,
            tag,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.patch(
    "/{conversation_id}/pin",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversations", "update"))],
)
async def set_pinned(
    conversation_id: str,
    payload: PinUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """Set or clear the pinned flag on a conversation owned by the caller."""
    service = ConversationService(db)
    try:
        return await service.set_pinned(
            user.user_id,
            user.tenant_id,
            conversation_id,
            payload.pinned,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.patch(
    "/{conversation_id}/star",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversations", "update"))],
)
async def set_starred(
    conversation_id: str,
    payload: StarUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    """Set or clear the starred flag on a conversation owned by the caller."""
    service = ConversationService(db)
    try:
        return await service.set_starred(
            user.user_id,
            user.tenant_id,
            conversation_id,
            payload.starred,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e
