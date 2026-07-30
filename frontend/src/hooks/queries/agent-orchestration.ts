/**
 * queries/agent-orchestration — agent orchestration (priority 58).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  attachSpecialist,
  detachSpecialist,
  fetchOrchestratorSpecialists,
} from "@/api/endpoints";
// ---------- agent orchestration (priority 58) ----------
// Specialists attached to an orchestrator. Attach/detach invalidate the
// agents list so AgentRead.specialist_ids stays fresh on the agents page.
export function useOrchestratorSpecialists(orchestratorId: string | undefined) {
  return useQuery({
    queryKey: [...qk.agents, "specialists", orchestratorId],
    queryFn: () => fetchOrchestratorSpecialists(orchestratorId!),
    enabled: !!orchestratorId,
  });
}

export function useAttachSpecialist() {
  return useApiMutation(
    ({
      orchestratorId,
      specialistId,
    }: {
      orchestratorId: string;
      specialistId: string;
    }) => attachSpecialist(orchestratorId, specialistId),
    [qk.agents],
  );
}

export function useDetachSpecialist() {
  return useApiMutation(
    ({
      orchestratorId,
      specialistId,
    }: {
      orchestratorId: string;
      specialistId: string;
    }) => detachSpecialist(orchestratorId, specialistId),
    [qk.agents],
  );
}

