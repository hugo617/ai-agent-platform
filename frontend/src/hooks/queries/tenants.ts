/**
 * queries/tenants — tenants.
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  createTenant,
  fetchAllTenants,
  fetchTenants,
  updateTenant,
} from "@/api/endpoints";
import type {
  TenantUpdate,
} from "@/api/types";
// ---------- tenants ----------
// useTenants/useCreateTenant serve the dashboard "my tenants" card (user-scoped
// GET /tenants/). The platform-level hooks below drive the store-management
// page (super_admin GET /tenants/all + PUT /tenants/{id}).
export function useTenants() {
  return useQuery({ queryKey: qk.tenants, queryFn: fetchTenants });
}

export function useCreateTenant() {
  return useApiMutation(
    (name: string) => createTenant(name),
    [qk.tenants, qk.allTenants],
  );
}

// Platform-wide tenant list (super_admin only). Also used by the groups page's
// tenant-attachment dropdown, where super_admin needs to see every store.
// `enabled` lets callers (e.g. the groups page, which non-super-admins view
// read-only) avoid firing a 403-guaranteed request.
export function useAllTenants(enabled = true) {
  return useQuery({
    queryKey: qk.allTenants,
    queryFn: fetchAllTenants,
    enabled,
  });
}

export function useUpdateTenant() {
  // Also refresh the user-scoped list: a rename should propagate to the
  // dashboard "my tenants" card if the edited tenant belongs to the user.
  return useApiMutation(
    ({ id, payload }: { id: string; payload: TenantUpdate }) =>
      updateTenant(id, payload),
    [qk.allTenants, qk.tenants],
  );
}

