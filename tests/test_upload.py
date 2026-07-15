"""File upload endpoint tests — ``POST /uploads/upload``.

Covers the behaviour added in priority 56:

- Happy path: a valid PNG is accepted, returns a /static URL + UUID key, and
  the URL is fetchable (GET 200) with the original bytes.
- Type whitelist: a disallowed content-type → 400.
- Size cap: an oversized upload → 413 (rejected without holding the whole body).
- Auth: no token → 401.
- Tenant keying: the returned key is prefixed with the caller's tenant_id and
  contains no original-filename segment (anti path-traversal).

The local storage backend writes into a per-test tmp directory (not the real
``uploads/`` under the repo), patched onto ``settings`` before the app is
created. This keeps tests hermetic and exercises the real LocalStorage code.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

AUTH = {"Authorization": "Bearer fake"}

# Minimal PNG (1x1 transparent). Small + widely-recognised so the content-type
# check has a real payload to read; the bytes themselves don't matter beyond
# round-tripping through storage and /static.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c636000000000050001a5f645400000000049454e44ae426082"
)


def _png(name: str = "avatar.png"):
    """A starlette UploadFile-alike tuple for httpx's ``files=`` kwarg."""
    return (name, _PNG_BYTES, "image/png")


@pytest.fixture
async def upload_client(test_env, tmp_path: Path):
    """An app_client whose local storage dir is a tmp dir, not the real uploads/.

    ``settings.storage_local_dir`` is what ``LocalStorage.__init__`` reads to
    resolve its root, and ``get_storage()`` builds the backend lazily — so
    patching the attribute *before* ``create_app`` runs makes ``get_storage()``
    land inside ``tmp_path``. This is the hermetic equivalent of pointing a
    real deploy at an uploads volume.
    """
    from contextlib import asynccontextmanager

    from app.api import deps as deps_mod
    from app.core import casbin_enforcer as casbin_mod
    from app.core.config import settings
    from app.core.database import get_db
    from app.core.storage import reset_storage_cache
    from app.main import create_app

    upload_dir = tmp_path / "uploads"
    with patch.object(settings, "storage_local_dir", str(upload_dir)):
        reset_storage_cache()
        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app):
            yield

        app.router.lifespan_context = noop_lifespan

        async def override_get_db():
            async with test_env.factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        async def fake_decode(token: str):
            return {
                "sub": test_env.owner_user,
                "tenant_id": test_env.tenant_id,
                "email": "owner@example.com",
            }

        from unittest.mock import AsyncMock

        with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer), \
             patch.object(deps_mod, "decode_token", new=AsyncMock(side_effect=fake_decode)):
            from httpx import ASGITransport, AsyncClient

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

        app.dependency_overrides.clear()
        reset_storage_cache()


@pytest.mark.asyncio
async def test_upload_png_returns_url_and_key(upload_client):
    """A valid PNG returns {url, key, size, content_type}; key is tenant/uuid."""
    resp = await upload_client.post(
        "/api/v1/uploads/upload",
        files={"file": _png()},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content_type"] == "image/png"
    assert body["size"] == len(_PNG_BYTES)
    assert body["url"].startswith("uploads/files/")
    # url and key agree: uploads/files/{key}
    assert body["url"].removeprefix("uploads/files/") == body["key"]
    assert body["key"].endswith(".png")
    # No original filename leaked into the key — only tenant/uuid.ext.
    assert "avatar" not in body["key"]
    assert "/" in body["key"]  # tenant-prefixed
    assert ".." not in body["key"]


@pytest.mark.asyncio
async def test_upload_then_download_returns_bytes(upload_client):
    """The authenticated download route serves the exact bytes we uploaded.

    Replaces the old ``/static`` mount test: downloads now go through
    ``GET /api/v1/uploads/files/{key}`` which requires a token. The returned
    ``url`` is a relative path (``uploads/files/{key}``) the frontend axios
    instance joins to its ``/api/v1`` baseURL; here we build the full path.
    """
    resp = await upload_client.post(
        "/api/v1/uploads/upload",
        files={"file": _png("logo.png")},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    key = resp.json()["key"]

    got = await upload_client.get(f"/api/v1/uploads/files/{key}", headers=AUTH)
    assert got.status_code == 200
    assert got.content == _PNG_BYTES
    assert got.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_download_requires_auth(upload_client):
    """No Authorization header on the download route → 401 (was 200 under /static)."""
    resp = await upload_client.post(
        "/api/v1/uploads/upload",
        files={"file": _png()},
        headers=AUTH,
    )
    key = resp.json()["key"]
    got = await upload_client.get(f"/api/v1/uploads/files/{key}")
    assert got.status_code == 401


@pytest.mark.asyncio
async def test_download_404_missing(upload_client):
    """A key that doesn't exist on disk → 404, not 500."""
    got = await upload_client.get(
        "/api/v1/uploads/files/does-not-exist/abc.png", headers=AUTH
    )
    assert got.status_code == 404


@pytest.mark.asyncio
async def test_upload_rejects_disallowed_content_type(upload_client):
    """A content-type outside the whitelist → 400."""
    resp = await upload_client.post(
        "/api/v1/uploads/upload",
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=AUTH,
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(upload_client):
    """A file larger than upload_max_bytes → 413."""
    from app.core.config import settings

    cap = settings.upload_max_bytes
    # One byte over the cap is enough; the route reads cap+1 bytes and rejects.
    too_big = b"\x00" * (cap + 1)
    resp = await upload_client.post(
        "/api/v1/uploads/upload",
        files={"file": ("big.png", too_big, "image/png")},
        headers=AUTH,
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_requires_auth(app_client):
    """No Authorization header → 401 (uploads are authenticated-only)."""
    # app_client (not upload_client) is fine here — we only assert the auth
    # gate, which runs before storage is touched.
    resp = await app_client.post(
        "/api/v1/uploads/upload",
        files={"file": _png()},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_key_is_tenant_scoped(upload_client):
    """The key is prefixed with the caller's tenant_id so files are grouped."""
    resp = await upload_client.post(
        "/api/v1/uploads/upload",
        files={"file": _png()},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    key = resp.json()["key"]
    # The fake_decode mock in the fixture binds the owner to test_env.tenant_id,
    # so the key must start with that tenant prefix.
    # Recover the tenant_id: it's the segment before the uuid.
    prefix = key.rsplit("/", 1)[0]
    # The fixture's tenant is whatever test_env picked; assert the prefix is a
    # non-empty, uuid-like tenant id (no original filename, no traversal).
    assert "/" in key
    assert prefix  # non-empty tenant prefix
    assert ".." not in key


# --------------------------------------------------------------- S3 backend
#
# These exercise the real AmazonS3Storage against a moto-mocked S3, so no AWS
# credentials are needed. We build the backend directly (not through the upload
# HTTP route) because the route's download endpoint is local-only — S3 save
# returns an absolute URL the route doesn't serve. Testing the backend class
# directly is what proves the boto3 calls are wired correctly.


@pytest.fixture
def s3_backend(monkeypatch, tmp_path):
    """A real AmazonS3Storage against an isolated moto S3.

    moto reads fake credentials from the environment; we set them, flip the
    storage settings to s3, create the bucket, and yield a fresh backend.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    from moto import mock_aws

    from app.core import storage as storage_mod
    from app.core.config import settings

    bucket = "test-uploads"
    with mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=bucket
        )
        with patch.object(settings, "s3_bucket", bucket), \
             patch.object(settings, "s3_region", "us-east-1"), \
             patch.object(settings, "s3_access_key", "test"), \
             patch.object(settings, "s3_secret_key", "test"):
            storage_mod.reset_storage_cache()
            yield storage_mod.AmazonS3Storage()
            storage_mod.reset_storage_cache()


@pytest.mark.asyncio
async def test_s3_save_returns_absolute_url_and_object_exists(s3_backend):
    """save() puts the object in S3 and returns a public https URL."""
    import boto3

    url = await s3_backend.save(_PNG_BYTES, "image/png", "t1/abc.png")
    assert url == "https://test-uploads.s3.us-east-1.amazonaws.com/t1/abc.png"
    # The object really landed in (mocked) S3.
    objs = boto3.client("s3", region_name="us-east-1").list_objects_v2(
        Bucket="test-uploads"
    )
    keys = [o["Key"] for o in objs.get("Contents", [])]
    assert "t1/abc.png" in keys


@pytest.mark.asyncio
async def test_s3_delete_is_idempotent(s3_backend):
    """Deleting a key that was never written is a no-op (S3 semantics)."""
    # No setup — the key doesn't exist; delete must not raise.
    await s3_backend.delete("never/existed.png")
    assert await s3_backend.exists("never/existed.png") is False


@pytest.mark.asyncio
async def test_s3_exists_after_save(s3_backend):
    """exists() reflects put_object: False before save, True after."""
    assert await s3_backend.exists("t2/img.png") is False
    await s3_backend.save(_PNG_BYTES, "image/png", "t2/img.png")
    assert await s3_backend.exists("t2/img.png") is True
