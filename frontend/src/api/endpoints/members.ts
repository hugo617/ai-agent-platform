/**
 * endpoints/members — members (tenant membership).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Member,
  MemberCreate,
  MemberUpdate,
  } from "../types";
// ---------- members (tenant membership) ----------
// Member endpoints moved to /tenants/me/members/ when /users/ became a full
// user-profile CRUD. Role-only operations on existing members live here.
export async function fetchMembers(): Promise<Member[]> {
  const { data } = await api.get<Member[]>("/tenants/me/members/");
  return data;
}

export async function addMember(payload: MemberCreate): Promise<Member> {
  const { data } = await api.post<Member>("/tenants/me/members/", payload);
  return data;
}

export async function updateMember(
  userId: string,
  payload: MemberUpdate
): Promise<Member> {
  const { data } = await api.patch<Member>(
    `/tenants/me/members/${userId}`,
    payload
  );
  return data;
}

export async function removeMember(userId: string): Promise<void> {
  await api.delete(`/tenants/me/members/${userId}`);
}

