/**
 * endpoints/groups — groups (platform-level org + tenant attachment).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Group,
  GroupCreate,
  GroupUpdate,
} from "../types";
// ---------- groups (platform-level org + tenant attachment) ----------
// Writes are super-admin only on the backend; reads are open to any logged-in
// user (the service returns the caller's own groups for tenant users).
export async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get<Group[]>("/groups/");
  return data;
}

export async function createGroup(payload: GroupCreate): Promise<Group> {
  const { data } = await api.post<Group>("/groups/", payload);
  return data;
}

export async function updateGroup(
  id: string,
  payload: GroupUpdate,
): Promise<Group> {
  const { data } = await api.put<Group>(`/groups/${id}`, payload);
  return data;
}

export async function deleteGroup(id: string): Promise<void> {
  await api.delete(`/groups/${id}`);
}

// Attach / detach a single tenant after creation (super-admin only).
export async function attachTenant(
  groupId: string,
  tenantId: string,
): Promise<void> {
  await api.post(`/groups/${groupId}/tenants/${tenantId}`);
}

export async function detachTenant(
  groupId: string,
  tenantId: string,
): Promise<void> {
  await api.delete(`/groups/${groupId}/tenants/${tenantId}`);
}

