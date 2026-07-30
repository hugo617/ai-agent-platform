/**
 * endpoints/export — CSV export (priority 55).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
// ---------- CSV export (priority 55) ----------
// GET /exports/{entity} streams a UTF-8-BOM CSV attachment for one of
// customers / conversations / usage / logs. The response is a binary stream
// (axios responseType: "blob"), so callers hand the Blob to downloadBlob().
// Store users are auto-scoped to their tenant; super_admin / hq_staff may pass
// tenant_id to narrow. Date params are optional (default: last 30 days).

export type ExportEntity = "customers" | "conversations" | "usage" | "logs";

export interface ExportParams {
  date_from?: string;
  date_to?: string;
  /** super_admin / hq_staff only: narrow to one tenant. */
  tenant_id?: string;
}

/** Fetch a CSV export as a Blob. The caller triggers the browser download. */
export async function exportEntity(
  entity: ExportEntity,
  params?: ExportParams,
): Promise<Blob> {
  const resp = await api.get<Blob>(`/exports/${entity}`, {
    params: {
      date_from: params?.date_from,
      date_to: params?.date_to,
      tenant_id: params?.tenant_id,
    },
    responseType: "blob",
  });
  return resp.data;
}
