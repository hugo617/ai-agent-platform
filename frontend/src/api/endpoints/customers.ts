/**
 * endpoints/customers — customers (global identity + per-store profile).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  CustomerProfileCreate,
  CustomerProfileRead,
  CustomerProfileUpdate,
  CustomerRead,
  CustomerStatistics,
  CustomerUsage,
} from "../types";
// ---------- customers (global identity + per-store profile) ----------
// Two access patterns: store view (tenant-scoped CRUD on this store's profiles)
// and HQ view (cross-store aggregation, super_admin only).
//
// Store view: /customers/profiles/  — list/create/update/delete this tenant's
// profiles. If identity_key already exists globally, the backend reuses the
// existing Customer and creates only a new Profile (HTTP 201 either way).
export async function fetchCustomerProfiles(): Promise<CustomerProfileRead[]> {
  const { data } = await api.get<CustomerProfileRead[]>("/customers/profiles/");
  return data;
}

export async function createCustomerProfile(
  payload: CustomerProfileCreate,
): Promise<CustomerProfileRead> {
  const { data } = await api.post<CustomerProfileRead>(
    "/customers/profiles/",
    payload,
  );
  return data;
}

export async function updateCustomerProfile(
  id: string,
  payload: CustomerProfileUpdate,
): Promise<CustomerProfileRead> {
  const { data } = await api.put<CustomerProfileRead>(
    `/customers/profiles/${id}`,
    payload,
  );
  return data;
}

export async function deleteCustomerProfile(id: string): Promise<void> {
  await api.delete(`/customers/profiles/${id}`);
}

// HQ view: /customers/ and /customers/{id}/aggregate — cross-store list/detail
// (super_admin only). The list endpoint already returns every store's profiles
// expanded, so aggregate detail is a convenience for one customer.
export async function fetchCustomers(): Promise<CustomerRead[]> {
  const { data } = await api.get<CustomerRead[]>("/customers/");
  return data;
}

export async function fetchCustomerUsage(
  id: string,
): Promise<CustomerUsage> {
  const { data } = await api.get<CustomerUsage>(`/customers/${id}/usage`);
  return data;
}

// Customer count for the dashboard card. Store scope = this store's profile
// counts; HQ scope (super_admin) = global identity counts. Mirrors the
// list_profiles dual-view split.
export async function fetchCustomerStatistics(): Promise<CustomerStatistics> {
  const { data } = await api.get<CustomerStatistics>("/customers/statistics");
  return data;
}

