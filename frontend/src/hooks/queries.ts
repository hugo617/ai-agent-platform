import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { applyThemeColor } from "@/lib/theme";
import { useTheme } from "@/components/theme/theme-provider";
import {
  addMember,
  addConversationTag,
  attachSpecialist,
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
  detachSpecialist,
  detachTenant,
  fetchAgents,
  fetchAgentStatistics,
  fetchOrchestratorSpecialists,
  fetchApiTokens,
  fetchConversations,
  fetchConversationStatistics,
  fetchCustomerProfiles,
  fetchCustomers,
  fetchCustomerStatistics,
  fetchCustomerUsage,
  fetchDashboardOverview,
  fetchDashboardTrends,
  fetchEffectiveModels,
  fetchGroups,
  fetchAllTenants,
  fetchDocuments,
  fetchPlatformEmbeddingConfig,
  fetchTenantEmbeddingConfig,
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
  updateAgent,
  updateCustomerProfile,
  updateGroup,
  updateMe,
  updateMember,
  updatePricing,
  updateTenant,
  updateTenantConfig,
  updatePlatformEmbeddingConfig,
  updatePlatformLlmConfig,
  updateRole,
  updateTenantEmbeddingConfig,
  updateTenantLlmConfig,
  updateUser,
  createDocument,
  deleteDocument,
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  exportEntity,
} from "@/api/endpoints";
import type { ExportEntity, ExportParams } from "@/api/endpoints";
import type {
  AgentCreate,
  AgentUpdate,
  ApiTokenCreate,
  ConversationFilters,
  CustomerProfileCreate,
  CustomerProfileUpdate,
  EmbeddingConfigUpdate,
  GroupCreate,
  GroupUpdate,
  DocumentCreate,
  LlmConfigUpdate,
  LogFilters,
  MemberCreate,
  MemberUpdate,
  ModelPricingUpsert,
  NotificationFilters,
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
  members: ["members"] as const,
  users: (filters: UserFilters) => ["users", filters] as const,
  userStats: ["users", "statistics"] as const,
  roles: ["roles"] as const,
  roleLabels: ["roles", "labels"] as const,
  rolePermissions: (id: string) => ["roles", id, "permissions"] as const,
  permissionMatrix: ["permissions", "matrix"] as const,
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
  // embedding config (RAG, priority 57). Mirror the LLM config key shape.
  embeddingConfigPlatform: ["settings", "embedding", "platform"] as const,
  embeddingConfigTenant: ["settings", "embedding", "tenant"] as const,
  // knowledge base documents (RAG, priority 57).
  documents: ["knowledge", "documents"] as const,
  // tenant branding config (white-label). One row per tenant; read is open to
  // any authenticated member of the tenant, write is owner/admin only.
  tenantConfig: ["tenant-config"] as const,
  apiTokens: ["api-tokens"] as const,
  groups: ["groups"] as const,
  // customers: two query families — store profiles (tenant-scoped CRUD) and
  // HQ aggregation (cross-store, super_admin only).
  customerProfiles: ["customers", "profiles"] as const,
  customers: ["customers"] as const,
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
  // in-app notifications (priority 54). The bell polls unread-count every
  // 30s; the page lists with an optional unread filter.
  notifications: (filters: NotificationFilters) => ["notifications", filters] as const,
  unreadCount: ["notifications", "unread-count"] as const,
};

/**
 * Mutation helper that wires the common shape: ``mutationFn`` + invalidate a
 * fixed set of query keys on success.
 *
 * Most write hooks in this file are the same 5-line skeleton
 * (``const qc = useQueryClient(); return useMutation({ mutationFn, onSuccess:
 * () => qc.invalidateQueries(...) })``). This helper collapses that to one
 * line for the common case and still allows an extra ``onSuccess`` callback
 * for hooks that need to invalidate a vars-derived key (e.g.
 * ``useGrantRolePermission`` invalidates ``qk.rolePermissions(roleId)``).
 *
 * Hooks with more involved logic (optimistic updates, conditional
 * invalidation, side-effects) stay as hand-written ``useMutation`` calls.
 */
function useApiMutation<TVars, TData>(
  mutationFn: (vars: TVars) => Promise<TData>,
  invalidate: QueryKey[],
  onSuccess?: (data: TData, vars: TVars) => void,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data, vars) => {
      for (const key of invalidate) qc.invalidateQueries({ queryKey: key });
      onSuccess?.(data, vars);
    },
  });
}

// ---------- tenants ----------
// useTenants/useCreateTenant serve the dashboard "my tenants" card (user-scoped
// GET /tenants/). The platform-level hooks below drive the store-management
// page (super_admin GET /tenants/all + PUT /tenants/{id}).
export function useTenants() {
  return useQuery({ queryKey: qk.tenants, queryFn: fetchTenants });
}

export function useCreateTenant() {
  return useApiMutation(
    (name: string) => createTenant(name),
    [qk.tenants, qk.allTenants],
  );
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
  // Also refresh the user-scoped list: a rename should propagate to the
  // dashboard "my tenants" card if the edited tenant belongs to the user.
  return useApiMutation(
    ({ id, payload }: { id: string; payload: TenantUpdate }) =>
      updateTenant(id, payload),
    [qk.allTenants, qk.tenants],
  );
}

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
  return useApiMutation(
    (payload: CustomerProfileCreate) => createCustomerProfile(payload),
    [qk.customerProfiles, qk.customers],
  );
}

export function useUpdateCustomerProfile() {
  return useApiMutation(
    ({
      id,
      payload,
    }: {
      id: string;
      payload: CustomerProfileUpdate;
    }) => updateCustomerProfile(id, payload),
    [qk.customerProfiles, qk.customers],
  );
}

export function useDeleteCustomerProfile() {
  return useApiMutation(
    (id: string) => deleteCustomerProfile(id),
    [qk.customerProfiles, qk.customers],
  );
}

// HQ view hooks: cross-store aggregation (super_admin only).
export function useCustomers() {
  return useQuery({ queryKey: qk.customers, queryFn: fetchCustomers });
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
  return useApiMutation(
    (payload: AgentCreate) => createAgent(payload),
    [qk.agents],
  );
}

export function useUpdateAgent() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: AgentUpdate }) =>
      updateAgent(id, payload),
    [qk.agents],
  );
}

export function useDeleteAgent() {
  return useApiMutation(
    (id: string) => deleteAgent(id),
    [qk.agents],
  );
}

// ---------- agent orchestration (priority 58) ----------
// Specialists attached to an orchestrator. Attach/detach invalidate the
// agents list so AgentRead.specialist_ids stays fresh on the agents page.
export function useOrchestratorSpecialists(orchestratorId: string | undefined) {
  return useQuery({
    queryKey: [...qk.agents, "specialists", orchestratorId],
    queryFn: () => fetchOrchestratorSpecialists(orchestratorId!),
    enabled: !!orchestratorId,
  });
}

export function useAttachSpecialist() {
  return useApiMutation(
    ({
      orchestratorId,
      specialistId,
    }: {
      orchestratorId: string;
      specialistId: string;
    }) => attachSpecialist(orchestratorId, specialistId),
    [qk.agents],
  );
}

export function useDetachSpecialist() {
  return useApiMutation(
    ({
      orchestratorId,
      specialistId,
    }: {
      orchestratorId: string;
      specialistId: string;
    }) => detachSpecialist(orchestratorId, specialistId),
    [qk.agents],
  );
}

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

// ---------- roles (full CRUD + permission grants) ----------
export function useRoles() {
  return useQuery({ queryKey: qk.roles, queryFn: fetchRoles });
}

export function useRoleLabels() {
  return useQuery({ queryKey: qk.roleLabels, queryFn: fetchRoleLabels });
}

export function useCreateRole() {
  return useApiMutation(
    (payload: RoleCreate) => createRole(payload),
    // The matrix endpoint returns roles[], so refresh it alongside the list
    // (consistent with useUpdateRole below).
    [["roles"], qk.permissionMatrix],
  );
}

export function useUpdateRole() {
  // data_scope lives on the role and the matrix endpoint returns roles[],
  // so refresh the matrix too (the permissions-page data_scope selector
  // goes through this hook).
  return useApiMutation(
    ({ id, payload }: { id: string; payload: RoleUpdate }) =>
      updateRole(id, payload),
    [["roles"], qk.permissionMatrix],
  );
}

export function useDeleteRole() {
  return useApiMutation(
    (id: string) => deleteRole(id),
    [["roles"], qk.permissionMatrix],
  );
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
  return useApiMutation(
    ({
      roleId,
      payload,
    }: {
      roleId: string;
      payload: RolePermissionGrant;
    }) => grantRolePermission(roleId, payload),
    [qk.permissionMatrix],
    (_data, { roleId }) =>
      qc.invalidateQueries({ queryKey: qk.rolePermissions(roleId) }),
  );
}

export function useRevokeRolePermission() {
  const qc = useQueryClient();
  return useApiMutation(
    ({
      roleId,
      permissionId,
    }: {
      roleId: string;
      permissionId: string;
    }) => revokeRolePermission(roleId, permissionId),
    [qk.permissionMatrix],
    (_data, { roleId }) =>
      qc.invalidateQueries({ queryKey: qk.rolePermissions(roleId) }),
  );
}

// ---------- auth ----------
// NOTE: there is no useLogin/useLogout hook by design. login-page.tsx calls the
// `login()` endpoint directly and hands the token to auth-context.signIn()
// (which already resets the /me query); dashboard-layout.tsx calls `logout()`
// directly before clearing local state. Wrapping them in mutations would just
// duplicate that wiring.

// Self-service profile + password (PUT /auth/me, PUT /auth/me/password).
// The /me query key is owned by auth-context (["auth","me",token]), so
// invalidating ["auth","me"] forces it to refetch the updated identity.
export function useUpdateMe() {
  return useApiMutation(
    (payload: ProfileUpdate) => updateMe(payload),
    [["auth", "me"]],
  );
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
  return useApiMutation(
    (payload: LlmConfigUpdate) => updatePlatformLlmConfig(payload),
    [qk.llmConfigPlatform],
  );
}

export function useTenantLlmConfig() {
  return useQuery({
    queryKey: qk.llmConfigTenant,
    queryFn: fetchTenantLlmConfig,
  });
}

export function useUpdateTenantLlmConfig() {
  return useApiMutation(
    (payload: LlmConfigUpdate) => updateTenantLlmConfig(payload),
    [qk.llmConfigTenant],
  );
}

export function useEffectiveModels() {
  return useQuery({
    queryKey: qk.effectiveModels,
    queryFn: fetchEffectiveModels,
  });
}

// ---------- embedding config (RAG, priority 57) ----------
export function usePlatformEmbeddingConfig() {
  return useQuery({
    queryKey: qk.embeddingConfigPlatform,
    queryFn: fetchPlatformEmbeddingConfig,
  });
}

export function useUpdatePlatformEmbeddingConfig() {
  return useApiMutation(
    (payload: EmbeddingConfigUpdate) => updatePlatformEmbeddingConfig(payload),
    [qk.embeddingConfigPlatform],
  );
}

export function useTenantEmbeddingConfig() {
  return useQuery({
    queryKey: qk.embeddingConfigTenant,
    queryFn: fetchTenantEmbeddingConfig,
  });
}

export function useUpdateTenantEmbeddingConfig() {
  return useApiMutation(
    (payload: EmbeddingConfigUpdate) => updateTenantEmbeddingConfig(payload),
    [qk.embeddingConfigTenant],
  );
}

// ---------- knowledge base / RAG (priority 57) ----------
export function useDocuments() {
  return useQuery({
    queryKey: qk.documents,
    queryFn: fetchDocuments,
  });
}

export function useCreateDocument() {
  return useApiMutation(
    (payload: DocumentCreate) => createDocument(payload),
    [qk.documents],
  );
}

export function useDeleteDocument() {
  return useApiMutation((id: string) => deleteDocument(id), [qk.documents]);
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
  return useApiMutation(
    (payload: TenantConfigUpdate) => updateTenantConfig(payload),
    [qk.tenantConfig],
  );
}

/**
 * Apply the tenant theme color globally as the ``--primary`` CSS token.
 *
 * Reads the current tenant's branding config (open to any authenticated user),
 * converts ``#RRGGBB`` to the HSL token shadcn expects, and writes it onto
 * ``:root``. The cleanup restores the platform default on unmount / tenant
 * switch / logout so a stale brand never bleeds across tenants. No-op while the
 * config is still loading or when no color is set (defaults preserved).
 *
 * Theme-aware re-application (P0-2): when the user flips light/dark, the
 * ``--primary`` foreground contrast must be re-derived against the active mode
 * (the revert path restores mode-specific platform defaults). So this hook also
 * re-runs ``applyThemeColor`` whenever ``resolvedTheme`` changes.
 */
export function useApplyTenantTheme() {
  const { data } = useTenantConfig();
  const { resolvedTheme } = useTheme();
  useEffect(() => {
    applyThemeColor(data?.theme_color ?? null);
    return () => {
      // Restore platform defaults when the branded surface unmounts (logout,
      // tenant switch) so a stale brand never bleeds across tenants.
      applyThemeColor(null);
    };
  }, [data?.theme_color, resolvedTheme]);
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
  return useApiMutation(
    (conversationId: string) => deleteConversation(conversationId),
    [["conversations"]],
  );
}

// conversation-management mutations (priority 50). Each invalidates the whole
// conversations family so the list (any active filter view) refetches.
export function useRenameConversation() {
  return useApiMutation(
    ({ id, title }: { id: string; title: string }) =>
      renameConversation(id, title),
    [["conversations"]],
  );
}

export function useAddConversationTag() {
  return useApiMutation(
    ({ id, tag }: { id: string; tag: string }) =>
      addConversationTag(id, tag),
    [["conversations"]],
  );
}

export function useRemoveConversationTag() {
  return useApiMutation(
    ({ id, tag }: { id: string; tag: string }) =>
      removeConversationTag(id, tag),
    [["conversations"]],
  );
}

export function useSetConversationPinned() {
  return useApiMutation(
    ({ id, pinned }: { id: string; pinned: boolean }) =>
      setConversationPinned(id, pinned),
    [["conversations"]],
  );
}

export function useSetConversationStarred() {
  return useApiMutation(
    ({ id, starred }: { id: string; starred: boolean }) =>
      setConversationStarred(id, starred),
    [["conversations"]],
  );
}

export function useBatchDeleteConversations() {
  return useApiMutation(
    (conversationIds: string[]) =>
      batchDeleteConversations(conversationIds),
    [["conversations"]],
  );
}

// ---------- api tokens (AtoA) ----------
export function useApiTokens() {
  return useQuery({ queryKey: qk.apiTokens, queryFn: fetchApiTokens });
}

export function useCreateApiToken() {
  return useApiMutation(
    (payload: ApiTokenCreate) => createApiToken(payload),
    [qk.apiTokens],
  );
}

export function useRevokeApiToken() {
  return useApiMutation(
    (id: string) => revokeApiToken(id),
    [qk.apiTokens],
  );
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
  return useApiMutation(
    (payload: RechargeRequest) => recharge(payload),
    // Refresh the global wallet list + the caller-side ledger (super_admin may
    // be viewing transactions too).
    [qk.wallet, qk.transactions],
    // Plus the specific affected tenant's wallet (vars-derived key).
    (_data, { tenant_id }) =>
      qc.invalidateQueries({ queryKey: qk.walletByTenant(tenant_id) }),
  );
}

/** Effective pricing for the caller (tenant overrides + platform defaults). */
export function useModelPricing() {
  return useQuery({ queryKey: qk.pricing, queryFn: fetchPricing });
}

export function useCreatePricing() {
  return useApiMutation(
    (payload: ModelPricingUpsert) => createPricing(payload),
    [qk.pricing],
  );
}

export function useUpdatePricing() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: ModelPricingUpsert }) =>
      updatePricing(id, payload),
    [qk.pricing],
  );
}

export function useDeletePricing() {
  return useApiMutation(
    (id: string) => deletePricing(id),
    [qk.pricing],
  );
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

// ---------- in-app notifications (priority 54) ----------

/** Paginated, filterable notification list (notifications page). */
export function useNotifications(filters?: NotificationFilters) {
  return useQuery({
    queryKey: qk.notifications(filters ?? {}),
    queryFn: () => fetchNotifications(filters),
    placeholderData: (prev) => prev, // keep previous page while fetching next
  });
}

/**
 * Bell-badge unread count. Polls every 30s — light endpoint, bounded cadence
 * (the plan's risk table: avoid tight SSE/WebSocket for now). The full
 * notification list is fetched on demand when the bell opens.
 */
export function useUnreadCount() {
  return useQuery({
    queryKey: qk.unreadCount,
    queryFn: fetchUnreadCount,
    refetchInterval: 30_000,
  });
}

/** Mark one notification read; invalidates unread-count + the open list. */
export function useMarkNotificationRead() {
  return useApiMutation(
    (id: string) => markNotificationRead(id),
    [["notifications"]],
  );
}

/** Mark all visible notifications read; invalidates unread-count + the list. */
export function useMarkAllNotificationsRead() {
  return useApiMutation(
    (_: void) => markAllNotificationsRead(),
    [["notifications"]],
  );
}

// ---------- CSV export (priority 55) ----------
// Triggers GET /exports/{entity} and saves the streamed CSV via downloadBlob.
// The mutation is just a wrapper around exportEntity + the browser download —
// no cache to invalidate (export is a read-only side-effect). The page wires
// the toast on success/error and supplies the filename based on the entity.
export function useExportCsv() {
  return useMutation({
    mutationFn: (args: {
      entity: ExportEntity;
      params?: ExportParams;
      filename: string;
    }) => exportEntityAndDownload(args.entity, args.params, args.filename),
  });
}

async function exportEntityAndDownload(
  entity: ExportEntity,
  params: ExportParams | undefined,
  filename: string,
): Promise<void> {
  const blob = await exportEntity(entity, params);
  // Lazy import keeps the download helper out of the bundle for callers that
  // only need the other hooks (the helper touches `document`, so isolating it
  // also keeps the module SSR-safe in case of future server rendering).
  const { downloadBlob } = await import("@/lib/download");
  downloadBlob(blob, filename);
}
