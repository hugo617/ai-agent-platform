"""Embedding service — turn text into vectors via an embeddings provider.

Mirrors the ``stream_agent`` pattern: the caller resolves the provider
credentials via ``EmbeddingConfigService.get_effective`` (tenant > platform >
env) and passes them in — this service never touches global settings, so
which provider actually serves an embedding is decided by the caller.

Uses langchain's ``OpenAIEmbeddings`` (an OpenAI-compatible client), so any
provider that speaks the OpenAI embeddings API works (OpenAI, Azure via a
custom base_url, local servers, Ollama, etc.). DeepSeek is NOT supported
here — it does not expose an embeddings endpoint, which is why embeddings
config is a separate table from the chat LLM config.

**Tokenization note.** ``OpenAIEmbeddings`` defaults to running the input
through tiktoken (to chunk-by-token for OpenAI's 8192-token context window).
That pre-tokenization breaks OpenAI-compatible servers that only accept raw
strings — e.g. Ollama rejects token IDs with ``invalid input type``. We pass
``check_embedding_ctx_length=False`` so the text is sent verbatim. This is
safe because :class:`KnowledgeService` already chunks via
``RecursiveCharacterTextSplitter`` (CHUNK_SIZE=500) before calling embed,
making langchain's second token-based chunking redundant.
"""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings


class EmbeddingService:
    """Wrap an ``OpenAIEmbeddings`` client for a resolved provider config."""

    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        # Explicitly pass ``model`` — the langchain default is the legacy
        # text-embedding-ada-002, whose dimension differs from whatever model
        # the caller resolved (default BAAI/bge-m3, 1024-dim). The chosen
        # model's dimension must match the ``document_chunks.embedding``
        # column width (see :data:`app.models.document.EMBEDDING_DIMENSION`).
        #
        # ``check_embedding_ctx_length=False``: skip langchain's tiktoken-based
        # pre-tokenization. Required for Ollama compatibility (token IDs get
        # rejected); harmless for OpenAI because we chunk upstream already.
        self._client = OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url,
            check_embedding_ctx_length=False,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (used during ingest)."""
        # aembed_documents is the async variant; returns one vector per text.
        return await self._client.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (used during retrieval)."""
        return await self._client.aembed_query(text)
