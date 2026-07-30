/**
 * endpoints/roles — roles.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Role,
  RoleCreate,
  RoleLabel,
  RolePermissionGrant,
  RolePermissionRead,
  RoleUpdate,
} from "../types";
// ---------- roles ----------
export async function fetchRoles(): Promise<Role[]> {
  const { data } = await api.get<Role[]>("/roles/");
  return data;
}

export async function fetchRoleLabels(): Promise<RoleLabel[]> {
  const { data } = await api.get<RoleLabel[]>("/roles/label");
  return data;
}

export async function createRole(payload: RoleCreate): Promise<Role> {
  const { data } = await api.post<Role>("/roles/", payload);
  return data;
}

export async function updateRole(id: string, payload: RoleUpdate): Promise<Role> {
  const { data } = await api.put<Role>(`/roles/${id}`, payload);
  return data;
}

export async function deleteRole(id: string): Promise<void> {
  await api.delete(`/roles/${id}`);
}

// role ↔ permission grants (SCD2; writes resync casbin on the backend)
export async function fetchRolePermissions(
  id: string
): Promise<RolePermissionRead[]> {
  const { data } = await api.get<RolePermissionRead[]>(`/roles/${id}/permissions`);
  return data;
}

export async function grantRolePermission(
  id: string,
  payload: RolePermissionGrant
): Promise<RolePermissionRead> {
  const { data } = await api.post<RolePermissionRead>(
    `/roles/${id}/permissions`,
    payload
  );
  return data;
}

export async function revokeRolePermission(
  id: string,
  permissionId: string
): Promise<void> {
  await api.delete(`/roles/${id}/permissions/${permissionId}`);
}

