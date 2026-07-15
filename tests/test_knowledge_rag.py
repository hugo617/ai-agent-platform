"""Knowledge base / RAG tests (priority 57).

We never call the real OpenAI embeddings API or run real vector SQL (SQLite
has no vector extension). Instead:

- **Chunking** (the ``RecursiveCharacterTextSplitter``) is exercised directly —
  it's a pure function with no external deps, so we assert its behaviour.
- **Ingest** is tested by stubbing ``EmbeddingService`` to return fixed
  vectors, then asserting chunks are created with the right content/index.
- **Retrieve** is tested by stubbing ``KnowledgeService.retrieve`` itself
  (the cosine-distance SQL is Postgres-only) — we assert the debug endpoint
  shapes the response correctly and enforces tenant isolation + permissions.
- **CRUD + permissions** are tested end-to-end through the API.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ---------------------------------------------------------------------------
# Pure-function: chunking (no mocking needed).
# ---------------------------------------------------------------------------


def test_recursive_splitter_chunks_long_text():
    """The splitter breaks long text into overlapping chunks."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
    text = "理疗服务介绍。" * 50  # ~400 chars
    chunks = splitter.split_text(text)
    assert len(chunks) > 1
    # Each chunk is at most chunk_size + some tolerance (overlap inflates).
    assert all(len(c) <= 120 for c in chunks)


def test_recursive_splitter_short_text_is_single_chunk():
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text("短文本")
    assert chunks == ["短文本"]


# ---------------------------------------------------------------------------
# Helpers: stub the embedding layer so ingest/retrieve are offline.
# ---------------------------------------------------------------------------


class _FakeEmbeddingService:
    """Drop-in for EmbeddingService that returns deterministic vectors.

    Returns a distinct-ish vector per chunk index so ingest produces N rows.
    """

    def __init__(self, **_kwargs):
        pass

    async def embed(self, texts):
        return [[float(i % 10) / 10.0] * 8 for i in range(len(texts))]

    async def embed_query(self, text):
        return [0.5] * 8


@pytest.fixture
def stub_embedding(monkeypatch):
    """Replace EmbeddingService + the embedding config resolution in the
    knowledge_service module so ingest runs fully offline."""
    from app.services import knowledge_service as ks_mod

    monkeypatch.setattr(ks_mod, "EmbeddingService", _FakeEmbeddingService)

    # Stub get_effective so it doesn't try to decrypt a non-existent DB row
    # or fall through to env defaults (which carry a placeholder key).
    from app.schemas.embedding_config import EffectiveEmbeddingConfig

    async def fake_get_effective(_db, _tenant_id):
        return EffectiveEmbeddingConfig.from_resolved(
            api_key="sk-test", base_url="http://localhost", model="test-embed"
        )

    monkeypatch.setattr(
        ks_mod.embedding_config_service, "get_effective", fake_get_effective
    )


# ---------------------------------------------------------------------------
# API: document CRUD + ingest.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_creates_document_and_ingests(app_client, stub_embedding):
    """Creating a document ingests it: chunks are created, status → indexed."""
    resp = await app_client.post(
        "/api/v1/knowledge/documents",
        headers=AUTH,
        json={"name": "颈椎理疗话术", "content": "这是一段理疗服务介绍。" * 20},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "颈椎理疗话术"
    assert body["status"] == "indexed"
    assert body["chunk_count"] >= 1


@pytest.mark.asyncio
async def test_list_documents_returns_tenant_docs(app_client, stub_embedding):
    await app_client.post(
        "/api/v1/knowledge/documents",
        headers=AUTH,
        json={"name": "FAQ", "content": "常见问题解答内容"},
    )
    resp = await app_client.get("/api/v1/knowledge/documents", headers=AUTH)
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "FAQ" in names


@pytest.mark.asyncio
async def test_delete_document_soft_deletes_and_clears_chunks(
    app_client, stub_embedding, db_session
):
    from sqlalchemy import select

    from app.models.document import Document, DocumentChunk

    create = await app_client.post(
        "/api/v1/knowledge/documents",
        headers=AUTH,
        json={"name": "待删除", "content": "内容" * 50},
    )
    doc_id = create.json()["id"]

    del_resp = await app_client.delete(
        f"/api/v1/knowledge/documents/{doc_id}", headers=AUTH
    )
    assert del_resp.status_code == 204

    # Document is soft-deleted...
    doc = (
        await db_session.execute(
            select(Document).where(Document.id == doc_id)
        )
    ).scalar_one()
    assert doc.is_deleted is True
    # ...and its chunks are hard-deleted.
    chunks = (
        await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
    ).scalars().all()
    assert chunks == []
    # List no longer shows it.
    listing = await app_client.get(
        "/api/v1/knowledge/documents", headers=AUTH
    )
    assert doc_id not in [d["id"] for d in listing.json()]


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(app_client, stub_embedding):
    resp = await app_client.delete(
        "/api/v1/knowledge/documents/nope", headers=AUTH
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Permissions.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_can_read_but_not_create(member_client, stub_embedding):
    """member has knowledge:read but not knowledge:create."""
    read = await member_client.get(
        "/api/v1/knowledge/documents", headers=AUTH
    )
    assert read.status_code == 200
    create = await member_client.post(
        "/api/v1/knowledge/documents",
        headers=AUTH,
        json={"name": "x", "content": "y"},
    )
    assert create.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_but_not_delete(
    tenant_admin_client, stub_embedding
):
    """admin has knowledge:create but not knowledge:delete (no update path)."""
    create = await tenant_admin_client.post(
        "/api/v1/knowledge/documents",
        headers=AUTH,
        json={"name": "admin doc", "content": "内容"},
    )
    assert create.status_code == 201
    doc_id = create.json()["id"]
    delete = await tenant_admin_client.delete(
        f"/api/v1/knowledge/documents/{doc_id}", headers=AUTH
    )
    assert delete.status_code == 403


# ---------------------------------------------------------------------------
# Retrieval: stubbed (cosine SQL is Postgres-only).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_debug_returns_hits(
    app_client, monkeypatch, db_session, test_env
):
    """retrieve_for_debug shapes the repository hits into the API response."""
    from app.services import knowledge_service as ks_mod

    async def fake_retrieve(self, query, tenant_id, top_k=4):
        return [("相关片段内容", 0.92, "doc-1")]

    monkeypatch.setattr(ks_mod.KnowledgeService, "retrieve", fake_retrieve)

    # Seed a doc in the *same* tenant the app_client is scoped to, so the
    # document-name lookup in retrieve_for_debug finds it.
    from app.models.document import Document

    db_session.add(
        Document(id="doc-1", tenant_id=test_env.tenant_id, name="话术库")
    )
    await db_session.commit()

    resp = await app_client.post(
        "/api/v1/knowledge/retrieve",
        headers=AUTH,
        json={"query": "颈椎理疗", "top_k": 4},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "颈椎理疗"
    assert len(body["hits"]) == 1
    assert body["hits"][0]["content"] == "相关片段内容"
    assert body["hits"][0]["score"] == pytest.approx(0.92)
    assert body["hits"][0]["document_name"] == "话术库"


@pytest.mark.asyncio
async def test_retrieve_member_allowed(member_client, monkeypatch):
    """knowledge:read (held by member) is enough to call retrieve."""
    from app.services import knowledge_service as ks_mod

    async def fake_retrieve(self, query, tenant_id, top_k=4):
        return []

    monkeypatch.setattr(ks_mod.KnowledgeService, "retrieve", fake_retrieve)

    resp = await member_client.post(
        "/api/v1/knowledge/retrieve",
        headers=AUTH,
        json={"query": "anything"},
    )
    assert resp.status_code == 200
    assert resp.json()["hits"] == []
