"""Pydantic schemas for embedding configuration DTOs.

Naming follows the project convention: ``Update`` for write payloads, ``Read``
for API responses. The decrypted key only ever lives in
``EffectiveEmbeddingConfig``, which is an internal type — never serialized to
the API. Mirrors ``app/schemas/llm_config.py`` but drops the model list.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingConfigUpdate(BaseModel):
    """Payload for PUT /settings/embedding/{platform,tenant}.

    ``api_key`` is optional: omit it (or send null/empty) to keep the stored
    key unchanged, e.g. when editing only the model.
    """

    api_key: str | None = Field(None, min_length=1, max_length=512)
    base_url: str | None = Field(None, max_length=255)
    model: str | None = Field(None, max_length=64)


class EmbeddingConfigRead(BaseModel):
    """Masked embedding config returned by GET endpoints.

    Never exposes the plaintext or ciphertext key — only ``api_key_hint``
    (e.g. ``sk-***wxyz``) so the UI can show which key is stored.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None
    api_key_hint: str
    base_url: str
    model: str
    is_active: bool
    updated_at: datetime


class EffectiveEmbeddingConfig(BaseModel):
    """The resolved, ready-to-use embedding config (internal — key decrypted).

    Produced by :meth:`EmbeddingConfigService.get_effective` after the
    tenant > platform > env fallback chain. Passed to ``EmbeddingService`` so
    it can instantiate ``OpenAIEmbeddings`` without touching global settings.

    ``dimension`` is a constant (1024 for BAAI/bge-m3) carried here so callers
    building ``Vector(dimension)`` columns or checking lengths don't hardcode
    the magic number in multiple places. It mirrors
    :data:`app.models.document.EMBEDDING_DIMENSION` — keep them in sync when
    switching embedding models.
    """

    api_key: str
    base_url: str
    model: str
    dimension: int = 1024

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_resolved(
        cls, *, api_key: str, base_url: str, model: str, dimension: int = 1024
    ) -> "EffectiveEmbeddingConfig":
        return cls(
            api_key=api_key, base_url=base_url, model=model, dimension=dimension
        )

    def model_dump_safe(self) -> dict[str, Any]:
        """Dump without the secret (for logging)."""
        d = self.model_dump()
        d["api_key"] = "***"
        return d
