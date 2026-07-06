import { api } from "./client";
import type {
  Agent,
  AgentCreate,
  AgentUpdate,
  MeResponse,
  Tenant,
} from "./types";

// ---------- auth ----------
export async function fetchMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/auth/me");
  return data;
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
