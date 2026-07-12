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

// ============= roles =============

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
  description: string;
  temperature: number;
  max_tokens: number | null;
  top_p: number | null;
  created_at: string;
}

export interface AgentCreate {
  name: string;
  system_prompt?: string;
  model?: string;
  description?: string;
  temperature?: number;
  max_tokens?: number | null;
  top_p?: number | null;
}

export interface AgentUpdate {
  name?: string;
  system_prompt?: string;
  model?: string;
  description?: string;
  temperature?: number;
  max_tokens?: number | null;
  top_p?: number | null;
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

// ============= groups (platform-level org + tenant attachment) =============

/** Minimal tenant info embedded in a GroupRead (aligns with app/schemas/group.py). */
export interface TenantBrief {
  id: string;
  name: string | null;
}

/** A platform-level group (business org) with its attached tenants expanded. */
export interface Group {
  id: string;
  name: string;
  code: string | null;
  address: string | null;
  description: string | null;
  status: string;
  sort_order: number;
  tenant_ids: string[];
  tenants: TenantBrief[];
  created_at: string;
  updated_at: string;
}

export interface GroupCreate {
  name: string;
  code?: string;
  address?: string;
  description?: string;
  status?: string;
  sort_order?: number;
  tenant_ids?: string[];
}

export interface GroupUpdate {
  name?: string;
  code?: string;
  address?: string;
  description?: string;
  status?: string;
  sort_order?: number;
}

// ============= customers (global identity + per-store profile) =============
//
// Two read shapes mirror the two access patterns on the backend:
// - CustomerProfileRead — the *store* view: this tenant's profile + global identity
// - CustomerRead        — the *HQ* (super_admin) view: global identity + every store profile

/** Minimal global-identity info, embedded in a store profile read. */
export interface CustomerBrief {
  id: string;
  identity_key: string;
  name: string;
  gender: string | null;
  birthday: string | null;
  avatar: string | null;
}

/** A per-store profile summary, embedded in a cross-store CustomerRead. */
export interface CustomerProfileBrief {
  id: string;
  tenant: TenantBrief;
  remark: string | null;
  tags: Record<string, unknown>;
  status: string;
  last_visit_at: string | null;
}

/** What a store user sees: their profile + the global identity. */
export interface CustomerProfileRead {
  id: string;
  customer_id: string;
  tenant_id: string;
  remark: string | null;
  tags: Record<string, unknown>;
  status: string;
  last_visit_at: string | null;
  created_at: string;
  updated_at: string;
  customer: CustomerBrief;
}

/** Create a customer in *this* store (reuses global identity if identity_key exists). */
export interface CustomerProfileCreate {
  identity_key: string;
  name: string;
  gender?: string;
  birthday?: string;
  remark?: string;
  tags?: Record<string, unknown>;
  status?: string;
}

/** Update a store profile (global-identity fields sync to the Customer). */
export interface CustomerProfileUpdate {
  name?: string;
  gender?: string;
  birthday?: string;
  remark?: string;
  tags?: Record<string, unknown>;
  status?: string;
}

/** What super_admin sees: global identity + every store's profile (cross-store aggregation). */
export interface CustomerRead {
  id: string;
  identity_key: string;
  name: string;
  gender: string | null;
  birthday: string | null;
  avatar: string | null;
  created_at: string;
  updated_at: string;
  profiles: CustomerProfileBrief[];
  profile_count: number;
}

export interface ApiError {
  detail: string;
}
