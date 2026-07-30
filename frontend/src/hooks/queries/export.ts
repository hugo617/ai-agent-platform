/**
 * queries/export — CSV export (priority 55).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { useMutation } from "@tanstack/react-query";
import {
  exportEntity,
} from "@/api/endpoints";
import type {
  ExportEntity,
  ExportParams,
} from "@/api/endpoints";
// ---------- CSV export (priority 55) ----------
// Triggers GET /exports/{entity} and saves the streamed CSV via downloadBlob.
// The mutation is just a wrapper around exportEntity + the browser download —
// no cache to invalidate (export is a read-only side-effect). The page wires
// the toast on success/error and supplies the filename based on the entity.
export function useExportCsv() {
  return useMutation({
    mutationFn: (args: {
      entity: ExportEntity;
      params?: ExportParams;
      filename: string;
    }) => exportEntityAndDownload(args.entity, args.params, args.filename),
  });
}

async function exportEntityAndDownload(
  entity: ExportEntity,
  params: ExportParams | undefined,
  filename: string,
): Promise<void> {
  const blob = await exportEntity(entity, params);
  // Lazy import keeps the download helper out of the bundle for callers that
  // only need the other hooks (the helper touches `document`, so isolating it
  // also keeps the module SSR-safe in case of future server rendering).
  const { downloadBlob } = await import("@/lib/download");
  downloadBlob(blob, filename);
}
