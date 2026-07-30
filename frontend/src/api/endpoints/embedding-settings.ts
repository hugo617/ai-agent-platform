/**
 * endpoints/embedding-settings — embedding settings (platform + tenant, RAG priority 57).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  EmbeddingConfig,
  EmbeddingConfigUpdate,
} from "../types";
// ---------- embedding settings (platform + tenant, RAG priority 57) ----------
export async function fetchPlatformEmbeddingConfig(): Promise<EmbeddingConfig | null> {
  const { data } = await api.get<EmbeddingConfig | null>(
    "/settings/embedding/platform"
  );
  return data;
}

export async function updatePlatformEmbeddingConfig(
  payload: EmbeddingConfigUpdate
): Promise<EmbeddingConfig> {
  const { data } = await api.put<EmbeddingConfig>(
    "/settings/embedding/platform",
    payload
  );
  return data;
}

export async function fetchTenantEmbeddingConfig(): Promise<EmbeddingConfig | null> {
  const { data } = await api.get<EmbeddingConfig | null>(
    "/settings/embedding/tenant"
  );
  return data;
}

export async function updateTenantEmbeddingConfig(
  payload: EmbeddingConfigUpdate
): Promise<EmbeddingConfig> {
  const { data } = await api.put<EmbeddingConfig>(
    "/settings/embedding/tenant",
    payload
  );
  return data;
}

