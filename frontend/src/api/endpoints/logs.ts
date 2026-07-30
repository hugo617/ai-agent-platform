/**
 * endpoints/logs — audit logs.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  LogFilters,
  SystemLogListResponse,
} from "../types";
// ---------- audit logs ----------

/** GET /logs — paginated, filterable audit log. Store users are auto-scoped to
 * their tenant; super_admin/hq_staff may pass tenant_id to narrow. */
export async function fetchLogs(
  filters?: LogFilters,
): Promise<SystemLogListResponse> {
  const { data } = await api.get<SystemLogListResponse>("/logs/", {
    params: {
      user_id: filters?.user_id,
      action: filters?.action,
      resource_type: filters?.resource_type,
      tenant_id: filters?.tenant_id,
      date_from: filters?.date_from,
      date_to: filters?.date_to,
      limit: filters?.limit,
      offset: filters?.offset,
    },
  });
  return data;
}

