/**
 * queries/customers — customers (global identity + per-store profile).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  createCustomerProfile,
  deleteCustomerProfile,
  fetchCustomerProfiles,
  fetchCustomerStatistics,
  fetchCustomerUsage,
  fetchCustomers,
  updateCustomerProfile,
} from "@/api/endpoints";
import type {
  CustomerProfileCreate,
  CustomerProfileUpdate,
} from "@/api/types";
// ---------- customers (global identity + per-store profile) ----------
// Store view hooks: this tenant's profile CRUD. Writes also invalidate the HQ
// list (customers) so a super_admin viewing the aggregate sees the change.
export function useCustomerProfiles(enabled: boolean = true) {
  return useQuery({
    queryKey: qk.customerProfiles,
    queryFn: fetchCustomerProfiles,
    enabled,
  });
}

export function useCreateCustomerProfile() {
  return useApiMutation(
    (payload: CustomerProfileCreate) => createCustomerProfile(payload),
    [qk.customerProfiles, qk.customers],
  );
}

export function useUpdateCustomerProfile() {
  return useApiMutation(
    ({
      id,
      payload,
    }: {
      id: string;
      payload: CustomerProfileUpdate;
    }) => updateCustomerProfile(id, payload),
    [qk.customerProfiles, qk.customers],
  );
}

export function useDeleteCustomerProfile() {
  return useApiMutation(
    (id: string) => deleteCustomerProfile(id),
    [qk.customerProfiles, qk.customers],
  );
}

// HQ view hooks: cross-store aggregation (super_admin only).
export function useCustomers() {
  return useQuery({ queryKey: qk.customers, queryFn: fetchCustomers });
}

// Token 费用管理系列 3/4: AI usage attributed to a customer (customer 360).
export function useCustomerUsage(id: string | null) {
  return useQuery({
    queryKey: qk.customerUsage(id ?? ""),
    queryFn: () => fetchCustomerUsage(id as string),
    enabled: !!id,
  });
}

// Customer count for the dashboard card (store profiles vs. HQ identities).
export function useCustomerStatistics() {
  return useQuery({
    queryKey: qk.customerStats,
    queryFn: fetchCustomerStatistics,
  });
}

