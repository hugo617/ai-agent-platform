// Types aligned with the FastAPI backend's Pydantic schemas (app/schemas/*).
// Kept in sync manually; consider codegen (openapi-typescript) later.

export interface Tenant {
  id: string;
  name: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
}

// A tenant member = (user, role) pair. Used by the user-management page.
export interface Member {
  user_id: string;
  role: string;
  email: string | null;
  display_name: string | null;
  joined_at: string | null;
}

export interface MemberCreate {
  user_id: string;
  role: string;
  email?: string | null;
  display_name?: string | null;
}

export interface MemberUpdate {
  role: string;
}

export interface UserTenant {
  tenant: Tenant;
  role: string;
}

// ============= Full user CRUD (aligns with backend /api/v1/users) =============

export type UserStatus = "active" | "inactive" | "locked";

export interface RoleBrief {
  id: string;
  name: string;
  code: string;
}

export interface OrganizationBrief {
  id: string;
  name: string;
  code: string | null;
}

export interface UserFull {
  id: string;
  username: string | null;
  email: string | null;
  display_name: string | null;
  real_name: string | null;
  phone: string | null;
  avatar: string | null;
  status: UserStatus;
  role: RoleBrief | null;
  organizations: OrganizationBrief[];
  last_login_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  // Cross-tenant fields (set only for super admin).
  tenant_id: string | null;
  tenant_name: string | null;
}

export interface UserFormData {
  username: string;
  email: string;
  password?: string;
  display_name?: string;
  real_name?: string;
  phone?: string;
  avatar?: string;
  role: string;
  organization_ids: string[];
  status: UserStatus;
}

export interface UserFilters {
  search?: string;
  status?: UserStatus | "all";
  role?: string | "all";
  sort_by?: "created_at" | "username" | "email";
  sort_order?: "asc" | "desc";
  page?: number;
  limit?: number;
}

export interface UserListResponse {
  items: UserFull[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface UserStatistics {
  total: number;
  active: number;
  inactive: number;
  locked: number;
  recent_logins: number;
  new_this_month: number;
}

// ============= roles / organizations =============

export interface Role {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_system: boolean;
  sort_order: number;
  status: string;
  created_at: string | null;
}

export interface RoleLabel {
  id: string;
  name: string;
  code: string;
}

export interface RoleCreate {
  name: string;
  code: string;
  description?: string;
  sort_order?: number;
}

export interface RoleUpdate {
  name?: string;
  description?: string;
  sort_order?: number;
  status?: string;
}

// role ↔ permission grants (SCD2; aligns with app/schemas/rbac.py)
export interface RolePermissionGrant {
  obj: string;
  act: string;
}

export interface RolePermissionRead {
  id: string;
  role_id: string;
  permission_id: string;
  obj: string;
  act: string;
  valid_from: string;
  valid_to: string | null;
}

// permission catalogue + aggregated matrix (read-only views; aligns with
// app/schemas/rbac.py PermissionItem / PermissionMatrix)
export interface PermissionItem {
  id: string;
  code: string; // "<obj>:<act>"
  name: string;
  obj: string;
  act: string;
}

export interface PermissionMatrix {
  roles: Role[];
  permissions: PermissionItem[];
  // [role.code][permission.code] → granted (SCD2 current state)
  matrix: Record<string, Record<string, boolean>>;
}

export interface Organization {
  id: string;
  tenant_id: string;
  name: string;
  code: string | null;
  path: string | null;
  parent_id: string | null;
  leader_id: string | null;
  status: string;
  sort_order: number;
  created_at: string | null;
}

export interface OrganizationTreeNode extends Organization {
  children: OrganizationTreeNode[];
}

export interface OrganizationCreate {
  name: string;
  code?: string;
  parent_id?: string | null;
  leader_id?: string | null;
  sort_order?: number;
}

export interface OrganizationUpdate {
  name?: string;
  code?: string | null;
  parent_id?: string | null;
  leader_id?: string | null;
  status?: string;
  sort_order?: number;
}

// ============= LLM settings =============

export interface LlmConfig {
  id: string;
  tenant_id: string | null; // null = platform-wide
  api_key_hint: string; // masked, e.g. "sk-***wxyz"
  base_url: string;
  default_model: string;
  available_models: string[];
  is_active: boolean;
  updated_at: string;
}

export interface LlmConfigUpdate {
  api_key?: string; // omit/empty = keep stored key
  base_url?: string;
  default_model?: string;
  available_models?: string[];
}

// ============= auth (local login + sessions) =============

export interface LoginRequest {
  username?: string;
  email?: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  tenant_id: string;
}

export interface SessionRead {
  id: string;
  session_id: string;
  device_type: string | null;
  device_name: string | null;
  platform: string | null;
  ip_address: string | null;
  user_agent: string | null;
  is_active: boolean;
  expires_at: string;
  created_at: string;
  last_accessed_at: string;
}

export interface Agent {
  id: string;
  tenant_id: string;
  name: string;
  system_prompt: string;
  model: string;
  created_at: string;
}

export interface AgentCreate {
  name: string;
  system_prompt?: string;
  model?: string;
}

export interface AgentUpdate {
  name?: string;
  system_prompt?: string;
  model?: string;
}

export interface MeResponse {
  user_id: string;
  tenant_id: string | null;
  email: string | null;
  platform_role: string | null;
  roles: string[];
}

export interface Conversation {
  id: string;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

// ============= API tokens (AtoA — agenthub CLI auth) =============

/** Masked token row returned by GET /api-tokens — no plaintext, no ciphertext. */
export interface ApiToken {
  id: string;
  name: string;
  token_prefix: string; // e.g. "ahp_***wxyz"
  token_type: string; // "pat" (personal access token); reserved for future OAuth
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
}

/** Payload for POST /api-tokens (issue a new token). */
export interface ApiTokenCreate {
  name: string;
  expires_at?: string | null; // ISO datetime; null/omitted = never expires
  scopes?: string[];
}

/** One-time response to issuing a token — includes the plaintext token. */
export interface ApiTokenCreated extends ApiToken {
  token_id: string;
  token: string; // plaintext; returned only here, never retrievable again
}

export interface ApiError {
  detail: string;
}
