import axios from "axios";
import { api, getStoredToken, setStoredToken, AUTH_EXPIRED_EVENT } from "./client";
import type {
  Agent,
  AgentCreate,
  AgentStatistics,
  AgentUpdate,
  ApiToken,
  ApiTokenCreate,
  ApiTokenCreated,
  Conversation,
  ConversationStatistics,
  CustomerProfileCreate,
  CustomerProfileRead,
  CustomerProfileUpdate,
  CustomerRead,
  CustomerStatistics,
  CustomerUsage,
  DashboardOverview,
  DashboardTrends,
  GlobalSearchResult,
  Group,
  GroupCreate,
  GroupUpdate,
  LlmConfig,
  LlmConfigUpdate,
  LoginRequest,
  LogFilters,
  Member,
  MemberCreate,
  MemberUpdate,
  Message,
  MeResponse,
  ModelPricing,
  ModelPricingUpsert,
  Notification,
  NotificationFilters,
  NotificationListResponse,
  PasswordChange,
  PermissionMatrix,
  ProfileUpdate,
  RechargeRequest,
  Role,
  RoleCreate,
  RoleLabel,
  RolePermissionGrant,
  RolePermissionRead,
  RoleUpdate,
  SessionRead,
  SystemLogListResponse,
  Tenant,
  TenantConfig,
  TenantConfigUpdate,
  TenantUpdate,
  TokenResponse,
  UnreadCountResponse,
  UsageDetail,
  UserFilters,
  UserFormData,
  UserFull,
  UserListResponse,
  UserStatistics,
  UserStatus,
  Wallet,
  WalletTransaction,
} from "./types";

// ---------- file upload (priority 56) ----------
// POST /uploads/upload takes a multipart FormData body (the axios `api` instance
// already attaches the bearer token), validates the content-type + size on the
// backend, and returns the public URL the caller should persist on its own
// model (avatar/logo/…). The caller is responsible for saving the returned URL.

export interface UploadResponse {
  url: string; // e.g. /static/{tenant}/{uuid}.png — what <img src=> should use
  key: string; // the storage key (no original filename)
  size: number; // bytes
  content_type: string; // the validated MIME type
}

/**
 * Upload a single file via POST /uploads/upload. Returns the URL + metadata;
 * the caller persists the URL on its own record (e.g. TenantConfig.logo_url).
 *
 * Pass an optional onProgress callback (0–100) for a progress bar.
 */
export async function uploadFile(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<UploadResponse>("/uploads/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) {
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      }
    },
  });
  return data;
}

// ---------- auth ----------
export async function fetchMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/auth/me");
  return data;
}

// Self-service profile edit (PUT /auth/me). Target user is always the caller
// (the token's user_id) — there is no user_id in the payload to honor.
export async function updateMe(payload: ProfileUpdate): Promise<MeResponse> {
  const { data } = await api.put<MeResponse>("/auth/me", payload);
  return data;
}

// Self-service password change (PUT /auth/me/password). Returns void on 204.
export async function changePassword(payload: PasswordChange): Promise<void> {
  await api.put("/auth/me/password", payload);
}

// ---------- dev helpers (development env only) ----------
// These hit backend root endpoints (not under /api/v1) that only exist when
// APP_ENV=development. They let the frontend log in without Logto configured.

export interface DevBootstrapResponse {
  tenant_id: string;
  user_id: string;
  exists: boolean;
}

export interface DevTokenResponse {
  access_token: string;
  expires_in: number;
}

// Same origin as the API (Vite proxies /dev and /oidc through to the backend
// in dev). See vite.config.ts.
const devHttp = axios.create({ baseURL: "", timeout: 15000 });

/** Create (idempotent) a dev tenant + user and seed casbin policies. */
export async function devBootstrap(payload: {
  sub?: string;
  tenant_name?: string;
  email?: string;
} = {}): Promise<DevBootstrapResponse> {
  const { data } = await devHttp.post<DevBootstrapResponse>("/dev/bootstrap", payload);
  return data;
}

/** Mint a short-lived dev JWT for local login. */
export async function devToken(payload: {
  sub?: string;
  tenant_id: string;
  email?: string;
}): Promise<DevTokenResponse> {
  const { data } = await devHttp.post<DevTokenResponse>("/dev/token", payload);
  return data;
}

/** One-click dev login: bootstrap → mint token. Returns the access token. */
export async function devLogin(): Promise<string> {
  const sub = "dev-user";
  const boot = await devBootstrap({
    sub,
    tenant_name: "开发租户",
    email: "dev@example.com",
  });
  const tok = await devToken({
    sub,
    tenant_id: boot.tenant_id,
    email: "dev@example.com",
  });
  return tok.access_token;
}

// ---------- tenants ----------
// Two read scopes, mirroring the backend:
// - fetchTenants:   GET /tenants/   (any logged-in user; their own tenants)
// - fetchAllTenants: GET /tenants/all (super_admin only; every tenant + member_count)
export async function fetchTenants(): Promise<Tenant[]> {
  const { data } = await api.get<Tenant[]>("/tenants/");
  return data;
}

export async function fetchAllTenants(): Promise<Tenant[]> {
  const { data } = await api.get<Tenant[]>("/tenants/all");
  return data;
}

export async function createTenant(name: string): Promise<Tenant> {
  const { data } = await api.post<Tenant>("/tenants/", { name });
  return data;
}

export async function updateTenant(
  id: string,
  payload: TenantUpdate,
): Promise<Tenant> {
  const { data } = await api.put<Tenant>(`/tenants/${id}`, payload);
  return data;
}

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

// ---------- customers (global identity + per-store profile) ----------
// Two access patterns: store view (tenant-scoped CRUD on this store's profiles)
// and HQ view (cross-store aggregation, super_admin only).
//
// Store view: /customers/profiles/  — list/create/update/delete this tenant's
// profiles. If identity_key already exists globally, the backend reuses the
// existing Customer and creates only a new Profile (HTTP 201 either way).
export async function fetchCustomerProfiles(): Promise<CustomerProfileRead[]> {
  const { data } = await api.get<CustomerProfileRead[]>("/customers/profiles/");
  return data;
}

export async function createCustomerProfile(
  payload: CustomerProfileCreate,
): Promise<CustomerProfileRead> {
  const { data } = await api.post<CustomerProfileRead>(
    "/customers/profiles/",
    payload,
  );
  return data;
}

export async function updateCustomerProfile(
  id: string,
  payload: CustomerProfileUpdate,
): Promise<CustomerProfileRead> {
  const { data } = await api.put<CustomerProfileRead>(
    `/customers/profiles/${id}`,
    payload,
  );
  return data;
}

export async function deleteCustomerProfile(id: string): Promise<void> {
  await api.delete(`/customers/profiles/${id}`);
}

// HQ view: /customers/ and /customers/{id}/aggregate — cross-store list/detail
// (super_admin only). The list endpoint already returns every store's profiles
// expanded, so aggregate detail is a convenience for one customer.
export async function fetchCustomers(): Promise<CustomerRead[]> {
  const { data } = await api.get<CustomerRead[]>("/customers/");
  return data;
}

export async function fetchCustomerAggregate(id: string): Promise<CustomerRead> {
  const { data } = await api.get<CustomerRead>(`/customers/${id}/aggregate`);
  return data;
}

// Token 费用管理系列 3/4: aggregate AI usage attributed to a customer.
// Store users get their tenant's slice; cross-tenant viewers get the global sum.
export async function fetchCustomerUsage(
  id: string,
): Promise<CustomerUsage> {
  const { data } = await api.get<CustomerUsage>(`/customers/${id}/usage`);
  return data;
}

// Customer count for the dashboard card. Store scope = this store's profile
// counts; HQ scope (super_admin) = global identity counts. Mirrors the
// list_profiles dual-view split.
export async function fetchCustomerStatistics(): Promise<CustomerStatistics> {
  const { data } = await api.get<CustomerStatistics>("/customers/statistics");
  return data;
}

// ---------- billing (Token 费用管理系列 4/4) ----------
// Wallet read is split by scope, mirroring the backend:
// - fetchWallet:          GET /billing/wallet        (caller's own tenant)
// - fetchWalletByTenant:  GET /billing/wallet/{id}   (super_admin, any tenant)
// The own-wallet endpoint may return null (a brand-new tenant with no wallet);
// callers should handle null.
export async function fetchWallet(): Promise<Wallet | null> {
  const { data } = await api.get<Wallet | null>("/billing/wallet");
  return data;
}

export async function fetchWalletByTenant(
  tenantId: string,
): Promise<Wallet | null> {
  const { data } = await api.get<Wallet | null>(`/billing/wallet/${tenantId}`);
  return data;
}

// Caller's own tenant ledger. limit/offset match the backend Query defaults.
export async function fetchTransactions(params?: {
  limit?: number;
  offset?: number;
}): Promise<WalletTransaction[]> {
  const { data } = await api.get<WalletTransaction[]>("/billing/transactions", {
    params: { limit: params?.limit, offset: params?.offset },
  });
  return data;
}

// Usage detail (drill-down for dashboards). Returns rows + summary in one call.
export async function fetchUsage(params?: {
  limit?: number;
  offset?: number;
}): Promise<UsageDetail> {
  const { data } = await api.get<UsageDetail>("/billing/usage", {
    params: { limit: params?.limit, offset: params?.offset },
  });
  return data;
}

// Super-admin: credit a tenant's wallet. Returns the new ledger row.
export async function recharge(
  payload: RechargeRequest,
): Promise<WalletTransaction> {
  const { data } = await api.post<WalletTransaction>(
    "/billing/recharge",
    payload,
  );
  return data;
}

// Effective pricing for the caller (tenant overrides + platform defaults).
export async function fetchPricing(): Promise<ModelPricing[]> {
  const { data } = await api.get<ModelPricing[]>("/billing/pricing");
  return data;
}

// Idempotent on (tenant_id, model): re-POSTing the same scope+model updates.
export async function createPricing(
  payload: ModelPricingUpsert,
): Promise<ModelPricing> {
  const { data } = await api.post<ModelPricing>("/billing/pricing", payload);
  return data;
}

export async function updatePricing(
  id: string,
  payload: ModelPricingUpsert,
): Promise<ModelPricing> {
  const { data } = await api.put<ModelPricing>(
    `/billing/pricing/${id}`,
    payload,
  );
  return data;
}

// Soft-delete (deactivates the row) so historical charges stay interpretable.
export async function deletePricing(id: string): Promise<void> {
  await api.delete(`/billing/pricing/${id}`);
}

// ---------- agents ----------
export async function fetchAgents(): Promise<Agent[]> {
  const { data } = await api.get<Agent[]>("/agents/");
  return data;
}

export async function fetchAgent(id: string): Promise<Agent> {
  const { data } = await api.get<Agent>(`/agents/${id}`);
  return data;
}

export async function createAgent(payload: AgentCreate): Promise<Agent> {
  const { data } = await api.post<Agent>("/agents/", payload);
  return data;
}

export async function updateAgent(id: string, payload: AgentUpdate): Promise<Agent> {
  const { data } = await api.patch<Agent>(`/agents/${id}`, payload);
  return data;
}

export async function deleteAgent(id: string): Promise<void> {
  await api.delete(`/agents/${id}`);
}

// Agent count for the dashboard card. Store users count their tenant; super_admin
// counts every tenant (the service splits on platform_role).
export async function fetchAgentStatistics(): Promise<AgentStatistics> {
  const { data } = await api.get<AgentStatistics>("/agents/statistics");
  return data;
}

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

export async function fetchUser(id: string): Promise<UserFull> {
  const { data } = await api.get<UserFull>(`/users/${id}`);
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

// ---------- audit logs ----------

/** GET /logs — paginated, filterable audit log. Store users are auto-scoped to
 * their tenant; super_admin/hq_staff may pass tenant_id to narrow. */
export async function fetchLogs(
  filters?: LogFilters,
): Promise<SystemLogListResponse> {
  const { data } = await api.get<SystemLogListResponse>("/logs/", {
    params: {
      user_id: filters?.user_id,
      action: filters?.action,
      resource_type: filters?.resource_type,
      tenant_id: filters?.tenant_id,
      date_from: filters?.date_from,
      date_to: filters?.date_to,
      limit: filters?.limit,
      offset: filters?.offset,
    },
  });
  return data;
}

// ---------- roles ----------
export async function fetchRoles(): Promise<Role[]> {
  const { data } = await api.get<Role[]>("/roles/");
  return data;
}

export async function fetchRoleLabels(): Promise<RoleLabel[]> {
  const { data } = await api.get<RoleLabel[]>("/roles/label");
  return data;
}

export async function createRole(payload: RoleCreate): Promise<Role> {
  const { data } = await api.post<Role>("/roles/", payload);
  return data;
}

export async function updateRole(id: string, payload: RoleUpdate): Promise<Role> {
  const { data } = await api.put<Role>(`/roles/${id}`, payload);
  return data;
}

export async function deleteRole(id: string): Promise<void> {
  await api.delete(`/roles/${id}`);
}

// role ↔ permission grants (SCD2; writes resync casbin on the backend)
export async function fetchRolePermissions(
  id: string
): Promise<RolePermissionRead[]> {
  const { data } = await api.get<RolePermissionRead[]>(`/roles/${id}/permissions`);
  return data;
}

export async function grantRolePermission(
  id: string,
  payload: RolePermissionGrant
): Promise<RolePermissionRead> {
  const { data } = await api.post<RolePermissionRead>(
    `/roles/${id}/permissions`,
    payload
  );
  return data;
}

export async function revokeRolePermission(
  id: string,
  permissionId: string
): Promise<void> {
  await api.delete(`/roles/${id}/permissions/${permissionId}`);
}

// ---------- permissions ----------
// Only the matrix endpoint is wired up: it already carries the permission
// catalogue (its `permissions` array), so a separate catalogue call would be
// dead code. Add fetchPermissionCatalogue here if a future view needs it.
export async function fetchPermissionMatrix(): Promise<PermissionMatrix> {
  const { data } = await api.get<PermissionMatrix>("/permissions/matrix");
  return data;
}

// ---------- llm settings (platform + tenant) ----------
export async function fetchPlatformLlmConfig(): Promise<LlmConfig | null> {
  const { data } = await api.get<LlmConfig | null>("/settings/llm/platform");
  return data;
}

export async function updatePlatformLlmConfig(
  payload: LlmConfigUpdate
): Promise<LlmConfig> {
  const { data } = await api.put<LlmConfig>("/settings/llm/platform", payload);
  return data;
}

export async function fetchTenantLlmConfig(): Promise<LlmConfig | null> {
  const { data } = await api.get<LlmConfig | null>("/settings/llm/tenant");
  return data;
}

export async function updateTenantLlmConfig(
  payload: LlmConfigUpdate
): Promise<LlmConfig> {
  const { data } = await api.put<LlmConfig>("/settings/llm/tenant", payload);
  return data;
}

export async function fetchEffectiveModels(): Promise<string[]> {
  const { data } = await api.get<string[]>("/settings/models");
  return data;
}

// ---------- tenant branding config (white-label, priority 52) ----------
// Read is open to any authenticated user of the tenant (branding applies to
// everyone); write requires settings:update (owner/admin). The caller's tenant
// is resolved from the token, so there is no tenant_id in the URL.
export async function fetchTenantConfig(): Promise<TenantConfig | null> {
  const { data } = await api.get<TenantConfig | null>("/tenant-config");
  return data;
}

export async function updateTenantConfig(
  payload: TenantConfigUpdate,
): Promise<TenantConfig> {
  const { data } = await api.put<TenantConfig>("/tenant-config", payload);
  return data;
}

// ---------- api tokens (AtoA) ----------
// Issue/list/revoke tokens for external agents (agenthub CLI). The plaintext
// token is returned ONLY by createApiToken — store it immediately, it can never
// be fetched again.
export async function fetchApiTokens(): Promise<ApiToken[]> {
  const { data } = await api.get<ApiToken[]>("/api-tokens");
  return data;
}

export async function createApiToken(
  payload: ApiTokenCreate
): Promise<ApiTokenCreated> {
  const { data } = await api.post<ApiTokenCreated>("/api-tokens", payload);
  return data;
}

export async function revokeApiToken(id: string): Promise<void> {
  await api.delete(`/api-tokens/${id}`);
}

// ---------- auth (local login + sessions) ----------
export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", payload);
  return data;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

export async function fetchSessions(): Promise<SessionRead[]> {
  const { data } = await api.get<SessionRead[]>("/auth/sessions");
  return data;
}

export async function terminateSession(sessionId: string): Promise<void> {
  await api.delete(`/auth/sessions/${sessionId}`);
}

// ---------- conversations + chat (SSE streaming) ----------
//
// `sendChatStream` is the one endpoint that bypasses the axios `api` instance:
// SSE responses must be consumed frame-by-frame, and axios buffers the whole
// body (losing the streaming effect). We use a raw `fetch` + ReadableStream
// instead, manually attaching the bearer token (axios interceptor can't run)
// and replicating the client's 401 → auth-expired handling.

export async function fetchConversations(params?: {
  search?: string;
  tag?: string;
}): Promise<Conversation[]> {
  const { data } = await api.get<Conversation[]>("/conversations/", {
    params: { search: params?.search, tag: params?.tag },
  });
  return data;
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const { data } = await api.get<Message[]>(
    `/conversations/${conversationId}/messages`,
  );
  return data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`/conversations/${conversationId}`);
}

// conversation-management (priority 50): rename / tags / pin / star / batch.
// All gated by conversations:update (or :delete) on the backend; ownership is
// re-checked server-side (only the conversation owner may mutate it).
export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/conversations/${conversationId}/title`,
    { title },
  );
  return data;
}

export async function addConversationTag(
  conversationId: string,
  tag: string,
): Promise<Conversation> {
  const { data } = await api.post<Conversation>(
    `/conversations/${conversationId}/tags`,
    { tag },
  );
  return data;
}

export async function removeConversationTag(
  conversationId: string,
  tag: string,
): Promise<Conversation> {
  const { data } = await api.delete<Conversation>(
    `/conversations/${conversationId}/tags/${encodeURIComponent(tag)}`,
  );
  return data;
}

export async function setConversationPinned(
  conversationId: string,
  pinned: boolean,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/conversations/${conversationId}/pin`,
    { pinned },
  );
  return data;
}

export async function setConversationStarred(
  conversationId: string,
  starred: boolean,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/conversations/${conversationId}/star`,
    { starred },
  );
  return data;
}

export async function batchDeleteConversations(
  conversationIds: string[],
): Promise<{ deleted: number }> {
  const { data } = await api.post<{ deleted: number }>(
    "/conversations/batch-delete",
    { conversation_ids: conversationIds },
  );
  return data;
}

// Conversation counts (total + 7d/30d windows) for the dashboard card. Store
// users are scoped to their tenant; super_admin aggregates across tenants.
export async function fetchConversationStatistics(): Promise<ConversationStatistics> {
  const { data } = await api.get<ConversationStatistics>(
    "/conversations/statistics",
  );
  return data;
}

// ---------- dashboard analytics ----------
// /dashboard/trends backs the activity bar chart on both the store and HQ
// dashboards; /dashboard/overview is super_admin-only (platform totals +
// per-tenant activity Top N). Trends reuses conversations:read; overview is
// require_super_admin on the backend.
export async function fetchDashboardTrends(days: number): Promise<DashboardTrends> {
  const { data } = await api.get<DashboardTrends>("/dashboard/trends", {
    params: { days },
  });
  return data;
}

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
  const { data } = await api.get<DashboardOverview>("/dashboard/overview");
  return data;
}

// ---------- global cross-entity search (priority 51) ----------
// GET /search?q=&limit_per_type= fans a single query across agents / customers /
// conversations (+ users / tenants for super_admin / hq_staff). The backend
// enforces tenant scoping: store users see their own tenant; cross-tenant
// viewers additionally get users + tenants. Short queries (< 2 chars) return an
// empty result, so callers gate the request on q.length >= 2 to avoid noise.
export async function globalSearch(
  q: string,
  limitPerType = 5,
): Promise<GlobalSearchResult> {
  const { data } = await api.get<GlobalSearchResult>("/search", {
    params: { q, limit_per_type: limitPerType },
  });
  return data;
}

export interface ChatStreamChunk {
  delta?: string;
  error?: string;
}

export interface ChatStreamPayload {
  agent_id: string;
  conversation_id?: string;
  message: string;
  // Optional customer attribution (Token 费用管理系列 3/4). Only takes
  // effect when creating a new conversation (no conversation_id). Lets a
  // staff member tag a chat as "serving customer X" for usage attribution.
  customer_id?: string;
}

/**
 * Stream a chat reply from `POST /chat/stream` (Server-Sent Events).
 *
 * Yields `{ delta }` chunks as the assistant's reply arrives (for a typewriter
 * effect), `{ error }` if the server reports one mid-stream, then returns when
 * the `data: [DONE]` sentinel arrives. Pass an AbortSignal to cancel.
 */
export async function* sendChatStream(
  payload: ChatStreamPayload,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamChunk> {
  const token = getStoredToken();
  const resp = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!resp.ok) {
    // Replicate the axios interceptor's 401 handling: a stale token clears
    // local state and fires the event AuthProvider listens for (→ /login).
    if (resp.status === 401) {
      setStoredToken(null);
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    throw new Error(`对话请求失败: ${resp.status}`);
  }
  if (!resp.body) throw new Error("浏览器不支持流式响应");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; the last segment may be a
    // partial frame, so keep it buffered for the next read.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      const data = line.slice(line.indexOf(":") + 1).trim();
      if (data === "[DONE]") return;
      try {
        yield JSON.parse(data) as ChatStreamChunk;
      } catch {
        // Non-JSON frame (e.g. keep-alive comment) — skip.
      }
    }
  }
}

// ---------- in-app notifications (priority 54) ----------

/** GET /notifications — paginated notification list (own + tenant-wide). */
export async function fetchNotifications(
  filters?: NotificationFilters,
): Promise<NotificationListResponse> {
  const { data } = await api.get<NotificationListResponse>("/notifications/", {
    params: {
      unread_only: filters?.unread_only,
      limit: filters?.limit,
      offset: filters?.offset,
    },
  });
  return data;
}

/** GET /notifications/unread-count — lightweight bell badge poll. */
export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  const { data } = await api.get<UnreadCountResponse>("/notifications/unread-count");
  return data;
}

/** PUT /notifications/{id}/read — mark one notification read. */
export async function markNotificationRead(id: string): Promise<Notification> {
  const { data } = await api.put<Notification>(`/notifications/${id}/read`);
  return data;
}

/** PUT /notifications/read-all — mark every visible unread notification read. */
export async function markAllNotificationsRead(): Promise<UnreadCountResponse> {
  const { data } = await api.put<UnreadCountResponse>("/notifications/read-all");
  return data;
}

// ---------- CSV export (priority 55) ----------
// GET /exports/{entity} streams a UTF-8-BOM CSV attachment for one of
// customers / conversations / usage / logs. The response is a binary stream
// (axios responseType: "blob"), so callers hand the Blob to downloadBlob().
// Store users are auto-scoped to their tenant; super_admin / hq_staff may pass
// tenant_id to narrow. Date params are optional (default: last 30 days).

export type ExportEntity = "customers" | "conversations" | "usage" | "logs";

export interface ExportParams {
  date_from?: string;
  date_to?: string;
  /** super_admin / hq_staff only: narrow to one tenant. */
  tenant_id?: string;
}

/** Fetch a CSV export as a Blob. The caller triggers the browser download. */
export async function exportEntity(
  entity: ExportEntity,
  params?: ExportParams,
): Promise<Blob> {
  const resp = await api.get<Blob>(`/exports/${entity}`, {
    params: {
      date_from: params?.date_from,
      date_to: params?.date_to,
      tenant_id: params?.tenant_id,
    },
    responseType: "blob",
  });
  return resp.data;
}
