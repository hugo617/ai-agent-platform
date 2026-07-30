/**
 * queries/users — users (full CRUD).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery, type QueryKey } from "@tanstack/react-query";
import {
  changeUserStatus,
  createUser,
  deleteUser,
  fetchUserStatistics,
  fetchUsers,
  resetUserPassword,
  updateUser,
} from "@/api/endpoints";
import type {
  UserFilters,
  UserFormData,
  UserStatus,
} from "@/api/types";
// ---------- users (full CRUD) ----------
export function useUsers(filters: UserFilters) {
  return useQuery({ queryKey: qk.users(filters), queryFn: () => fetchUsers(filters) });
}

export function useUserStatistics() {
  return useQuery({ queryKey: qk.userStats, queryFn: fetchUserStatistics });
}

// All user mutations invalidate the ["users"] key family (list + statistics).
const USER_KEYS: QueryKey[] = [["users"]];

export function useCreateUser() {
  return useApiMutation(
    (payload: UserFormData) => createUser(payload),
    USER_KEYS,
  );
}

export function useUpdateUser() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: Partial<UserFormData> }) =>
      updateUser(id, payload),
    USER_KEYS,
  );
}

export function useDeleteUser() {
  return useApiMutation(
    (id: string) => deleteUser(id),
    USER_KEYS,
  );
}

export function useChangeUserStatus() {
  return useApiMutation(
    ({ id, status }: { id: string; status: UserStatus }) =>
      changeUserStatus(id, status),
    USER_KEYS,
  );
}

export function useResetUserPassword() {
  return useApiMutation(
    ({ id, password }: { id: string; password: string }) =>
      resetUserPassword(id, password),
    USER_KEYS,
  );
}

