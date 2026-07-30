/**
 * endpoints/agent-orchestration — agent orchestration (priority 58).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Agent,
} from "../types";
// ---------- agent orchestration (priority 58) ----------
// Specialists attached to an orchestrator. Attach/detach are immediate
// (per-row), mirroring the group-tenant mount pattern.
export async function fetchOrchestratorSpecialists(
  orchestratorId: string,
): Promise<Agent[]> {
  const { data } = await api.get<Agent[]>(
    `/agents/${orchestratorId}/specialists`,
  );
  return data;
}

export async function attachSpecialist(
  orchestratorId: string,
  specialistId: string,
): Promise<void> {
  await api.post(`/agents/${orchestratorId}/specialists/${specialistId}`);
}

export async function detachSpecialist(
  orchestratorId: string,
  specialistId: string,
): Promise<void> {
  await api.delete(`/agents/${orchestratorId}/specialists/${specialistId}`);
}

