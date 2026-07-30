/**
 * endpoints/api-tokens — api tokens (AtoA).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  ApiToken,
  ApiTokenCreate,
  ApiTokenCreated,
} from "../types";
// ---------- api tokens (AtoA) ----------
// Issue/list/revoke tokens for external agents (agenthub CLI). The plaintext
// token is returned ONLY by createApiToken — store it immediately, it can never
// be fetched again.
export async function fetchApiTokens(): Promise<ApiToken[]> {
  const { data } = await api.get<ApiToken[]>("/api-tokens");
  return data;
}

export async function createApiToken(
  payload: ApiTokenCreate
): Promise<ApiTokenCreated> {
  const { data } = await api.post<ApiTokenCreated>("/api-tokens", payload);
  return data;
}

export async function revokeApiToken(id: string): Promise<void> {
  await api.delete(`/api-tokens/${id}`);
}

