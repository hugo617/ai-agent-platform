import axios from "axios";
import { api } from "./client";
import type {
  Agent,
  AgentCreate,
  AgentUpdate,
  LoginRequest,
  Member,
  MemberCreate,
  MemberUpdate,
  MeResponse,
  Organization,
  OrganizationCreate,
  OrganizationTreeNode,
  Role,
  RoleCreate,
  RoleLabel,
  SessionRead,
  Tenant,
  TokenResponse,
  UserFilters,
  UserFormData,
  UserFull,
  UserListResponse,
  UserStatistics,
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
  status: string
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

export async function deleteRole(id: string): Promise<void> {
  await api.delete(`/roles/${id}`);
}

// ---------- organizations ----------
export async function fetchOrganizationTree(): Promise<OrganizationTreeNode[]> {
  const { data } = await api.get<OrganizationTreeNode[]>("/organizations/tree");
  return data;
}

export async function fetchOrganizations(): Promise<Organization[]> {
  const { data } = await api.get<Organization[]>("/organizations/");
  return data;
}

export async function createOrganization(
  payload: OrganizationCreate
): Promise<Organization> {
  const { data } = await api.post<Organization>("/organizations/", payload);
  return data;
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
