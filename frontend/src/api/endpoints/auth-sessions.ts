/**
 * endpoints/auth-2 — auth (local login + sessions).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  LoginHint,
  LoginRequest,
  TokenResponse,
} from "../types";
// ---------- auth (local login + sessions) ----------
export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", payload);
  return data;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

/** Demo login prefill (plan §4). Returns nulls in production — the backend
 * only returns real values when APP_ENV is development/testing. */
export async function fetchLoginHint(): Promise<LoginHint> {
  const { data } = await api.get<LoginHint>("/auth/login-hint");
  return data;
}

