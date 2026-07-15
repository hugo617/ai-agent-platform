"""File storage abstraction (priority 56).

Provides a single ``StorageBackend`` interface with three implementations:

- ``LocalStorage`` — writes to a local directory and serves files back over the
  authenticated ``GET /uploads/files/{key}`` download route. This is the default
  and the backend used in dev/test.
- ``AmazonS3Storage`` — real S3 backend (``boto3`` is a runtime dependency).
  ``save`` returns the object's public https URL. Select with
  ``settings.storage_backend = "s3"`` + S3_* credentials.
- ``AliyunOSSStorage`` — stub. ``oss2`` is NOT a dependency, so every method
  raises ``NotImplementedError`` with install/config instructions until wired
  up. The shape (``save``/``delete``/``exists``) mirrors a real OSS backend, so
  implementing it later is a fill-in-the-blank exercise.

``get_storage()`` is a cached factory returning the backend chosen by
``settings.storage_backend``. Keeping it cached means every upload in a process
reuses one backend instance (Local creates its dir once; S3 reuses one client).
Tests reset the cache via ``reset_storage_cache``.

Design notes (per project 铁律 + plan-file-upload-storage.md):

- Storage is **infrastructure** (like metrics/scheduler), not a business
  Repository, so calling it directly from the API controller is fine — the
  controller → service → repository layering rule is about business data.
- ``save`` takes raw ``file_bytes`` (not an ``UploadFile``) so the backend is
  decoupled from Starlette and trivially testable. The upload route reads the
  bytes + validates them, then hands them to the backend with an opaque key.
- The key is always caller-supplied and is expected to be a UUID-derived path
  (never the user's original filename) to prevent path traversal. The backend
  never trusts the key beyond joining it under its root.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import boto3  # runtime dep (requirements.txt) — powers AmazonS3Storage

from app.core.config import settings

if TYPE_CHECKING:
    from typing import Final


class StorageError(RuntimeError):
    """Raised by a backend when a write/delete fails for an infra reason."""


class StorageBackend(ABC):
    """Pluggable object/file storage.

    Implementations store ``file_bytes`` under ``key`` and return the public
    URL the client can fetch it from. The key is opaque to the backend — the
    upload route generates ``{tenant_id}/{uuid}{ext}`` so there is no original
    filename to leak or traverse on.
    """

    @abstractmethod
    async def save(self, file_bytes: bytes, content_type: str, key: str) -> str:
        """Persist ``file_bytes`` under ``key``. Return the access URL."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the object at ``key``. Missing keys are a no-op."""

    async def exists(self, key: str) -> bool:
        """Whether an object exists at ``key``. Default impl reads dir/list."""
        return False


class LocalStorage(StorageBackend):
    """Writes files to a local directory; served back over the authenticated
    ``GET /uploads/files/{key}`` download route (see ``uploads.download_file``).

    The directory (and the per-tenant subdirectory implied by the key) is
    created lazily on first write so a fresh checkout with no ``uploads/``
    dir works immediately — and so the download route returns 404 (not a 500
    startup error) if the dir happens to be absent.

    Writes go through ``anyio.to_thread`` + ``Path.write_bytes`` rather than
    ``aiofiles`` because ``aiofiles`` is not a project dependency and adding
    it just for synchronous disk I/O would be noise. ``anyio`` ships with
    Starlette/FastAPI already.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        # Default to the configured dir resolved against the project root so it
        # is independent of the process cwd (uvicorn vs pytest vs alembic).
        if root is None:
            root = Path(__file__).resolve().parents[2] / settings.storage_local_dir
        self.root: Final = Path(root)

    def _path(self, key: str) -> Path:
        """Resolve ``key`` to an absolute path under ``self.root``.

        ``resolve()`` collapses any ``..`` segments and an attacker-supplied
        traversal key (``../../etc/passwd``) lands outside ``self.root``; the
        membership check rejects it. The upload route only ever passes UUID
        keys, so this is defense in depth.
        """
        target = (self.root / key).resolve()
        try:
            target.relative_to(self.root.resolve())
        except ValueError as exc:  # path escaped the root
            raise StorageError("key escapes storage root") from exc
        return target

    async def save(self, file_bytes: bytes, content_type: str, key: str) -> str:
        target = self._path(key)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file_bytes)

        try:
            await anyio.to_thread.run_sync(_write)
        except OSError as exc:  # pragma: no cover - disk failures are env-specific
            raise StorageError(f"failed to write {key}: {exc}") from exc
        # Relative to the API prefix: the download route is registered at
        # ``/api/v1/uploads/files/{key}``, and the frontend axios instance has
        # ``baseURL: "/api/v1"``, so a leading-slash-less relative path joins
        # correctly (``/api/v1`` + ``uploads/files/...``). S3/OSS backends return
        # absolute https URLs instead. See uploads.py ``download_file``.
        return f"uploads/files/{key}"

    async def delete(self, key: str) -> None:
        target = self._path(key)

        def _remove() -> None:
            try:
                target.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - best-effort cleanup
                pass

        await anyio.to_thread.run_sync(_remove)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


class AmazonS3Storage(StorageBackend):
    """Amazon S3 backend (real implementation, boto3 is a runtime dependency).

    Configured via ``settings.s3_*`` (bucket/region/access_key/secret_key). All
    boto3 calls go through ``anyio.to_thread`` so the async upload route isn't
    blocked on the blocking boto3 client. ``save`` returns the object's public
    https URL — a real deployment would typically serve the bucket via CloudFront
    (and may make the objects private + use presigned URLs); the URL we return
    is the canonical S3 path-style address the frontend can request directly.

    ``delete`` is idempotent: S3 ``delete_object`` on a missing key is a no-op
    (it returns 204 regardless), so we don't catch the 404 branch specially.
    """

    def __init__(self) -> None:
        if not (
            settings.s3_bucket
            and settings.s3_region
            and settings.s3_access_key
            and settings.s3_secret_key
        ):
            raise StorageError(
                "S3 storage not configured: set S3_BUCKET/S3_REGION/"
                "S3_ACCESS_KEY/S3_SECRET_KEY"
            )
        self.bucket: Final = settings.s3_bucket
        self.region: Final = settings.s3_region
        self._client = boto3.client(
            "s3",
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=self.region,
        )

    async def save(self, file_bytes: bytes, content_type: str, key: str) -> str:
        def _put() -> None:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )

        await anyio.to_thread.run_sync(_put)
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            self._client.delete_object(Bucket=self.bucket, Key=key)

        await anyio.to_thread.run_sync(_delete)

    async def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        def _head() -> None:
            self._client.head_object(Bucket=self.bucket, Key=key)

        try:
            await anyio.to_thread.run_sync(_head)
        except ClientError as exc:
            # 404 → does not exist; anything else propagates as a real error.
            if exc.response.get("Error", {}).get("Code") == "404":
                return False
            raise
        return True


class AliyunOSSStorage(StorageBackend):
    """Aliyun OSS backend (stub until oss2 + credentials are configured).

    Mirrors ``AmazonS3Storage``: ``oss2`` is not in requirements, so every
    method raises ``NotImplementedError`` with install/config instructions
    until both the SDK and credentials are present.
    """

    NOT_CONFIGURED = (
        "OSS storage not configured: set OSS_BUCKET/OSS_ENDPOINT/OSS_ACCESS_KEY/"
        "OSS_SECRET_KEY and install oss2 (not a default dependency)."
    )

    def __init__(self) -> None:
        self.bucket = settings.oss_bucket
        self.endpoint = settings.oss_endpoint

    def _ensure(self) -> None:
        if not (
            self.bucket and self.endpoint and settings.oss_access_key
            and settings.oss_secret_key
        ):
            raise NotImplementedError(self.NOT_CONFIGURED)
        try:
            import oss2  # noqa: F401  (presence check only)
        except ImportError as exc:  # pragma: no cover - depends on env
            raise NotImplementedError(self.NOT_CONFIGURED) from exc

    async def save(self, file_bytes: bytes, content_type: str, key: str) -> str:
        self._ensure()
        # Real impl (once oss2 is installed):
        #   auth = oss2.Auth(settings.oss_access_key, settings.oss_secret_key)
        #   bucket = oss2.Bucket(auth, self.endpoint, self.bucket)
        #   await anyio.to_thread.run_sync(
        #       bucket.put_object, key, file_bytes,
        #       headers={"Content-Type": content_type},
        #   )
        #   return f"https://{self.bucket}.{self.endpoint}/{key}"
        raise NotImplementedError(self.NOT_CONFIGURED)  # pragma: no cover

    async def delete(self, key: str) -> None:
        self._ensure()
        raise NotImplementedError(self.NOT_CONFIGURED)  # pragma: no cover


_BACKENDS = {
    "local": LocalStorage,
    "s3": AmazonS3Storage,
    "oss": AliyunOSSStorage,
}


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """Return the configured backend (cached per process).

    The backend name comes from ``settings.storage_backend``; an unknown name
    raises immediately so a typo fails at the first upload, not silently.
    """
    name = settings.storage_backend
    try:
        cls = _BACKENDS[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown storage_backend {name!r}; expected one of {sorted(_BACKENDS)}"
        ) from exc
    return cls()


def reset_storage_cache() -> None:
    """Drop the cached backend. Tests use this to point at a tmp dir."""
    get_storage.cache_clear()
