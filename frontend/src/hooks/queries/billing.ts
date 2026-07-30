/**
 * queries/billing — billing (Token 费用管理系列 4/4).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPricing,
  deletePricing,
  fetchPricing,
  fetchTransactions,
  fetchUsage,
  fetchWallet,
  recharge,
  updatePricing,
} from "@/api/endpoints";
import type {
  ModelPricingUpsert,
  RechargeRequest,
} from "@/api/types";
// ---------- billing (Token 费用管理系列 4/4) ----------
// Wallet reads are split by scope (own tenant vs. any tenant).
// recharge + pricing writes invalidate the keys they touch so dashboards
// refetch immediately after a mutation.

/** The caller's own tenant wallet (null if the tenant has none yet). */
export function useWallet() {
  return useQuery({ queryKey: qk.wallet, queryFn: fetchWallet });
}

/** The caller's own tenant ledger (recharge/consume/refund/adjust). */
export function useTransactions() {
  return useQuery({
    queryKey: qk.transactions,
    queryFn: () => fetchTransactions(),
  });
}

/** Usage detail (drill-down): raw usage rows + token totals in one call. */
export function useUsage() {
  return useQuery({ queryKey: qk.usage, queryFn: () => fetchUsage() });
}

/** Super-admin: credit a tenant's wallet. Invalidates wallet + ledger. */
export function useRecharge() {
  const qc = useQueryClient();
  return useApiMutation(
    (payload: RechargeRequest) => recharge(payload),
    // Refresh the global wallet list + the caller-side ledger (super_admin may
    // be viewing transactions too).
    [qk.wallet, qk.transactions],
    // Plus the specific affected tenant's wallet (vars-derived key).
    (_data, { tenant_id }) =>
      qc.invalidateQueries({ queryKey: qk.walletByTenant(tenant_id) }),
  );
}

/** Effective pricing for the caller (tenant overrides + platform defaults). */
export function useModelPricing() {
  return useQuery({ queryKey: qk.pricing, queryFn: fetchPricing });
}

export function useCreatePricing() {
  return useApiMutation(
    (payload: ModelPricingUpsert) => createPricing(payload),
    [qk.pricing],
  );
}

export function useUpdatePricing() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: ModelPricingUpsert }) =>
      updatePricing(id, payload),
    [qk.pricing],
  );
}

export function useDeletePricing() {
  return useApiMutation(
    (id: string) => deletePricing(id),
    [qk.pricing],
  );
}

