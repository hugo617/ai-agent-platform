/**
 * endpoints/users — users (full profile CRUD).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  UserFilters,
  UserFormData,
  UserFull,
  UserListResponse,
  UserStatistics,
  UserStatus,
} from "../types";
// ---------- users (full profile CRUD) ----------
export async function fetchUsers(
  filters: UserFilters = {}
): Promise<UserListResponse> {
  const { data } = await api.get<UserListResponse>("/users/", {
    params: {
      search: filters.search || undefined,
      status: filters.status && filters.status !== "all" ? filters.status : undefined,
      role: filters.role && filters.role !== "all" ? filters.role : undefined,
      sort_by: filters.sort_by,
      sort_order: filters.sort_order,
      page: filters.page ?? 1,
      limit: filters.limit ?? 10,
    },
  });
  return data;
}

export async function createUser(payload: UserFormData): Promise<UserFull> {
  const { data } = await api.post<UserFull>("/users/", payload);
  return data;
}

export async function updateUser(
  id: string,
  payload: Partial<UserFormData>
): Promise<UserFull> {
  const { data } = await api.put<UserFull>(`/users/${id}`, payload);
  return data;
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);
}

export async function changeUserStatus(
  id: string,
  status: UserStatus
): Promise<UserFull> {
  const { data } = await api.patch<UserFull>(`/users/${id}/status`, { status });
  return data;
}

export async function resetUserPassword(
  id: string,
  newPassword: string
): Promise<void> {
  await api.post(`/users/${id}/reset-password`, { new_password: newPassword });
}

export async function fetchUserStatistics(): Promise<UserStatistics> {
  const { data } = await api.get<UserStatistics>("/users/statistics");
  return data;
}

