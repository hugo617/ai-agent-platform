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
    """Document list/detail response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    source_type: str
    content: str
    chunk_count: int
    status: str  # pending | indexed | failed
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
