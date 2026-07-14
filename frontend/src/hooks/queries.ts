import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { applyThemeColor } from "@/lib/theme";
import {
  addMember,
  addConversationTag,
  attachTenant,
  batchDeleteConversations,
  changePassword,
  changeUserStatus,
  createAgent,
  createApiToken,
  createCustomerProfile,
  createGroup,
  createPricing,
  createRole,
  createTenant,
  createUser,
  deleteAgent,
  deleteConversation,
  deleteCustomerProfile,
  deleteGroup,
  deletePricing,
  deleteRole,
  deleteUser,
  detachTenant,
  fetchAgents,
  fetchAgentStatistics,
  fetchApiTokens,
  fetchConversations,
  fetchConversationStatistics,
  fetchCustomerAggregate,
  fetchCustomerProfiles,
  fetchCustomers,
  fetchCustomerStatistics,
  fetchCustomerUsage,
  fetchDashboardOverview,
  fetchDashboardTrends,
  fetchEffectiveModels,
  fetchGroups,
  fetchAllTenants,
  globalSearch,
  fetchLogs,
  fetchMembers,
  fetchMessages,
  fetchPermissionMatrix,
  fetchPlatformLlmConfig,
  fetchPricing,
  fetchRoleLabels,
  fetchRolePermissions,
  fetchRoles,
  fetchSessions,
  fetchTenantLlmConfig,
  fetchTenants,
  fetchTenantConfig,
  fetchTransactions,
  fetchUsage,
  fetchUserStatistics,
  fetchUsers,
  fetchWallet,
  grantRolePermission,
  recharge,
  removeConversationTag,
  removeMember,
  renameConversation,
  resetUserPassword,
  revokeApiToken,
  revokeRolePermission,
  setConversationPinned,
  setConversationStarred,
  terminateSession,
  updateAgent,
  updateCustomerProfile,
  updateGroup,
  updateMe,
  updateMember,
  updatePricing,
  updateTenant,
  updateTenantConfig,
  updatePlatformLlmConfig,
  updateRole,
  updateTenantLlmConfig,
  updateUser,
} from "@/api/endpoints";
import type {
  AgentCreate,
  AgentUpdate,
  ApiTokenCreate,
  ConversationFilters,
  CustomerProfileCreate,
  CustomerProfileUpdate,
  GroupCreate,
  GroupUpdate,
  LlmConfigUpdate,
  LogFilters,
  MemberCreate,
  MemberUpdate,
  ModelPricingUpsert,
  PasswordChange,
  ProfileUpdate,
  RechargeRequest,
  RoleCreate,
  RolePermissionGrant,
  RoleUpdate,
  TenantConfigUpdate,
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
  // conversation list query key encodes the search/tag filters so each distinct
  // filter set caches independently (a debounced search produces a stream of
  // unique keys). Empty filters collapse to the bare key for the common case.
  conversations: (filters?: ConversationFilters) =>
    (filters && (filters.search || filters.tag)
      ? ["conversations", filters] as const
      : ["conversations"] as const),
  messages: (conversationId: string) =>
    ["conversations", conversationId, "messages"] as const,
  llmConfigPlatform: ["settings", "llm", "platform"] as const,
  llmConfigTenant: ["settings", "llm", "tenant"] as const,
  effectiveModels: ["settings", "models"] as const,
  // tenant branding config (white-label). One row per tenant; read is open to
  // any authenticated member of the tenant, write is owner/admin only.
  tenantConfig: ["tenant-config"] as const,
  apiTokens: ["api-tokens"] as const,
  groups: ["groups"] as const,
  group: (id: string) => ["groups", id] as const,
  // customers: two query families — store profiles (tenant-scoped CRUD) and
  // HQ aggregation (cross-store, super_admin only).
  customerProfiles: ["customers", "profiles"] as const,
  customers: ["customers"] as const,
  customer: (id: string) => ["customers", id] as const,
  customerUsage: (id: string) => ["customers", id, "usage"] as const,
  // Token 费用管理系列 4/4 — wallet / ledger / usage / pricing.
  wallet: ["billing", "wallet"] as const,
  walletByTenant: (tenantId: string) =>
    ["billing", "wallet", tenantId] as const,
  transactions: ["billing", "transactions"] as const,
  usage: ["billing", "usage"] as const,
  pricing: ["billing", "pricing"] as const,
  // dashboard analytics — per-entity stats + trend + HQ overview.
  agentStats: ["agents", "statistics"] as const,
  conversationStats: ["conversations", "statistics"] as const,
  customerStats: ["customers", "statistics"] as const,
  dashboardTrends: (days: number) => ["dashboard", "trends", days] as const,
  dashboardOverview: ["dashboard", "overview"] as const,
  // audit logs — paginated, filterable by operator/action/resource/date.
  logs: (filters: LogFilters) => ["logs", filters] as const,
  // global cross-entity search (priority 51). Key encodes the query so each
  // distinct term caches independently; the debounced hook below produces the
  // stream of unique keys.
  globalSearch: (q: string, limitPerType: number) =>
    ["search", q, limitPerType] as const,
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
export function useCustomerProfiles(enabled: boolean = true) {
  return useQuery({
    queryKey: qk.customerProfiles,
    queryFn: fetchCustomerProfiles,
    enabled,
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

// Token 费用管理系列 3/4: AI usage attributed to a customer (customer 360).
export function useCustomerUsage(id: string | null) {
  return useQuery({
    queryKey: qk.customerUsage(id ?? ""),
    queryFn: () => fetchCustomerUsage(id as string),
    enabled: !!id,
  });
}

// Customer count for the dashboard card (store profiles vs. HQ identities).
export function useCustomerStatistics() {
  return useQuery({
    queryKey: qk.customerStats,
    queryFn: fetchCustomerStatistics,
  });
}

// ---------- agents ----------
export function useAgents() {
  return useQuery({ queryKey: qk.agents, queryFn: fetchAgents });
}

// Agent count for the dashboard card (store-scoped or HQ aggregate).
export function useAgentStatistics() {
  return useQuery({ queryKey: qk.agentStats, queryFn: fetchAgentStatistics });
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roles"] });
      // data_scope lives on the role and the matrix endpoint returns roles[],
      // so refresh the matrix too (the permissions-page data_scope selector
      // goes through this hook).
      qc.invalidateQueries({ queryKey: qk.permissionMatrix });
    },
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

// Self-service profile + password (PUT /auth/me, PUT /auth/me/password).
// The /me query key is owned by auth-context (["auth","me",token]), so
// invalidating ["auth","me"] forces it to refetch the updated identity.
export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProfileUpdate) => updateMe(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "me"] }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: PasswordChange) => changePassword(payload),
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

// ---------- tenant branding config (white-label, priority 52) ----------
// Read is open to any authenticated user of the tenant (the theme color / logo /
// display name apply globally to everyone), so this hook has no `enabled` gate.
// Write (update) requires settings:update, checked by the caller before showing
// the card.
export function useTenantConfig() {
  return useQuery({
    queryKey: qk.tenantConfig,
    queryFn: fetchTenantConfig,
  });
}

export function useUpdateTenantConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TenantConfigUpdate) => updateTenantConfig(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.tenantConfig }),
  });
}

/**
 * Apply the tenant theme color globally as the ``--primary`` CSS token.
 *
 * Reads the current tenant's branding config (open to any authenticated user),
 * converts ``#RRGGBB`` to the HSL token shadcn expects, and writes it onto
 * ``:root``. The cleanup restores the platform default on unmount / tenant
 * switch / logout so a stale brand never bleeds across tenants. No-op while the
 * config is still loading or when no color is set (defaults preserved).
 */
export function useApplyTenantTheme() {
  const { data } = useTenantConfig();
  useEffect(() => {
    applyThemeColor(data?.theme_color ?? null);
    return () => {
      // Restore platform defaults when the branded surface unmounts (logout,
      // tenant switch) so a stale brand never bleeds across tenants.
      applyThemeColor(null);
    };
  }, [data?.theme_color]);
}

// ---------- conversations (chat history; streaming is NOT a query) ----------
// sendChatStream is an async generator consumed imperatively in chat-page.tsx
// (streaming deltas don't fit useMutation's one-shot success semantics), so
// there is no useChatStream hook here by design.
//
// conversation-management (priority 50): useConversations accepts search/tag
// filters; the query key encodes them so each filter set caches independently.
// All mutations invalidate the whole ["conversations"] family so every filter
// view refetches after a change.
export function useConversations(filters?: ConversationFilters) {
  return useQuery({
    queryKey: qk.conversations(filters),
    queryFn: () => fetchConversations(filters),
  });
}

// Conversation counts (total + 7d/30d) for the dashboard card.
export function useConversationStatistics() {
  return useQuery({
    queryKey: qk.conversationStats,
    queryFn: fetchConversationStatistics,
  });
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

// conversation-management mutations (priority 50). Each invalidates the whole
// conversations family so the list (any active filter view) refetches.
export function useRenameConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      renameConversation(id, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useAddConversationTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tag }: { id: string; tag: string }) =>
      addConversationTag(id, tag),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useRemoveConversationTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tag }: { id: string; tag: string }) =>
      removeConversationTag(id, tag),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useSetConversationPinned() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) =>
      setConversationPinned(id, pinned),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useSetConversationStarred() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, starred }: { id: string; starred: boolean }) =>
      setConversationStarred(id, starred),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useBatchDeleteConversations() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (conversationIds: string[]) =>
      batchDeleteConversations(conversationIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
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

// ---------- billing (Token 费用管理系列 4/4) ----------
// Wallet reads are split by scope (own tenant vs. any tenant).
// recharge + pricing writes invalidate the keys they touch so dashboards
// refetch immediately after a mutation.

/** The caller's own tenant wallet (null if the tenant has none yet). */
export function useWallet() {
  return useQuery({ queryKey: qk.wallet, queryFn: fetchWallet });
}

/** The caller's own tenant ledger (recharge/consume/refund/adjust). */
export function useTransactions() {
  return useQuery({
    queryKey: qk.transactions,
    queryFn: () => fetchTransactions(),
  });
}

/** Usage detail (drill-down): raw usage rows + token totals in one call. */
export function useUsage() {
  return useQuery({ queryKey: qk.usage, queryFn: () => fetchUsage() });
}

/** Super-admin: credit a tenant's wallet. Invalidates wallet + ledger. */
export function useRecharge() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RechargeRequest) => recharge(payload),
    onSuccess: (_data, { tenant_id }) => {
      // Refresh the affected tenant's wallet + the global wallet list, plus the
      // caller-side ledger (super_admin may be viewing transactions too).
      qc.invalidateQueries({ queryKey: qk.walletByTenant(tenant_id) });
      qc.invalidateQueries({ queryKey: qk.wallet });
      qc.invalidateQueries({ queryKey: qk.transactions });
    },
  });
}

/** Effective pricing for the caller (tenant overrides + platform defaults). */
export function useModelPricing() {
  return useQuery({ queryKey: qk.pricing, queryFn: fetchPricing });
}

export function useCreatePricing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ModelPricingUpsert) => createPricing(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.pricing }),
  });
}

export function useUpdatePricing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ModelPricingUpsert }) =>
      updatePricing(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.pricing }),
  });
}

export function useDeletePricing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePricing(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.pricing }),
  });
}

// ---------- dashboard analytics ----------
// Trends backs the activity bar chart on both the store and HQ dashboards
// (store-scoped vs. cross-tenant aggregate — the backend splits on platform_role,
// so one hook serves both views). Overview is super_admin-only; callers gate it
// with `enabled` so a tenant user never fires a 403-guaranteed request.

/** Daily conversation + message counts for the last `days` days. */
export function useDashboardTrends(days: number) {
  return useQuery({
    queryKey: qk.dashboardTrends(days),
    queryFn: () => fetchDashboardTrends(days),
  });
}

/** super_admin HQ overview: platform totals + per-tenant activity Top N. */
export function useDashboardOverview(enabled = true) {
  return useQuery({
    queryKey: qk.dashboardOverview,
    queryFn: fetchDashboardOverview,
    enabled,
  });
}

// ---------- audit logs ----------

/** Paginated, filterable audit log. Refetches when filters change (new key). */
export function useLogs(filters: LogFilters) {
  return useQuery({
    queryKey: qk.logs(filters),
    queryFn: () => fetchLogs(filters),
    placeholderData: (prev) => prev, // keep previous page while fetching next
  });
}

// ---------- global cross-entity search (priority 51) ----------

/**
 * Delay mirroring a value until the user stops changing it for `delay` ms.
 *
 * Used by `useGlobalSearch` to avoid firing a cross-entity search on every
 * keystroke. Generic so other live-search inputs can reuse it later.
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/**
 * Cross-entity search hook for the top-bar search box.
 *
 * Debounces the raw query (300ms), then fires GET /search only when the
 * debounced term is at least 2 chars (the backend's minimum). Below that the
 * query is disabled so no request leaves the browser — matching the empty-
 * result guard on the server side.
 */
export function useGlobalSearch(q: string, limitPerType = 5) {
  const term = q.trim();
  const debounced = useDebouncedValue(term, 300);
  const enabled = debounced.length >= 2;
  return useQuery({
    queryKey: qk.globalSearch(debounced, limitPerType),
    queryFn: () => globalSearch(debounced, limitPerType),
    enabled,
    placeholderData: (prev) => prev, // keep the prior dropdown stable while typing
  });
}
