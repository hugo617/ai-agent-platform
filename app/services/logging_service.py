"""Audit-log service — thin wrapper that writes SystemLog rows.

Called by user/auth services after each notable action (user CRUD, login, …).
Best-effort: a logging failure must never break the business transaction, so
exceptions are swallowed and (debug-logged) rather than propagated.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import SystemLog

logger = logging.getLogger(__name__)


class LoggingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        *,
        action: str,
        module: str,
        message: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        level: str = "info",
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Append a SystemLog row. Never raises — audit is best-effort."""
        try:
            self.db.add(
                SystemLog(
                    level=level,
                    action=action,
                    module=module,
                    message=message,
                    details_json=details,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    old_values=old_values,
                    new_values=new_values,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    ip=ip,
                    user_agent=user_agent,
                    session_id=session_id,
                )
            )
            await self.db.flush()
        except Exception:  # noqa: BLE001 — audit must not break the request
            logger.warning("failed to write audit log: %s", action, exc_info=True)
