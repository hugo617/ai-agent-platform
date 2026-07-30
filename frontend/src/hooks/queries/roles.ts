/**
 * queries/roles — roles (full CRUD + permission grants).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createRole,
  deleteRole,
  fetchPermissionCatalogue,
  fetchPermissionMatrix,
  fetchRoleLabels,
  fetchRolePermissions,
  fetchRoles,
  grantRolePermission,
  revokeRolePermission,
  updateRole,
} from "@/api/endpoints";
import type {
  RoleCreate,
  RolePermissionGrant,
  RoleUpdate,
} from "@/api/types";
// ---------- roles (full CRUD + permission grants) ----------
export function useRoles() {
  return useQuery({ queryKey: qk.roles, queryFn: fetchRoles });
}

export function useRoleLabels() {
  return useQuery({ queryKey: qk.roleLabels, queryFn: fetchRoleLabels });
}

export function useCreateRole() {
  return useApiMutation(
    (payload: RoleCreate) => createRole(payload),
    // The matrix endpoint returns roles[], so refresh it alongside the list
    // (consistent with useUpdateRole below).
    [["roles"], qk.permissionMatrix],
  );
}

export function useUpdateRole() {
  // data_scope lives on the role and the matrix endpoint returns roles[],
  // so refresh the matrix too (the permissions-page data_scope selector
  // goes through this hook).
  return useApiMutation(
    ({ id, payload }: { id: string; payload: RoleUpdate }) =>
      updateRole(id, payload),
    [["roles"], qk.permissionMatrix],
  );
}

export function useDeleteRole() {
  return useApiMutation(
    (id: string) => deleteRole(id),
    [["roles"], qk.permissionMatrix],
  );
}

// role ↔ permission grants
export function useRolePermissions(roleId: string | null) {
  return useQuery({
    queryKey: qk.rolePermissions(roleId ?? ""),
    queryFn: () => fetchRolePermissions(roleId as string),
    enabled: !!roleId,
  });
}

// aggregated role × permission matrix (drives the permissions page)
export function usePermissionMatrix() {
  return useQuery({
    queryKey: qk.permissionMatrix,
    queryFn: fetchPermissionMatrix,
  });
}

// permission catalogue — the flat list of permission items, optionally
// filtered by type ("api" / "menu"). The API token issue dialog uses the
// "api" filter to render the scope picker (the selectable scopes a restricted
// token can be narrowed to).
export function usePermissionsCatalogue(type?: "api" | "menu") {
  return useQuery({
    queryKey: qk.permissionCatalogue(type),
    queryFn: () => fetchPermissionCatalogue(type),
  });
}

export function useGrantRolePermission() {
  const qc = useQueryClient();
  return useApiMutation(
    ({
      roleId,
      payload,
    }: {
      roleId: string;
      payload: RolePermissionGrant;
    }) => grantRolePermission(roleId, payload),
    [qk.permissionMatrix],
    (_data, { roleId }) =>
      qc.invalidateQueries({ queryKey: qk.rolePermissions(roleId) }),
  );
}

export function useRevokeRolePermission() {
  const qc = useQueryClient();
  return useApiMutation(
    ({
      roleId,
      permissionId,
    }: {
      roleId: string;
      permissionId: string;
    }) => revokeRolePermission(roleId, permissionId),
    [qk.permissionMatrix],
    (_data, { roleId }) =>
      qc.invalidateQueries({ queryKey: qk.rolePermissions(roleId) }),
  );
}

