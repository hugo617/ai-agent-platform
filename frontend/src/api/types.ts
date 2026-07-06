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
