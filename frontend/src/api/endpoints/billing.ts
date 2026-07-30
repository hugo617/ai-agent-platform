/**
 * endpoints/billing — billing (Token 费用管理系列 4/4).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  ModelPricing,
  ModelPricingUpsert,
  RechargeRequest,
  UsageDetail,
  Wallet,
  WalletTransaction,
} from "../types";
// ---------- billing (Token 费用管理系列 4/4) ----------
// Wallet read is split by scope, mirroring the backend:
// - fetchWallet:          GET /billing/wallet        (caller's own tenant)
// - fetchWalletByTenant:  GET /billing/wallet/{id}   (super_admin, any tenant)
// The own-wallet endpoint may return null (a brand-new tenant with no wallet);
// callers should handle null.
export async function fetchWallet(): Promise<Wallet | null> {
  const { data } = await api.get<Wallet | null>("/billing/wallet");
  return data;
}

export async function fetchWalletByTenant(
  tenantId: string,
): Promise<Wallet | null> {
  const { data } = await api.get<Wallet | null>(`/billing/wallet/${tenantId}`);
  return data;
}

// Caller's own tenant ledger. limit/offset match the backend Query defaults.
export async function fetchTransactions(params?: {
  limit?: number;
  offset?: number;
}): Promise<WalletTransaction[]> {
  const { data } = await api.get<WalletTransaction[]>("/billing/transactions", {
    params: { limit: params?.limit, offset: params?.offset },
  });
  return data;
}

// Usage detail (drill-down for dashboards). Returns rows + summary in one call.
export async function fetchUsage(params?: {
  limit?: number;
  offset?: number;
}): Promise<UsageDetail> {
  const { data } = await api.get<UsageDetail>("/billing/usage", {
    params: { limit: params?.limit, offset: params?.offset },
  });
  return data;
}

// Super-admin: credit a tenant's wallet. Returns the new ledger row.
export async function recharge(
  payload: RechargeRequest,
): Promise<WalletTransaction> {
  const { data } = await api.post<WalletTransaction>(
    "/billing/recharge",
    payload,
  );
  return data;
}

// Effective pricing for the caller (tenant overrides + platform defaults).
export async function fetchPricing(): Promise<ModelPricing[]> {
  const { data } = await api.get<ModelPricing[]>("/billing/pricing");
  return data;
}

// Idempotent on (tenant_id, model): re-POSTing the same scope+model updates.
export async function createPricing(
  payload: ModelPricingUpsert,
): Promise<ModelPricing> {
  const { data } = await api.post<ModelPricing>("/billing/pricing", payload);
  return data;
}

export async function updatePricing(
  id: string,
  payload: ModelPricingUpsert,
): Promise<ModelPricing> {
  const { data } = await api.put<ModelPricing>(
    `/billing/pricing/${id}`,
    payload,
  );
  return data;
}

// Soft-delete (deactivates the row) so historical charges stay interpretable.
export async function deletePricing(id: string): Promise<void> {
  await api.delete(`/billing/pricing/${id}`);
}

