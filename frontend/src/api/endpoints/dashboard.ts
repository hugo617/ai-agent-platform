/**
 * endpoints/dashboard — dashboard analytics.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  DashboardOverview,
  DashboardTrends,
} from "../types";
// ---------- dashboard analytics ----------
// /dashboard/trends backs the activity bar chart on both the store and HQ
// dashboards; /dashboard/overview is super_admin-only (platform totals +
// per-tenant activity Top N). Trends reuses conversations:read; overview is
// require_super_admin on the backend.
export async function fetchDashboardTrends(days: number): Promise<DashboardTrends> {
  const { data } = await api.get<DashboardTrends>("/dashboard/trends", {
    params: { days },
  });
  return data;
}

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
  const { data } = await api.get<DashboardOverview>("/dashboard/overview");
  return data;
}

