/**
 * queries/agents — agents.
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  createAgent,
  deleteAgent,
  fetchAgentStatistics,
  fetchAgents,
  updateAgent,
} from "@/api/endpoints";
import type {
  AgentCreate,
  AgentUpdate,
} from "@/api/types";
// ---------- agents ----------
export function useAgents() {
  return useQuery({ queryKey: qk.agents, queryFn: fetchAgents });
}

// Agent count for the dashboard card (store-scoped or HQ aggregate).
export function useAgentStatistics() {
  return useQuery({ queryKey: qk.agentStats, queryFn: fetchAgentStatistics });
}

export function useCreateAgent() {
  return useApiMutation(
    (payload: AgentCreate) => createAgent(payload),
    [qk.agents],
  );
}

export function useUpdateAgent() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: AgentUpdate }) =>
      updateAgent(id, payload),
    [qk.agents],
  );
}

export function useDeleteAgent() {
  return useApiMutation(
    (id: string) => deleteAgent(id),
    [qk.agents],
  );
}

