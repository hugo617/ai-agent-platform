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
  roles: string[];
}

export interface Conversation {
  id: string;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  created_at: string;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface ApiError {
  detail: string;
}
