"""Pydantic read schema for SystemLog (the audit log).

SystemLog is append-only and written by ``LoggingService.record``; this schema
backs the read-side ``GET /logs`` endpoint. Field names mirror the ORM
attribute names (notably ``details_json`` — the DB column is ``details`` but
the mapped Python attribute is ``details_json``).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SystemLogRead(BaseModel):
    """One audit-log row (read-side DTO)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    level: str
    action: str
    module: str
    message: str
    # Extra structured context. ORM attribute is ``details_json`` (the DB
    # column is named ``details``); the schema mirrors the Python attribute.
    details_json: dict[str, Any] | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    # before / after snapshots for update operations (JSONB on Postgres).
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    # The operator who performed the action (FK users). Named ``user_id`` on
    # the model — NOT ``operator_id``.
    user_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    user_agent: str | None = None
    ip: str | None = None
    request_id: str | None = None
    duration_ms: int | None = None
    created_at: datetime


class SystemLogListResponse(BaseModel):
    """Paginated audit-log envelope (mirrors UserListResponse's shape)."""

    items: list[SystemLogRead]
    total: int
    limit: int
    offset: int
