/**
 * queries/groups — groups (platform-level org + tenant attachment).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  attachTenant,
  createGroup,
  deleteGroup,
  detachTenant,
  fetchGroups,
  updateGroup,
} from "@/api/endpoints";
import type {
  GroupCreate,
  GroupUpdate,
} from "@/api/types";
// ---------- groups (platform-level org + tenant attachment) ----------
export function useGroups() {
  return useQuery({ queryKey: qk.groups, queryFn: fetchGroups });
}

export function useCreateGroup() {
  return useApiMutation(
    (payload: GroupCreate) => createGroup(payload),
    [qk.groups],
  );
}

export function useUpdateGroup() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: GroupUpdate }) =>
      updateGroup(id, payload),
    [qk.groups],
  );
}

export function useDeleteGroup() {
  return useApiMutation(
    (id: string) => deleteGroup(id),
    [qk.groups],
  );
}

export function useAttachTenant() {
  return useApiMutation(
    ({ groupId, tenantId }: { groupId: string; tenantId: string }) =>
      attachTenant(groupId, tenantId),
    [qk.groups],
  );
}

export function useDetachTenant() {
  return useApiMutation(
    ({ groupId, tenantId }: { groupId: string; tenantId: string }) =>
      detachTenant(groupId, tenantId),
    [qk.groups],
  );
}

