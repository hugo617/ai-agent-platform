"""Pydantic schemas for LLM configuration DTOs.

Naming follows the project convention: ``Update`` for write payloads, ``Read``
for API responses. The decrypted key only ever lives in ``EffectiveLlmConfig``,
which is an internal type — never serialized to the API.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LlmConfigUpdate(BaseModel):
    """Payload for PUT /settings/llm/{platform,tenant}.

    ``api_key`` is optional: omit it (or send null/empty) to keep the stored
    key unchanged, e.g. when editing only the model list.
    """

    api_key: str | None = Field(None, min_length=1, max_length=512)
    base_url: str | None = Field(None, max_length=255)
    default_model: str | None = Field(None, max_length=64)
    available_models: list[str] | None = None


class LlmConfigRead(BaseModel):
    """Masked LLM config returned by GET endpoints.

    Never exposes the plaintext or ciphertext key — only ``api_key_hint``
    (e.g. ``sk-***wxyz``) so the UI can show which key is stored.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None
    api_key_hint: str
    base_url: str
    default_model: str
    available_models: list[str]
    is_active: bool
    updated_at: datetime


class EffectiveLlmConfig(BaseModel):
    """The resolved, ready-to-use config (internal only — key is decrypted).

    Produced by ``LlmConfigService.get_effective`` after the tenant > platform
    > env fallback chain. Passed to ``stream_agent`` so it can instantiate
    ``ChatOpenAI`` without touching global settings.
    """

    api_key: str
    base_url: str
    default_model: str
    available_models: list[str]

    model_config = ConfigDict(from_attributes=True)

    # Accept both ORM rows (with api_key_encrypted) and plain dicts; the
    # service always builds this from decrypted values.
    @classmethod
    def from_resolved(
        cls, *, api_key: str, base_url: str, default_model: str, available_models: list[str]
    ) -> "EffectiveLlmConfig":
        return cls(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            available_models=available_models,
        )

    def model_dump_safe(self) -> dict[str, Any]:
        """Dump without the secret (for logging)."""
        d = self.model_dump()
        d["api_key"] = "***"
        return d
