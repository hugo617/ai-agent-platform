import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  addMember,
  changeUserStatus,
  createAgent,
  createOrganization,
  createRole,
  createTenant,
  createUser,
  deleteAgent,
  deleteUser,
  fetchAgents,
  fetchMe,
  fetchMembers,
  fetchOrganizationTree,
  fetchRoleLabels,
  fetchSessions,
  fetchTenants,
  fetchUserStatistics,
  fetchUsers,
  logout,
  removeMember,
  resetUserPassword,
  terminateSession,
  updateAgent,
  updateMember,
  updateUser,
} from "@/api/endpoints";
import type {
  AgentCreate,
  AgentUpdate,
  MemberCreate,
  MemberUpdate,
  OrganizationCreate,
  RoleCreate,
  UserFilters,
  UserFormData,
} from "@/api/types";

// Query key factory — centralised so cache invalidation is consistent.
export const qk = {
  me: ["auth", "me"] as const,
  tenants: ["tenants"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  members: ["members"] as const,
  users: (filters: UserFilters) => ["users", filters] as const,
  user: (id: string) => ["users", id] as const,
  userStats: ["users", "statistics"] as const,
  roles: ["roles"] as const,
  roleLabels: ["roles", "labels"] as const,
  orgTree: ["organizations", "tree"] as const,
  sessions: ["auth", "sessions"] as const,
};

// ---------- auth ----------
export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: fetchMe });
}

// ---------- tenants ----------
export function useTenants() {
  return useQuery({ queryKey: qk.tenants, queryFn: fetchTenants });
}

export function useCreateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createTenant(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.tenants }),
  });
}

// ---------- agents ----------
export function useAgents() {
  return useQuery({ queryKey: qk.agents, queryFn: fetchAgents });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AgentCreate) => createAgent(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AgentUpdate }) =>
      updateAgent(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAgent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

// ---------- members (tenant-membership UI not built yet) ----------
export function useMembers() {
  return useQuery({ queryKey: qk.members, queryFn: fetchMembers });
}

export function useAddMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: MemberCreate) => addMember(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members }),
  });
}

export function useUpdateMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: MemberUpdate }) =>
      updateMember(userId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members }),
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeMember(userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members }),
  });
}

// ---------- users (full CRUD) ----------
export function useUsers(filters: UserFilters) {
  return useQuery({ queryKey: qk.users(filters), queryFn: () => fetchUsers(filters) });
}

export function useUserStatistics() {
  return useQuery({ queryKey: qk.userStats, queryFn: fetchUserStatistics });
}

function invalidateUsers(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["users"] });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserFormData) => createUser(payload),
    onSuccess: () => invalidateUsers(qc),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<UserFormData> }) =>
      updateUser(id, payload),
    onSuccess: () => invalidateUsers(qc),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => invalidateUsers(qc),
  });
}

export function useChangeUserStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      changeUserStatus(id, status),
    onSuccess: () => invalidateUsers(qc),
  });
}

export function useResetUserPassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      resetUserPassword(id, password),
    onSuccess: () => invalidateUsers(qc),
  });
}

// ---------- roles ----------
// useRoleLabels powers the user-form role dropdown. useCreateRole + the full
// role-management UI are scaffolded for a future Roles page.
export function useRoleLabels() {
  return useQuery({ queryKey: qk.roleLabels, queryFn: fetchRoleLabels });
}

export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoleCreate) => createRole(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}

// ---------- organizations (tree UI not built yet) ----------
export function useOrganizationTree() {
  return useQuery({ queryKey: qk.orgTree, queryFn: fetchOrganizationTree });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrganizationCreate) => createOrganization(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["organizations"] }),
  });
}

// ---------- auth (sessions) ----------
// NOTE: useLogin is intentionally omitted — login-page.tsx calls the `login()`
// endpoint directly and hands the token to auth-context.signIn(), which already
// resets the /me query. Adding a useLogin hook here would duplicate that.
export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => logout(),
    onSuccess: () => {
      qc.removeQueries({ queryKey: qk.sessions });
    },
  });
}

// Sessions UI is not built yet — these power the future "active sessions" page.
export function useSessions() {
  return useQuery({ queryKey: qk.sessions, queryFn: fetchSessions });
}

export function useTerminateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => terminateSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.sessions }),
  });
}
