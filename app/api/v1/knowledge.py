"""Knowledge-base endpoints — document CRUD + retrieval debug (RAG, priority 57).

Documents are tenant-scoped: a store only ever sees its own knowledge base
(enforced at the repository layer). Permission granularity mirrors the unified
permission model: ``knowledge:read`` (GET) seeded for owner/admin/member,
``knowledge:create`` / ``knowledge:delete`` seeded for owner/admin (admin has
no delete). Super admins short-circuit via ``permission_service.check``.

Create ingests inline (split + embed + index) within the request — MVP scope,
no background task. If the embedding provider is misconfigured the document is
still created but marked ``status=failed`` so the admin sees it in the list.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.document import (
    DocumentCreate,
    DocumentRead,
    RetrieveRequest,
    RetrieveResult,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get(
    "/documents",
    response_model=list[DocumentRead],
    dependencies=[Depends(require_permission("knowledge", "read"))],
)
async def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentRead]:
    """List the caller's tenant documents."""
    return await KnowledgeService(db).list_documents(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.post(
    "/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("knowledge", "create"))],
)
async def create_document(
    payload: DocumentCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    """Create a document and ingest it (split + embed + index) inline."""
    return await KnowledgeService(db).create_document(
        user.user_id,
        user.tenant_id,
        payload,
        platform_role=user.platform_role,
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("knowledge", "delete"))],
)
async def delete_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a document and drop its chunks."""
    await KnowledgeService(db).delete_document(
        user.user_id,
        user.tenant_id,
        document_id,
        platform_role=user.platform_role,
    )


@router.post(
    "/retrieve",
    response_model=RetrieveResult,
    dependencies=[Depends(require_permission("knowledge", "read"))],
)
async def retrieve(
    payload: RetrieveRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetrieveResult:
    """Debug retrieval: embed the query, return top-k chunks with scores.

    Lets an admin verify the RAG pipeline finds the right context before
    relying on it in agent conversations. Requires Postgres (pgvector) — on
    SQLite this is exercised via mocked embeddings.
    """
    return await KnowledgeService(db).retrieve_for_debug(
        user.user_id,
        user.tenant_id,
        payload.query,
        top_k=payload.top_k,
        platform_role=user.platform_role,
    )
