/**
 * queries/logs — audit logs.
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  fetchLogs,
} from "@/api/endpoints";
import type {
  LogFilters,
} from "@/api/types";
// ---------- audit logs ----------

/** Paginated, filterable audit log. Refetches when filters change (new key). */
export function useLogs(filters: LogFilters) {
  return useQuery({
    queryKey: qk.logs(filters),
    queryFn: () => fetchLogs(filters),
    placeholderData: (prev) => prev, // keep previous page while fetching next
  });
}

