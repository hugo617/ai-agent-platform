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
  deleteConversation,
  deleteOrganization,
  deleteRole,
  deleteUser,
  fetchAgents,
  fetchConversations,
  fetchEffectiveModels,
  fetchMembers,
  fetchMessages,
  fetchOrganizationTree,
  fetchPermissionMatrix,
  fetchPlatformLlmConfig,
  fetchRoleLabels,
  fetchRolePermissions,
  fetchRoles,
  fetchSessions,
  fetchTenantLlmConfig,
  fetchTenants,
  fetchUserStatistics,
  fetchUsers,
  grantRolePermission,
  removeMember,
  resetUserPassword,
  revokeRolePermission,
  terminateSession,
  updateAgent,
  updateMember,
  updateOrganization,
  updatePlatformLlmConfig,
  updateRole,
  updateTenantLlmConfig,
  updateUser,
} from "@/api/endpoints";
import type {
  AgentCreate,
  AgentUpdate,
  LlmConfigUpdate,
  MemberCreate,
  MemberUpdate,
  OrganizationCreate,
  OrganizationUpdate,
  RoleCreate,
  RolePermissionGrant,
  RoleUpdate,
  UserFilters,
  UserFormData,
  UserStatus,
} from "@/api/types";

// Query key factory — centralised so cache invalidation is consistent.
// NOTE: the /me query key is owned by auth-context.tsx (["auth","me",token]) so
// it is intentionally absent here to avoid a split-brain key.
export const qk = {
  tenants: ["tenants"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  members: ["members"] as const,
  users: (filters: UserFilters) => ["users", filters] as const,
  user: (id: string) => ["users", id] as const,
  userStats: ["users", "statistics"] as const,
  roles: ["roles"] as const,
  roleLabels: ["roles", "labels"] as const,
  rolePermissions: (id: string) => ["roles", id, "permissions"] as const,
  permissionMatrix: ["permissions", "matrix"] as const,
  orgTree: ["organizations", "tree"] as const,
  organizations: ["organizations"] as const,
  sessions: ["auth", "sessions"] as const,
  conversations: ["conversations"] as const,
  messages: (conversationId: string) =>
    ["conversations", conversationId, "messages"] as const,
  llmConfigPlatform: ["settings", "llm", "platform"] as const,
  llmConfigTenant: ["settings", "llm", "tenant"] as const,
  effectiveModels: ["settings", "models"] as const,
};

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
    mutationFn: ({ id, status }: { id: string; status: UserStatus }) =>
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

// ---------- roles (full CRUD + permission grants) ----------
export function useRoles() {
  return useQuery({ queryKey: qk.roles, queryFn: fetchRoles });
}

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

export function useUpdateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RoleUpdate }) =>
      updateRole(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteRole(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}

// role ↔ permission grants
export function useRolePermissions(roleId: string | null) {
  return useQuery({
    queryKey: qk.rolePermissions(roleId ?? ""),
    queryFn: () => fetchRolePermissions(roleId as string),
    enabled: !!roleId,
  });
}

// aggregated role × permission matrix (drives the permissions page)
export function usePermissionMatrix() {
  return useQuery({
    queryKey: qk.permissionMatrix,
    queryFn: fetchPermissionMatrix,
  });
}

export function useGrantRolePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      roleId,
      payload,
    }: {
      roleId: string;
      payload: RolePermissionGrant;
    }) => grantRolePermission(roleId, payload),
    onSuccess: (_data, { roleId }) => {
      qc.invalidateQueries({ queryKey: qk.rolePermissions(roleId) });
      qc.invalidateQueries({ queryKey: qk.permissionMatrix });
    },
  });
}

export function useRevokeRolePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      roleId,
      permissionId,
    }: {
      roleId: string;
      permissionId: string;
    }) => revokeRolePermission(roleId, permissionId),
    onSuccess: (_data, { roleId }) => {
      qc.invalidateQueries({ queryKey: qk.rolePermissions(roleId) });
      qc.invalidateQueries({ queryKey: qk.permissionMatrix });
    },
  });
}

// ---------- organizations ----------
export function useOrganizationTree() {
  return useQuery({ queryKey: qk.orgTree, queryFn: fetchOrganizationTree });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrganizationCreate) => createOrganization(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.organizations }),
  });
}

export function useUpdateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: OrganizationUpdate;
    }) => updateOrganization(id, payload),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: qk.organizations }),
  });
}

export function useDeleteOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOrganization(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.organizations }),
  });
}

// ---------- auth ----------
// NOTE: there is no useLogin/useLogout hook by design. login-page.tsx calls the
// `login()` endpoint directly and hands the token to auth-context.signIn()
// (which already resets the /me query); dashboard-layout.tsx calls `logout()`
// directly before clearing local state. Wrapping them in mutations would just
// duplicate that wiring.

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

// ---------- llm settings (platform + tenant) ----------
export function usePlatformLlmConfig() {
  return useQuery({
    queryKey: qk.llmConfigPlatform,
    queryFn: fetchPlatformLlmConfig,
  });
}

export function useUpdatePlatformLlmConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LlmConfigUpdate) => updatePlatformLlmConfig(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.llmConfigPlatform }),
  });
}

export function useTenantLlmConfig() {
  return useQuery({
    queryKey: qk.llmConfigTenant,
    queryFn: fetchTenantLlmConfig,
  });
}

export function useUpdateTenantLlmConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LlmConfigUpdate) => updateTenantLlmConfig(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.llmConfigTenant }),
  });
}

export function useEffectiveModels() {
  return useQuery({
    queryKey: qk.effectiveModels,
    queryFn: fetchEffectiveModels,
  });
}

// ---------- conversations (chat history; streaming is NOT a query) ----------
// sendChatStream is an async generator consumed imperatively in chat-page.tsx
// (streaming deltas don't fit useMutation's one-shot success semantics), so
// there is no useChatStream hook here by design.
export function useConversations() {
  return useQuery({ queryKey: qk.conversations, queryFn: fetchConversations });
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: qk.messages(conversationId ?? ""),
    queryFn: () => fetchMessages(conversationId as string),
    enabled: !!conversationId,
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => deleteConversation(conversationId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.conversations }),
  });
}
