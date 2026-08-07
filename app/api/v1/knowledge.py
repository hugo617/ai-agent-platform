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
    DistributeRequest,
    DocumentCreate,
    DocumentRead,
    KnowledgeCategoryCreate,
    KnowledgeCategoryRead,
    KnowledgeCategoryUpdate,
    KnowledgeDistributionRead,
    RetrieveRequest,
    RetrieveResult,
)
from app.services.category_service import KnowledgeCategoryService
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


# --------------------------------------------------- distribution (slice 03)
# D3 explicit distribution: a superior pushes a source document to target store(s)
# by writing knowledge_distribution rows (the reference-model link, D4). Two
# endpoints — POST to distribute (G4: target_tenant_ids XOR target_group_id),
# DELETE to revoke (soft flip is_active=false, audit preserved). Both require the
# new ``knowledge:distribute`` perm (seeded for owner/admin, not member; the
# group_admin bypass fires via the service's require(db=self.db)).


@router.post(
    "/documents/{document_id}/distribute",
    response_model=list[KnowledgeDistributionRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("knowledge", "distribute"))],
)
async def distribute_document(
    document_id: str,
    payload: DistributeRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeDistributionRead]:
    """Push a source document to target store(s).

    Body is G4 XOR: ``target_tenant_ids`` (explicit list) OR ``target_group_id``
    (expand to every store in that group). group_admin may only target their own
    group; super_admin is unrestricted. Returns the resulting distribution rows.
    """
    return await KnowledgeService(db).distribute_document(
        user.user_id,
        user.tenant_id,
        document_id,
        payload,
        platform_role=user.platform_role,
    )


@router.delete(
    "/distributions/{distribution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("knowledge", "distribute"))],
)
async def revoke_distribution(
    distribution_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-revoke a distribution (is_active=false; audit row preserved).

    After revoke the target store's list/retrieve automatically exclude the doc
    (their ``dist.is_active=True`` predicate drops it) — no manual flip needed.
    """
    await KnowledgeService(db).revoke_distribution(
        user.user_id,
        user.tenant_id,
        distribution_id,
        platform_role=user.platform_role,
    )


# -------------------------------------------------------- categories (slice 01)
# Tiered Category CRUD (plan-knowledge-tiered-backend slice 01). The casbin
# gate reuses the existing knowledge:read/create/delete codes (G6: no new code);
# KnowledgeCategoryService adds the scope↔role binding (platform→super_admin /
# group→group_admin / store→owner-admin) on top. ``update`` rides the
# ``knowledge:create`` write gate (no knowledge:update code exists — documents
# have no edit path; see KnowledgeCategoryService.update docstring).


@router.get(
    "/categories",
    response_model=list[KnowledgeCategoryRead],
    dependencies=[Depends(require_permission("knowledge", "read"))],
)
async def list_categories(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeCategoryRead]:
    """List Categories visible to the caller (platform + own group + own store).

    group_admin gets the aggregated chain view (all sibling stores in their
    group); super_admin/hq_staff see everything.
    """
    return await KnowledgeCategoryService(db).list(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.post(
    "/categories",
    response_model=KnowledgeCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("knowledge", "create"))],
)
async def create_category(
    payload: KnowledgeCategoryCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeCategoryRead:
    """Create a Category in the caller's authorized scope (G6 scope↔role check)."""
    return await KnowledgeCategoryService(db).create(
        user.user_id, user.tenant_id, payload, platform_role=user.platform_role
    )


@router.put(
    "/categories/{category_id}",
    response_model=KnowledgeCategoryRead,
    dependencies=[Depends(require_permission("knowledge", "create"))],
)
async def update_category(
    category_id: str,
    payload: KnowledgeCategoryUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeCategoryRead:
    """Update a Category's name/sort_order (scope and ownership are immutable)."""
    return await KnowledgeCategoryService(db).update(
        user.user_id, user.tenant_id, category_id, payload,
        platform_role=user.platform_role,
    )


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("knowledge", "delete"))],
)
async def delete_category(
    category_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a Category (is_deleted=true; name reusable afterwards)."""
    await KnowledgeCategoryService(db).delete(
        user.user_id, user.tenant_id, category_id,
        platform_role=user.platform_role,
    )
