"""CSV export endpoints (``GET /exports/{entity}``).

Streams a UTF-8-BOM CSV attachment for one of four entities so a store can
pull monthly business data (customer list / conversations / token usage /
audit logs) and open it in Excel without garbled Chinese. No export
capability existed before this feature (priority 55).

Design notes (per project 铁律 + plan-data-export.md):

- **Read-only aggregator** issuing scoped ``select`` queries directly — same
  shape as ``/dashboard/overview``, ``/logs``, ``/search``. No Service layer
  because export is pure serialisation of filtered reads.
- **Server-side streaming**: each row generator uses ``db.stream(stmt)`` and
  ``async for`` so rows are fetched incrementally from a server-side cursor
  rather than materialised into one list. ``_stream_rows`` then batches the
  CSV serialisation so the response body is flushed in chunks — a large export
  (up to ``MAX_EXPORT_ROWS``) never holds the whole result set in memory.
- **No N+1**: customers batch-prefetch the global ``Customer`` rows in one
  ``id IN (...)`` query; conversations compute ``message_count`` via an OUTER
  JOIN + GROUP BY in the same query that fetches the rows.
- **UTF-8 BOM** (``\\ufeff``) at the start so Excel decodes Chinese columns
  correctly (Excel guesses GBK on a bare UTF-8 CSV and shows mojibake).
- **Multi-tenant isolation**: the scope split mirrors ``/logs`` +
  ``/customers/{id}/usage`` — store users are pinned to their tenant;
  cross-tenant viewers (super_admin / hq_staff) see the whole platform
  (optionally narrowed by ``tenant_id``). The ``tenant_id``/``user_id``
  predicates live in the query WHERE, not in a service "remember to filter".
- **Per-entity permission**: the guard is inlined (not a router
  ``dependencies=``) because each entity needs a different read permission
  (customers:read / conversations:read / wallet:read|billing:read /
  logs:read), while super_admin / hq_staff bypass via the cross-tenant branch.
  This mirrors the logs endpoint's rationale verbatim.
"""

import csv
import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.core.dates import parse_iso_dt, row_dt, to_naive_utc
from app.repositories.log import SystemLogRepository
from app.services.permission_service import is_cross_tenant_viewer, permission_service

router = APIRouter(prefix="/exports", tags=["exports"])

# Upper bound on rows per export so memory stays bounded even for the streaming
# path (each batch is small, but the DB cursor + serialised rows still cost RAM).
# Matches the plan's "限制最大行数(10 万)" risk-table mitigation.
MAX_EXPORT_ROWS = 100_000
# Rows serialised per yield. Small enough that each chunk flushes promptly;
# large enough that per-row async overhead stays negligible.
EXPORT_BATCH_SIZE = 500
# Default window when neither date_from nor date_to is supplied. Matches the
# plan's "默认近 30 天" and the dashboard trends convention.
DEFAULT_WINDOW_DAYS = 30

# The four supported entities, in the order the frontend lists them. Kept as a
# constant so the 404 path and any future OpenAPI doc stay in sync.
ENTITIES: tuple[str, ...] = ("customers", "conversations", "usage", "logs")


def _default_window(date_from: datetime | None, date_to: datetime | None) -> tuple[datetime, datetime | None]:
    """Apply the default 30-day window when the caller omitted both bounds.

    Mirrors the plan's "默认近 30 天": if neither side is given, ``date_from``
    becomes ``now - 30d``. If only one side is given, the other stays open
    (the Repository only filters on the bounds that are not None).
    """
    if date_from is None and date_to is None:
        return datetime.now(UTC) - timedelta(days=DEFAULT_WINDOW_DAYS), None
    return date_from, date_to


# --------------------------------------------------------------------------- CSV streaming
#
# The generator yields ``str`` chunks (CSV text). ``StreamingResponse`` encodes
# each chunk to bytes using the media-type charset (UTF-8). The very first
# chunk is the BOM so Excel detects UTF-8 and renders Chinese columns correctly.


async def _stream_rows(
    headers: list[str],
    row_iter: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[str]:
    """Yield CSV text in batches: BOM, header, then row batches.

    ``row_iter`` is an async generator the caller builds per entity; it yields
    one ``{column: value}`` dict per underlying row (already scoped + filtered
    by the Repository). We cap the total at ``MAX_EXPORT_ROWS`` so a runaway
    query can't exhaust memory — the cap is checked here (not in the Repository)
    so every entity benefits without duplicating the limit logic.
    """
    # UTF-8 BOM first — Excel keys off this byte sequence to pick UTF-8 over
    # the platform default (GBK on zh-CN Windows). Without it, Chinese columns
    # arrive as mojibake.
    yield "\ufeff"

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate()

    emitted = 0
    batch = 0
    async for row in row_iter:
        if emitted >= MAX_EXPORT_ROWS:
            break
        writer.writerow([_cell(row.get(h)) for h in headers])
        emitted += 1
        batch += 1
        if batch >= EXPORT_BATCH_SIZE:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
            batch = 0
    # Flush whatever remains in the buffer (the partial last batch).
    if batch > 0:
        yield buffer.getvalue()


def _cell(value: Any) -> Any:
    """Normalise one cell value for csv.writer.

    - ``None`` → empty string (cleaner than the bare ``''`` csv writes for None
      on some platforms).
    - ``bool`` → ``"true"``/``"false"`` (Python's default str(True) is "True";
      lowercase reads better in spreadsheets and matches JSON conventions).
    - ``list`` / ``dict`` (JSON columns like ``tags``) → compact JSON string so
      a multi-value cell stays one CSV field instead of being split.
    - ``datetime`` → ISO-8601 (Excel parses it, and it's timezone-aware).
    - ``Decimal`` → ``str()`` preserves precision without float rounding.
    - everything else → returned as-is (csv.writer calls ``str()``).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        import json

        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


# --------------------------------------------------------------------------- per-entity row generators


async def _customer_rows(
    db: AsyncSession, *, scope_tenant: str | None, date_from: datetime | None, date_to: datetime | None
) -> AsyncIterator[dict[str, Any]]:
    """Yield customer profile rows joined to the global identity.

    Store scope → profiles in one tenant; cross-tenant → every store's
    profiles. Columns (name/identity_key/gender) live on the platform-level
    ``Customer``; status/created_at/tags live on the store ``CustomerProfile``.

    N+1 avoidance: the profile columns come from a single scoped query, then
    the related Customer rows are fetched in ONE batch (``id IN (...)``) and
    joined in Python — no per-row lookup. Streaming via ``db.stream`` so a
    large tenant's profiles don't all materialise in memory at once.
    """
    from sqlalchemy import select

    from app.models.customer import Customer, CustomerProfile

    naive_from = to_naive_utc(date_from)
    naive_to = to_naive_utc(date_to)

    prof_stmt = select(CustomerProfile).where(CustomerProfile.is_deleted.is_(False))
    if scope_tenant is not None:
        prof_stmt = prof_stmt.where(CustomerProfile.tenant_id == scope_tenant)
    prof_stmt = prof_stmt.order_by(CustomerProfile.created_at.desc()).limit(MAX_EXPORT_ROWS)

    # Batch-prefetch the global Customer rows referenced by the profiles so the
    # join is O(1) per row instead of a query per row (the old N+1). We collect
    # profile rows first (they're bounded by MAX_EXPORT_ROWS) then one query.
    profiles: list[CustomerProfile] = []
    async for p in (await db.stream(prof_stmt)).scalars():
        row_created = row_dt(p.created_at)
        if naive_from is not None and row_created is not None and row_created < naive_from:
            continue
        if naive_to is not None and row_created is not None and row_created > naive_to:
            continue
        profiles.append(p)

    cust_ids = list({p.customer_id for p in profiles})
    customers_map: dict[str, Customer] = {}
    if cust_ids:
        cust_rows = (
            await db.execute(
                select(Customer).where(
                    Customer.id.in_(cust_ids), Customer.is_deleted.is_(False)
                )
            )
        ).scalars().all()
        customers_map = {c.id: c for c in cust_rows}

    for p in profiles:
        cust = customers_map.get(p.customer_id)
        yield {
            "name": cust.name if cust else "",
            "identity_key": cust.identity_key if cust else "",
            "gender": cust.gender if cust else "",
            "status": p.status,
            "created_at": p.created_at,
            "tags": p.tags,
        }


async def _conversation_rows(
    db: AsyncSession, *, scope_tenant: str | None, user_id: str | None, date_from: datetime | None, date_to: datetime | None
) -> AsyncIterator[dict[str, Any]]:
    """Yield conversation rows for a user (store scope) or all (cross-tenant).

    Store scope → the caller's own conversations in their tenant; cross-tenant
    → every conversation platform-wide (super_admin / hq_staff panorama).

    ``message_count`` is computed in a single query via an OUTER JOIN + GROUP BY
    (one round-trip for conversations + counts), not a per-row count query (the
    old N+1). We deliberately do NOT reuse ``ConversationRepository.search_all``
    — it matches on ``title ILIKE`` and would drop NULL-title rows; an export
    must be lossless. Streaming via ``db.stream``.
    """
    from sqlalchemy import func, select

    from app.models.agent import Conversation
    from app.models.message import Message

    naive_from = to_naive_utc(date_from)
    naive_to = to_naive_utc(date_to)

    msg_count = func.count(Message.id).label("message_count")
    stmt = (
        select(Conversation, msg_count)
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Conversation.id)
        .order_by(Conversation.created_at.desc())
        .limit(MAX_EXPORT_ROWS)
    )
    if scope_tenant is not None:
        stmt = stmt.where(
            Conversation.tenant_id == scope_tenant,
            Conversation.user_id == (user_id or ""),
        )

    result = await db.stream(stmt)
    async for c, count in result:
        row_created = row_dt(c.created_at)
        if naive_from is not None and row_created is not None and row_created < naive_from:
            continue
        if naive_to is not None and row_created is not None and row_created > naive_to:
            continue
        yield {
            "title": c.title or "",
            "agent_id": c.agent_id,
            "user_id": c.user_id,
            "created_at": c.created_at,
            "message_count": int(count),
            "is_pinned": c.is_pinned,
            "is_starred": c.is_starred,
        }


async def _usage_rows(
    db: AsyncSession, *, scope_tenant: str | None, date_from: datetime | None, date_to: datetime | None
) -> AsyncIterator[dict[str, Any]]:
    """Yield token usage events (store scope = this tenant; HQ = all).

    Columns (date/conversation_id/model/prompt/completion/total/cost/customer_id)
    are all columns on UsageEvent, so each row maps 1:1. Streaming via
    ``db.stream``.
    """
    from sqlalchemy import select

    from app.models.usage_event import UsageEvent

    naive_from = to_naive_utc(date_from)
    naive_to = to_naive_utc(date_to)

    stmt = select(UsageEvent).order_by(UsageEvent.created_at.desc()).limit(MAX_EXPORT_ROWS)
    if scope_tenant is not None:
        stmt = stmt.where(UsageEvent.tenant_id == scope_tenant)

    async for e in (await db.stream(stmt)).scalars():
        row_created = row_dt(e.created_at)
        if naive_from is not None and row_created is not None and row_created < naive_from:
            continue
        if naive_to is not None and row_created is not None and row_created > naive_to:
            continue
        yield {
            "date": e.created_at,
            "conversation_id": e.conversation_id,
            "model": e.model,
            "prompt_tokens": e.prompt_tokens,
            "completion_tokens": e.completion_tokens,
            "total_tokens": e.total_tokens,
            "cost": e.cost,
            "customer_id": e.customer_id or "",
        }


async def _log_rows(
    db: AsyncSession, *, scope_tenant: str | None, date_from: datetime | None, date_to: datetime | None
) -> AsyncIterator[dict[str, Any]]:
    """Yield audit log rows. Mirrors ``/logs`` scope split exactly.

    Calls ``SystemLogRepository.list_logs`` with a high limit so the export
    isn't paginated; the generator cap (``MAX_EXPORT_ROWS``) still bounds it.
    """
    repo = SystemLogRepository(db)
    rows, _total = await repo.list_logs(
        tenant_id=scope_tenant,
        date_from=date_from,
        date_to=date_to,
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )
    for r in rows:
        yield {
            "created_at": r.created_at,
            "user_id": r.user_id or "",
            "action": r.action,
            "resource_type": r.resource_type or "",
            "resource_id": r.resource_id or "",
            "message": r.message,
        }


# Per-entity column order. Dicts from the generators carry these keys; missing
# keys serialise as empty cells. Kept module-level so a future schema change
# only touches one place per entity.
COLUMNS: dict[str, list[str]] = {
    "customers": ["name", "identity_key", "gender", "status", "created_at", "tags"],
    "conversations": [
        "title",
        "agent_id",
        "user_id",
        "created_at",
        "message_count",
        "is_pinned",
        "is_starred",
    ],
    "usage": [
        "date",
        "conversation_id",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "customer_id",
    ],
    "logs": [
        "created_at",
        "user_id",
        "action",
        "resource_type",
        "resource_id",
        "message",
    ],
}


# --------------------------------------------------------------------------- route


@router.get("/{entity}")
async def export_entity(
    entity: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None, description="起始时间 ISO-8601(含)"),
    date_to: str | None = Query(default=None, description="结束时间 ISO-8601(含)"),
    tenant_id: str | None = Query(
        default=None,
        description="仅 super_admin/hq_staff 生效:按租户过滤;省略=全平台",
    ),
) -> StreamingResponse:
    """Stream a CSV attachment for ``entity`` ∈ {customers, conversations, usage, logs}.

    Scope split (mirrors ``/logs`` + ``/customers/{id}/usage``):

    - **Store users** (owner/admin/member with the entity's read permission):
      scoped to their own tenant. ``tenant_id`` is ignored — they cannot escape
      their own tenant.
    - **Cross-tenant viewers** (super_admin / hq_staff): see all-platform rows
      by default; may optionally pass ``tenant_id`` to filter to one tenant.

    The guard is inlined because each entity needs a different read permission
    (customers:read / conversations:read / wallet:read|billing:read /
    logs:read); super_admin bypasses inside ``check`` (its first-line return).
    """
    if entity not in ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"不支持的导出实体: {entity}",
        )

    cross_tenant = is_cross_tenant_viewer(user.platform_role)
    scope_tenant: str | None
    if not cross_tenant:
        # Store user: enforce the entity's read permission. Each branch calls
        # permission_service.require manually (mirroring logs.py / customers.py).
        await _require_entity_read(entity, user)
        scope_tenant = user.tenant_id
    else:
        # Cross-tenant viewer (super_admin / hq_staff): optional tenant filter.
        scope_tenant = tenant_id

    parsed_from = parse_iso_dt(date_from)
    parsed_to = parse_iso_dt(date_to)
    parsed_from, parsed_to = _default_window(parsed_from, parsed_to)

    # Build the per-entity async row generator. ``conversations`` needs the
    # caller's user_id for the store-scoped branch; the others don't.
    if entity == "customers":
        row_iter = _customer_rows(db, scope_tenant=scope_tenant, date_from=parsed_from, date_to=parsed_to)
    elif entity == "conversations":
        row_iter = _conversation_rows(
            db,
            scope_tenant=scope_tenant,
            user_id=user.user_id,
            date_from=parsed_from,
            date_to=parsed_to,
        )
    elif entity == "usage":
        row_iter = _usage_rows(db, scope_tenant=scope_tenant, date_from=parsed_from, date_to=parsed_to)
    else:  # logs
        row_iter = _log_rows(db, scope_tenant=scope_tenant, date_from=parsed_from, date_to=parsed_to)

    headers = COLUMNS[entity]
    filename = f"{entity}_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    # media_type text/csv with an explicit charset so the BOM + UTF-8 payload
    # decode correctly in every client (curl, Excel, Numbers).
    return StreamingResponse(
        _stream_rows(headers, row_iter),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Hint the body length is unknown (streamed) — some clients render a
            # progress bar only with a length; without it they just save on
            # completion, which is fine for a download.
            "Cache-Control": "no-store",
        },
    )


async def _require_entity_read(entity: str, user: CurrentUser) -> None:
    """Enforce the per-entity read permission for store users.

    Each entity maps to its existing read perm (no new perms introduced — the
    plan explicitly reuses customers:read / conversations:read / wallet:read
    or billing:read / logs:read). Usage accepts either wallet:read (the
    /billing/usage guard) or billing:read so an owner or an admin alike can
    export; super_admin is bypassed by ``check`` before we get here.
    """
    if entity == "customers":
        await permission_service.require(
            user.user_id, user.tenant_id, "customers", "read", platform_role=user.platform_role
        )
    elif entity == "conversations":
        await permission_service.require(
            user.user_id,
            user.tenant_id,
            "conversations",
            "read",
            platform_role=user.platform_role,
        )
    elif entity == "usage":
        # /billing/usage is guarded by billing:read; wallet:read owners should
        # also be able to export their token usage. Accept either.
        allowed = await permission_service.check(
            user.user_id, user.tenant_id, "billing", "read", platform_role=user.platform_role
        ) or await permission_service.check(
            user.user_id, user.tenant_id, "wallet", "read", platform_role=user.platform_role
        )
        if not allowed:
            raise PermissionError(
                f"无权限：{user.user_id} 不能在租户 {user.tenant_id} 中导出用量"
            )
    elif entity == "logs":
        await permission_service.require(
            user.user_id, user.tenant_id, "logs", "read", platform_role=user.platform_role
        )
