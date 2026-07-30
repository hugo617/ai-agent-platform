/**
 * endpoints/dev — dev helpers (development env only).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  } from "../client";
import axios from "axios";
// ---------- dev helpers (development env only) ----------
// These hit backend root endpoints (not under /api/v1) that only exist when
// APP_ENV=development. They let the frontend log in without Logto configured.

export interface DevBootstrapResponse {
  tenant_id: string;
  user_id: string;
  exists: boolean;
}

export interface DevTokenResponse {
  access_token: string;
  expires_in: number;
}

// Same origin as the API (Vite proxies /dev and /oidc through to the backend
// in dev). See vite.config.ts.
const devHttp = axios.create({ baseURL: "", timeout: 15000 });

/** Create (idempotent) a dev tenant + user and seed casbin policies. */
export async function devBootstrap(payload: {
  sub?: string;
  tenant_name?: string;
  email?: string;
} = {}): Promise<DevBootstrapResponse> {
  const { data } = await devHttp.post<DevBootstrapResponse>("/dev/bootstrap", payload);
  return data;
}

/** Mint a short-lived dev JWT for local login. */
export async function devToken(payload: {
  sub?: string;
  tenant_id: string;
  email?: string;
}): Promise<DevTokenResponse> {
  const { data } = await devHttp.post<DevTokenResponse>("/dev/token", payload);
  return data;
}

/** One-click dev login: bootstrap → mint token. Returns the access token. */
export async function devLogin(): Promise<string> {
  const sub = "dev-user";
  const boot = await devBootstrap({
    sub,
    tenant_name: "开发租户",
    email: "dev@example.com",
  });
  const tok = await devToken({
    sub,
    tenant_id: boot.tenant_id,
    email: "dev@example.com",
  });
  return tok.access_token;
}

