import axios from "axios";
import { api } from "./client";
import type {
  Agent,
  AgentCreate,
  AgentUpdate,
  Member,
  MemberCreate,
  MemberUpdate,
  MeResponse,
  Tenant,
} from "./types";

// ---------- auth ----------
export async function fetchMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/auth/me");
  return data;
}

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

// ---------- tenants ----------
export async function fetchTenants(): Promise<Tenant[]> {
  const { data } = await api.get<Tenant[]>("/tenants/");
  return data;
}

export async function createTenant(name: string): Promise<Tenant> {
  const { data } = await api.post<Tenant>("/tenants/", { name });
  return data;
}

// ---------- agents ----------
export async function fetchAgents(): Promise<Agent[]> {
  const { data } = await api.get<Agent[]>("/agents/");
  return data;
}

export async function fetchAgent(id: string): Promise<Agent> {
  const { data } = await api.get<Agent>(`/agents/${id}`);
  return data;
}

export async function createAgent(payload: AgentCreate): Promise<Agent> {
  const { data } = await api.post<Agent>("/agents/", payload);
  return data;
}

export async function updateAgent(id: string, payload: AgentUpdate): Promise<Agent> {
  const { data } = await api.patch<Agent>(`/agents/${id}`, payload);
  return data;
}

export async function deleteAgent(id: string): Promise<void> {
  await api.delete(`/agents/${id}`);
}

// ---------- users (tenant members) ----------
export async function fetchMembers(): Promise<Member[]> {
  const { data } = await api.get<Member[]>("/users/");
  return data;
}

export async function addMember(payload: MemberCreate): Promise<Member> {
  const { data } = await api.post<Member>("/users/", payload);
  return data;
}

export async function updateMember(
  userId: string,
  payload: MemberUpdate
): Promise<Member> {
  const { data } = await api.patch<Member>(`/users/${userId}`, payload);
  return data;
}

export async function removeMember(userId: string): Promise<void> {
  await api.delete(`/users/${userId}`);
}
