/**
 * endpoints/auth — auth.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  MeResponse,
  PasswordChange,
  ProfileUpdate,
} from "../types";
// ---------- auth ----------
export async function fetchMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/auth/me");
  return data;
}

// Self-service profile edit (PUT /auth/me). Target user is always the caller
// (the token's user_id) — there is no user_id in the payload to honor.
export async function updateMe(payload: ProfileUpdate): Promise<MeResponse> {
  const { data } = await api.put<MeResponse>("/auth/me", payload);
  return data;
}

// Self-service password change (PUT /auth/me/password). Returns void on 204.
export async function changePassword(payload: PasswordChange): Promise<void> {
  await api.put("/auth/me/password", payload);
}

