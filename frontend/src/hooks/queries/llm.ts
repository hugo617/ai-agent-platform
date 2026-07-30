/**
 * queries/llm — llm settings (platform + tenant).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  fetchEffectiveModels,
  fetchPlatformLlmConfig,
  fetchTenantLlmConfig,
  updatePlatformLlmConfig,
  updateTenantLlmConfig,
} from "@/api/endpoints";
import type {
  LlmConfigUpdate,
} from "@/api/types";
// ---------- llm settings (platform + tenant) ----------
export function usePlatformLlmConfig() {
  return useQuery({
    queryKey: qk.llmConfigPlatform,
    queryFn: fetchPlatformLlmConfig,
  });
}

export function useUpdatePlatformLlmConfig() {
  return useApiMutation(
    (payload: LlmConfigUpdate) => updatePlatformLlmConfig(payload),
    [qk.llmConfigPlatform],
  );
}

export function useTenantLlmConfig() {
  return useQuery({
    queryKey: qk.llmConfigTenant,
    queryFn: fetchTenantLlmConfig,
  });
}

export function useUpdateTenantLlmConfig() {
  return useApiMutation(
    (payload: LlmConfigUpdate) => updateTenantLlmConfig(payload),
    [qk.llmConfigTenant],
  );
}

export function useEffectiveModels() {
  return useQuery({
    queryKey: qk.effectiveModels,
    queryFn: fetchEffectiveModels,
  });
}

