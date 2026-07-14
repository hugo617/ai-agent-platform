"""Pydantic schemas for in-app notifications.

``NotificationRead`` is the read-side DTO returned by ``GET /notifications``.
Trigger points (scheduler scan, recharge, role change) call
``NotificationService.create(**kwargs)`` directly rather than through a write
DTO, so there is no ``NotificationCreate`` here.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    """One notification row (read-side DTO)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    user_id: str | None = None
    type: str
    title: str
    content: str
    link: str | None = None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated notification envelope (mirrors SystemLogListResponse's shape)."""

    items: list[NotificationRead]
    total: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    """Lightweight reply for the bell's badge poll."""

    count: int
