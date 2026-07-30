/**
 * queries/dashboard — dashboard analytics.
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  fetchDashboardOverview,
  fetchDashboardTrends,
} from "@/api/endpoints";
// ---------- dashboard analytics ----------
// Trends backs the activity bar chart on both the store and HQ dashboards
// (store-scoped vs. cross-tenant aggregate — the backend splits on platform_role,
// so one hook serves both views). Overview is super_admin-only; callers gate it
// with `enabled` so a tenant user never fires a 403-guaranteed request.

/** Daily conversation + message counts for the last `days` days. */
export function useDashboardTrends(days: number) {
  return useQuery({
    queryKey: qk.dashboardTrends(days),
    queryFn: () => fetchDashboardTrends(days),
  });
}

/** super_admin HQ overview: platform totals + per-tenant activity Top N. */
export function useDashboardOverview(enabled = true) {
  return useQuery({
    queryKey: qk.dashboardOverview,
    queryFn: fetchDashboardOverview,
    enabled,
  });
}

