/**
 * queries/api-tokens — api tokens (AtoA).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  createApiToken,
  fetchApiTokens,
  revokeApiToken,
} from "@/api/endpoints";
import type {
  ApiTokenCreate,
} from "@/api/types";
// ---------- api tokens (AtoA) ----------
export function useApiTokens() {
  return useQuery({ queryKey: qk.apiTokens, queryFn: fetchApiTokens });
}

export function useCreateApiToken() {
  return useApiMutation(
    (payload: ApiTokenCreate) => createApiToken(payload),
    [qk.apiTokens],
  );
}

export function useRevokeApiToken() {
  return useApiMutation(
    (id: string) => revokeApiToken(id),
    [qk.apiTokens],
  );
}

