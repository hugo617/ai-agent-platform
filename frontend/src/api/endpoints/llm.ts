/**
 * endpoints/llm — llm settings (platform + tenant).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  LlmConfig,
  LlmConfigUpdate,
} from "../types";
// ---------- llm settings (platform + tenant) ----------
export async function fetchPlatformLlmConfig(): Promise<LlmConfig | null> {
  const { data } = await api.get<LlmConfig | null>("/settings/llm/platform");
  return data;
}

export async function updatePlatformLlmConfig(
  payload: LlmConfigUpdate
): Promise<LlmConfig> {
  const { data } = await api.put<LlmConfig>("/settings/llm/platform", payload);
  return data;
}

export async function fetchTenantLlmConfig(): Promise<LlmConfig | null> {
  const { data } = await api.get<LlmConfig | null>("/settings/llm/tenant");
  return data;
}

export async function updateTenantLlmConfig(
  payload: LlmConfigUpdate
): Promise<LlmConfig> {
  const { data } = await api.put<LlmConfig>("/settings/llm/tenant", payload);
  return data;
}

export async function fetchEffectiveModels(): Promise<string[]> {
  const { data } = await api.get<string[]>("/settings/models");
  return data;
}

