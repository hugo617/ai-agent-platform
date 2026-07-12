import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  addMember,
  attachTenant,
  changeUserStatus,
  createAgent,
  createApiToken,
  createCustomerProfile,
  createGroup,
  createRole,
  createTenant,
  createUser,
  deleteAgent,
  deleteConversation,
  deleteCustomerProfile,
  deleteGroup,
  deleteRole,
  deleteUser,
  detachTenant,
  fetchAgents,
  fetchApiTokens,
  fetchConversations,
  fetchCustomerAggregate,
  fetchCustomerProfiles,
  fetchCustomers,
  fetchEffectiveModels,
  fetchGroups,
  fetchAllTenants,
  fetchMembers,
  fetchMessages,
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
  revokeApiToken,
  revokeRolePermission,
  terminateSession,
  updateAgent,
  updateCustomerProfile,
  updateGroup,
  updateMember,
  updateTenant,
  updatePlatformLlmConfig,
  updateRole,
  updateTenantLlmConfig,
  updateUser,
} from "@/api/endpoints";
import type {
  AgentCreate,
  AgentUpdate,
  ApiTokenCreate,
  CustomerProfileCreate,
  CustomerProfileUpdate,
  GroupCreate,
  GroupUpdate,
  LlmConfigUpdate,
  MemberCreate,
  MemberUpdate,
  RoleCreate,
  RolePermissionGrant,
  RoleUpdate,
  TenantUpdate,
  UserFilters,
  UserFormData,
  UserStatus,
} from "@/api/types";

// Query key factory — centralised so cache invalidation is consistent.
// NOTE: the /me query key is owned by auth-context.tsx (["auth","me",token]) so
// it is intentionally absent here to avoid a split-brain key.
export const qk = {
  tenants: ["tenants"] as const,
  // allTenants = GET /tenants/all (super_admin platform-wide list, with
  // member_count). Distinct from qk.tenants (user-scoped "my tenants").
  allTenants: ["tenants", "all"] as const,
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
  sessions: ["auth", "sessions"] as const,
  conversations: ["conversations"] as const,
  messages: (conversationId: string) =>
    ["conversations", conversationId, "messages"] as const,
  llmConfigPlatform: ["settings", "llm", "platform"] as const,
  llmConfigTenant: ["settings", "llm", "tenant"] as const,
  effectiveModels: ["settings", "models"] as const,
  apiTokens: ["api-tokens"] as const,
  groups: ["groups"] as const,
  group: (id: string) => ["groups", id] as const,
  // customers: two query families — store profiles (tenant-scoped CRUD) and
  // HQ aggregation (cross-store, super_admin only).
  customerProfiles: ["customers", "profiles"] as const,
  customers: ["customers"] as const,
  customer: (id: string) => ["customers", id] as const,
};

// ---------- tenants ----------
// useTenants/useCreateTenant serve the dashboard "my tenants" card (user-scoped
// GET /tenants/). The platform-level hooks below drive the store-management
// page (super_admin GET /tenants/all + PUT /tenants/{id}).
export function useTenants() {
  return useQuery({ queryKey: qk.tenants, queryFn: fetchTenants });
}

export function useCreateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createTenant(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.tenants });
      qc.invalidateQueries({ queryKey: qk.allTenants });
    },
  });
}

// Platform-wide tenant list (super_admin only). Also used by the groups page's
// tenant-attachment dropdown, where super_admin needs to see every store.
// `enabled` lets callers (e.g. the groups page, which non-super-admins view
// read-only) avoid firing a 403-guaranteed request.
export function useAllTenants(enabled = true) {
  return useQuery({
    queryKey: qk.allTenants,
    queryFn: fetchAllTenants,
    enabled,
  });
}

export function useUpdateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: TenantUpdate }) =>
      updateTenant(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.allTenants });
      // Also refresh the user-scoped list: a rename should propagate to the
      // dashboard "my tenants" card if the edited tenant belongs to the user.
      qc.invalidateQueries({ queryKey: qk.tenants });
    },
  });
}

// ---------- groups (platform-level org + tenant attachment) ----------
export function useGroups() {
  return useQuery({ queryKey: qk.groups, queryFn: fetchGroups });
}

export function useCreateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: GroupCreate) => createGroup(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.groups }),
  });
}

export function useUpdateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: GroupUpdate }) =>
      updateGroup(id, payload),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: qk.groups });
      qc.invalidateQueries({ queryKey: qk.group(id) });
    },
  });
}

export function useDeleteGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteGroup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.groups }),
  });
}

export function useAttachTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, tenantId }: { groupId: string; tenantId: string }) =>
      attachTenant(groupId, tenantId),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: qk.groups });
      qc.invalidateQueries({ queryKey: qk.group(groupId) });
    },
  });
}

export function useDetachTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, tenantId }: { groupId: string; tenantId: string }) =>
      detachTenant(groupId, tenantId),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: qk.groups });
      qc.invalidateQueries({ queryKey: qk.group(groupId) });
    },
  });
}

// ---------- customers (global identity + per-store profile) ----------
// Store view hooks: this tenant's profile CRUD. Writes also invalidate the HQ
// list (customers) so a super_admin viewing the aggregate sees the change.
export function useCustomerProfiles() {
  return useQuery({
    queryKey: qk.customerProfiles,
    queryFn: fetchCustomerProfiles,
  });
}

export function useCreateCustomerProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerProfileCreate) => createCustomerProfile(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.customerProfiles });
      qc.invalidateQueries({ queryKey: qk.customers });
    },
  });
}

export function useUpdateCustomerProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: CustomerProfileUpdate;
    }) => updateCustomerProfile(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.customerProfiles });
      qc.invalidateQueries({ queryKey: qk.customers });
    },
  });
}

export function useDeleteCustomerProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCustomerProfile(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.customerProfiles });
      qc.invalidateQueries({ queryKey: qk.customers });
    },
  });
}

// HQ view hooks: cross-store aggregation (super_admin only).
export function useCustomers() {
  return useQuery({ queryKey: qk.customers, queryFn: fetchCustomers });
}

export function useCustomerAggregate(id: string | null) {
  return useQuery({
    queryKey: qk.customer(id ?? ""),
    queryFn: () => fetchCustomerAggregate(id as string),
    enabled: !!id,
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

// ---------- api tokens (AtoA) ----------
export function useApiTokens() {
  return useQuery({ queryKey: qk.apiTokens, queryFn: fetchApiTokens });
}

export function useCreateApiToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApiTokenCreate) => createApiToken(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.apiTokens }),
  });
}

export function useRevokeApiToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => revokeApiToken(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.apiTokens }),
  });
}
