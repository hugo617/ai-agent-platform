/**
 * endpoints/tenants — tenants.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Tenant,
  TenantUpdate,
} from "../types";
// ---------- tenants ----------
// Two read scopes, mirroring the backend:
// - fetchTenants:   GET /tenants/   (any logged-in user; their own tenants)
// - fetchAllTenants: GET /tenants/all (super_admin only; every tenant + member_count)
export async function fetchTenants(): Promise<Tenant[]> {
  const { data } = await api.get<Tenant[]>("/tenants/");
  return data;
}

export async function fetchAllTenants(): Promise<Tenant[]> {
  const { data } = await api.get<Tenant[]>("/tenants/all");
  return data;
}

export async function createTenant(name: string): Promise<Tenant> {
  const { data } = await api.post<Tenant>("/tenants/", { name });
  return data;
}

export async function updateTenant(
  id: string,
  payload: TenantUpdate,
): Promise<Tenant> {
  const { data } = await api.put<Tenant>(`/tenants/${id}`, payload);
  return data;
}

