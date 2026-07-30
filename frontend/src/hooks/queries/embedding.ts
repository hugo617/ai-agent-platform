/**
 * queries/embedding — embedding config (RAG, priority 57).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPlatformEmbeddingConfig,
  fetchTenantEmbeddingConfig,
  updatePlatformEmbeddingConfig,
  updateTenantEmbeddingConfig,
} from "@/api/endpoints";
import type {
  EmbeddingConfigUpdate,
} from "@/api/types";
// ---------- embedding config (RAG, priority 57) ----------
export function usePlatformEmbeddingConfig() {
  return useQuery({
    queryKey: qk.embeddingConfigPlatform,
    queryFn: fetchPlatformEmbeddingConfig,
  });
}

export function useUpdatePlatformEmbeddingConfig() {
  return useApiMutation(
    (payload: EmbeddingConfigUpdate) => updatePlatformEmbeddingConfig(payload),
    [qk.embeddingConfigPlatform],
  );
}

export function useTenantEmbeddingConfig() {
  return useQuery({
    queryKey: qk.embeddingConfigTenant,
    queryFn: fetchTenantEmbeddingConfig,
  });
}

export function useUpdateTenantEmbeddingConfig() {
  return useApiMutation(
    (payload: EmbeddingConfigUpdate) => updateTenantEmbeddingConfig(payload),
    [qk.embeddingConfigTenant],
  );
}

