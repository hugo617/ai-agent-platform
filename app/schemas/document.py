"""Pydantic schemas for knowledge-base (Document) DTOs.

Three shapes:

- ``DocumentCreate`` — write payload (name + content + optional source type).
- ``DocumentRead`` — list/detail response (includes the pipeline status and
  chunk count).
- ``RetrieveRequest`` / ``RetrieveResult`` — the retrieval-debug endpoint,
  which returns the matched chunks with their similarity scores so an admin
  can verify the RAG pipeline is finding the right context.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Payload for POST /knowledge/documents/."""

    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source_type: str = Field("text", pattern="^(text|upload)$")


class DocumentRead(BaseModel):
    """Document list/detail response.

    ``scope`` / ``group_id`` / ``category_id`` are exposed so a store viewer can
    tell platform-distributed vs group-distributed vs own-store documents apart
    (knowledge-tiered Feature B slice 02). All three are nullable/optional in
    the sense that older rows pre-date the tiering columns, but the model's
    ``server_default='store'`` means ``scope`` is always populated — ``group_id``
    and ``category_id`` are genuinely optional (None for store/platform docs
    without a category). Forward-compatible: existing responses simply gain
    three fields.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    source_type: str
    content: str
    chunk_count: int
    status: str  # pending | indexed | failed
    # Tier the document belongs to (knowledge-tiered foundation E4). scope is
    # always present (server_default 'store'); group_id set only for scope=group;
    # category_id None when uncategorized.
    scope: str = "store"
    group_id: str | None = None
    category_id: str | None = None
    created_at: datetime
    updated_at: datetime


class RetrieveRequest(BaseModel):
    """Payload for POST /knowledge/retrieve (debug retrieval)."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(4, ge=1, le=20)


class RetrieveHit(BaseModel):
    """One matched chunk with its similarity score."""

    content: str
    score: float  # cosine similarity (1 - cosine_distance); higher is better
    document_id: str
    document_name: str


class RetrieveResult(BaseModel):
    """The retrieval-debug response."""

    query: str
    hits: list[RetrieveHit]


# ------------------------------------------------------------ distribution (G4)
# Distributing a document pushes it to one or more target stores
# (knowledge-tiered Feature B slice 03). The caller picks EXACTLY ONE of two
# targeting shapes:
#   - ``target_tenant_ids`` — an explicit list of store tenant_ids.
#   - ``target_group_id``   — every store in that group (expanded server-side).
# Both-set or neither-set is a 400 (G4). Like ``KnowledgeCategoryCreate``'s
# scope↔(group_id, tenant_id) binding, this cross-field XOR lives in the SERVICE
# as a ``BizError`` rather than a pydantic ``model_validator``: a hand-rolled
# validator raising ``ValueError`` embeds the raw exception in the error's
# ``ctx``, which FastAPI's validation-error handler then fails to JSON-serialize
# (see BookingCreate / KnowledgeCategoryCreate docstrings for the same hazard).
# The schema therefore declares both fields Optional and leaves the XOR to the
# service, which serializes cleanly.


class DistributeRequest(BaseModel):
    """Payload for POST /knowledge/documents/{doc_id}/distribute (G4).

    Exactly one of ``target_tenant_ids`` / ``target_group_id`` must be set; the
    XOR is enforced in ``KnowledgeService.distribute_document`` (BizError → 400).
    """

    target_tenant_ids: list[str] | None = None
    target_group_id: str | None = None


class KnowledgeDistributionRead(BaseModel):
    """One distribution row — the reference-model link (D4) doc→store.

    Returned from the distribute endpoint so the caller sees which stores a doc
    was pushed to, by whom, and whether the push is still active. ``distributed_by``
    is nullable (SET NULL on user delete, see the model docstring) and
    ``is_active`` carries the soft-revoke state (D4: revoke = flip, not delete).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_doc_id: str
    target_tenant_id: str
    distributed_by: str | None
    distributed_at: datetime
    is_active: bool


# ---------------------------------------------------------------- categories
# Knowledge categories are tiered by ``scope`` (knowledge-tiered Feature B,
# slice 01). The scope↔(group_id, tenant_id) binding is mutually exclusive:
#   platform → both NULL  |  group → group_id set, tenant_id NULL
#                store  → tenant_id set, group_id NULL
# NOTE: this cross-field binding is NOT a ``model_validator`` here. A
# hand-rolled validator raising ``ValueError`` embeds the raw exception object
# in the error's ``ctx``, which FastAPI's validation-error handler then fails
# to JSON-serialize (the same hazard ``BookingCreate`` documents — see its
# docstring). Cross-field checks can't be a native constraint, so the binding
# lives in ``CategoryService._check_scope_binding`` as a ``BizError`` → 400,
# which serializes cleanly. ``scope`` itself is a native pattern (single
# field), so it stays here.


class KnowledgeCategoryBase(BaseModel):
    """Shared shape for create/update payloads."""

    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0


class KnowledgeCategoryCreate(KnowledgeCategoryBase):
    """Payload for POST /knowledge/categories — scope-tiered.

    The (scope, group_id, tenant_id) combo consistency is enforced in
    ``CategoryService`` (BizError → 400, serializes cleanly); the scope↔role
    authorization (who may create which scope) is also there (G6).
    """

    scope: str = Field(..., pattern="^(platform|group|store)$")
    group_id: str | None = None
    tenant_id: str | None = None


class KnowledgeCategoryUpdate(BaseModel):
    """Payload for PUT /knowledge/categories/{id} — name/sort only.

    Does NOT inherit ``KnowledgeCategoryBase``: every base field is overridden
    Optional here (partial update), so inheritance would be Refused Bequest with
    no payoff. Scope and ownership (group_id/tenant_id) are immutable after
    create: moving a Category between tiers would silently change who can
    see/edit it. A re-tier is delete + recreate (mirrors how Group code is
    immutable).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None


class KnowledgeCategoryRead(BaseModel):
    """Category list/detail response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    scope: str
    group_id: str | None = None
    tenant_id: str | None = None
    sort_order: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
