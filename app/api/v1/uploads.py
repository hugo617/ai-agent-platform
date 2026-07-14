"""File upload endpoint (``POST /upload``).

No upload capability existed before this feature (priority 56); ``Customer.avatar``
was a dead field. This route is the foundation depended on by user-profile
(avatar), tenant-branding (logo) and knowledge-base-rag (documents).

Design notes (per project 铁律 + plan-file-upload-storage.md):

- **Infrastructure, not a Repository**: the storage backend is infrastructure
  (like metrics/scheduler), so the controller calls ``get_storage()`` directly
  instead of going through a service/repository layer. There is no DB row for
  an upload — the returned URL is what consumers persist on their own models.
- **Security**: the stored key is ``{tenant_id}/{uuid}{ext}`` — the user's
  original filename is **never** used, which both prevents path traversal and
  avoids leaking PII through filenames. The content-type is validated against
  an allowlist, and the size is capped at ``settings.upload_max_bytes``.
- **Size enforcement**: we read at most ``upload_max_bytes + 1`` bytes; if more
  arrives, the upload is oversized and rejected with 413 *before* we hold the
  whole oversized blob in memory (avoids a trivial memory-exhaustion DoS where
  a client streams a 10 GB body).
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.core.storage import StorageError, get_storage

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Content types accepted by the upload endpoint. Kept narrow on purpose: each
# entry is something a known consumer needs (avatars/logos → images, RAG → pdf
# + text). Adding a type here is a deliberate security decision, not a default.
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "application/pdf",
        "text/plain",
    }
)

# Extension picked from the content-type so the stored key carries a hint of
# what it is (purely cosmetic; the content-type is the source of truth). The
# upload route never trusts the client's filename for the extension.
_CONTENT_TYPE_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}


class UploadResponse(BaseModel):
    """Returned by POST /upload. ``url`` is what <img src=> / fetch should use."""

    url: str
    key: str
    size: int
    content_type: str


def _build_key(tenant_id: str, content_type: str) -> str:
    """Build a traversal-safe storage key.

    ``{tenant_id}/{uuid}{ext}`` — tenant prefix groups a tenant's files for a
    future cleanup/grep, the uuid makes the key unguessable and collision-free,
    and the extension is derived from the (validated) content-type, never the
    user's filename.
    """
    ext = _CONTENT_TYPE_EXT.get(content_type, "")
    return f"{tenant_id}/{uuid.uuid4().hex}{ext}"


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    user: CurrentUser = Depends(get_current_user),
    file: UploadFile = File(...),
) -> UploadResponse:
    """Accept a multipart upload and persist it via the configured backend.

    Any authenticated user may upload — consumers (avatar/logo/…) apply their
    own permission checks when they persist the returned URL. The route only
    authenticates the caller so the upload key can be scoped to their tenant.
    """
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"file type not allowed: {content_type or 'unknown'}",
        )

    max_bytes = settings.upload_max_bytes
    # Read at most one byte over the cap: if we get more, the upload is too
    # large and we reject it without ever holding the full oversized body.
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file too large: max {max_bytes} bytes",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="empty file",
        )

    key = _build_key(user.tenant_id, content_type)
    storage = get_storage()
    try:
        url = await storage.save(data, content_type, key)
    except (StorageError, NotImplementedError) as exc:
        # NotImplementedError surfaces when a stub S3/OSS backend is selected
        # without the SDK/creds — surface it as a 502 (bad gateway: upstream
        # storage misconfigured) so the client knows it isn't a request error.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return UploadResponse(
        url=url, key=key, size=len(data), content_type=content_type
    )
