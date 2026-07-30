/**
 * endpoints/permissions — permissions.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  PermissionItem,
  PermissionMatrix,
} from "../types";
// ---------- permissions ----------
// The matrix endpoint carries the catalogue (its `permissions` array), which
// is what the permissions-page uses. The catalogue endpoint is needed by views
// that want the permission list WITHOUT a selected role's matrix — the API
// token issue dialog uses it to render the scope picker (the grantor's role
// is implicit; we just need the catalogue of selectable scopes).
export async function fetchPermissionMatrix(): Promise<PermissionMatrix> {
  const { data } = await api.get<PermissionMatrix>("/permissions/matrix");
  return data;
}

export async function fetchPermissionCatalogue(
  type?: "api" | "menu"
): Promise<PermissionItem[]> {
  const params = type ? { type } : undefined;
  const { data } = await api.get<PermissionItem[]>("/permissions/catalogue", {
    params,
  });
  return data;
}

