"""Schemas for the global cross-entity search endpoint.

Each entity returns a lightweight DTO (``id`` + ``label`` + ``type``) — just
enough for the top-bar dropdown to render a clickable row and navigate to the
right detail page. The aggregator groups results by entity type so the UI can
render them as categorized sections.
"""

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    """One lightweight search hit.

    - ``id``    — the entity's primary key (navigate target).
    - ``label`` — the primary human-readable field (name / title / identity).
    - ``type``  — discriminator so the UI can pick an icon + route, kept on the
      item (not just the group key) so a flat list of mixed hits still works.
    """

    id: str
    label: str
    type: str


class GlobalSearchResult(BaseModel):
    """Grouped cross-entity search response.

    Every entity key is always present (possibly an empty list) so the frontend
    can render stable sections without a key-existence check. ``users`` and
    ``tenants`` are only populated for cross-tenant viewers (super_admin /
    hq_staff); for store users they stay empty.
    """

    agents: list[SearchResultItem] = []
    customers: list[SearchResultItem] = []
    conversations: list[SearchResultItem] = []
    users: list[SearchResultItem] = []
    tenants: list[SearchResultItem] = []
