/**
 * endpoints/agents — agents.
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Agent,
  AgentCreate,
  AgentStatistics,
  AgentUpdate,
} from "../types";
// ---------- agents ----------
export async function fetchAgents(): Promise<Agent[]> {
  const { data } = await api.get<Agent[]>("/agents/");
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

// Agent count for the dashboard card. Store users count their tenant; super_admin
// counts every tenant (the service splits on platform_role).
export async function fetchAgentStatistics(): Promise<AgentStatistics> {
  const { data } = await api.get<AgentStatistics>("/agents/statistics");
  return data;
}

