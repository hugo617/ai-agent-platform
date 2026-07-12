import axios from "axios";
import { api, getStoredToken, setStoredToken, AUTH_EXPIRED_EVENT } from "./client";
import type {
  Agent,
  AgentCreate,
  AgentUpdate,
  ApiToken,
  ApiTokenCreate,
  ApiTokenCreated,
  Conversation,
  LlmConfig,
  LlmConfigUpdate,
  LoginRequest,
  Member,
  MemberCreate,
  MemberUpdate,
  Message,
  MeResponse,
  PermissionMatrix,
  Role,
  RoleCreate,
  RoleLabel,
  RolePermissionGrant,
  RolePermissionRead,
  RoleUpdate,
  SessionRead,
  Tenant,
  TokenResponse,
  UserFilters,
  UserFormData,
  UserFull,
  UserListResponse,
  UserStatistics,
  UserStatus,
} from "./types";

// ---------- auth ----------
export async function fetchMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/auth/me");
  return data;
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
export async function fetchTenants(): Promise<Tenant[]> {
  const { data } = await api.get<Tenant[]>("/tenants/");
  return data;
}

export async function createTenant(name: string): Promise<Tenant> {
  const { data } = await api.post<Tenant>("/tenants/", { name });
  return data;
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

export async function fetchConversations(): Promise<Conversation[]> {
  const { data } = await api.get<Conversation[]>("/conversations/");
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

export interface ChatStreamChunk {
  delta?: string;
  error?: string;
}

export interface ChatStreamPayload {
  agent_id: string;
  conversation_id?: string;
  message: string;
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
