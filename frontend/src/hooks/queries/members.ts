/**
 * queries/members — members (tenant-membership UI not built yet).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  addMember,
  fetchMembers,
  removeMember,
  updateMember,
} from "@/api/endpoints";
import type {
  MemberCreate,
  MemberUpdate,
} from "@/api/types";
// ---------- members (tenant-membership UI not built yet) ----------
export function useMembers() {
  return useQuery({ queryKey: qk.members, queryFn: fetchMembers });
}

export function useAddMember() {
  return useApiMutation(
    (payload: MemberCreate) => addMember(payload),
    [qk.members],
  );
}

export function useUpdateMember() {
  return useApiMutation(
    ({ userId, payload }: { userId: string; payload: MemberUpdate }) =>
      updateMember(userId, payload),
    [qk.members],
  );
}

export function useRemoveMember() {
  return useApiMutation(
    (userId: string) => removeMember(userId),
    [qk.members],
  );
}

