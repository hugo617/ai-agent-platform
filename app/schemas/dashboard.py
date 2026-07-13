"""Pydantic schemas for the dashboard (trends + HQ overview).

Aligns with the new ``/dashboard/trends`` and ``/dashboard/overview`` endpoints.
Trends is store-level (this tenant) or HQ-level (super_admin cross-tenant);
overview is super_admin-only (platform totals + per-tenant activity Top N).
"""

from pydantic import BaseModel


class TrendPoint(BaseModel):
    """One day of activity. ``date`` is a calendar day (YYYY-MM-DD)."""

    date: str
    conversations: int
    messages: int


class DashboardTrends(BaseModel):
    """Daily conversation + message counts for the last ``days`` days.

    Days with zero activity are included as zero-valued points so the chart
    stays a continuous timeline (oldest → newest). ``days`` echoes the request.
    """

    days: int
    points: list[TrendPoint]


class TenantActivityItem(BaseModel):
    """One store's activity for the HQ "store Top N" panel."""

    tenant_id: str
    tenant_name: str
    conversations: int


class PlatformTotals(BaseModel):
    """Platform-wide counts for the HQ overview cards."""

    tenants: int
    users: int
    conversations: int
    agents: int
    customers: int


class DashboardOverview(BaseModel):
    """super_admin HQ overview: platform totals + per-tenant activity Top N."""

    totals: PlatformTotals
    top_tenants: list[TenantActivityItem]
