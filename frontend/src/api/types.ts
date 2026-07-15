// Types aligned with the FastAPI backend's Pydantic schemas (app/schemas/*).
// Kept in sync manually; consider codegen (openapi-typescript) later.

export interface Tenant {
  id: string;
  name: string;
  // The four fields below are only populated by the platform-level endpoints
  // (GET /tenants/all, GET /tenants/{id}); the user-scoped GET /tenants/ (my
  // tenants) leaves them at their defaults. Kept optional so the existing
  // dashboard "my tenants" card (which only reads id/name) is unaffected.
  status?: string;
  description?: string | null;
  address?: string | null;
  member_count?: number;
  created_by?: string | null;
  created_at: string;
}

export interface TenantUpdate {
  name?: string;
  status?: string;
  description?: string;
  address?: string;
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

// Row-level data scope levels a role can carry (权限重构系列 3/4). See
// app/services/data_scope.py. The matrix UI exposes a selector for these.
export type DataScope = "all" | "tenant" | "group" | "self";

export interface Role {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_system: boolean;
  sort_order: number;
  status: string;
  data_scope: DataScope; // 权限重构系列 3/4,矩阵页可配置
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
  data_scope?: DataScope;
}

export interface RoleUpdate {
  name?: string;
  description?: string;
  sort_order?: number;
  status?: string;
  data_scope?: DataScope;
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
  // Chinese display labels sourced from the backend (OBJ_CN/ACT_CN/MENU_CN), so
  // the frontend renders the matrix without keeping its own label map.
  obj_label: string; // e.g. "智能体"
  act_label: string; // e.g. "查看"
  // "api" = real backend authorization unit (e.g. customers:read);
  // "menu" = UX-layer visibility (e.g. menu:agents). The matrix groups by it.
  type: string; // "api" | "menu"
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

// ============= embedding settings (RAG, priority 57) =============
// Separate from LlmConfig because embeddings target a different provider
// (DeepSeek does NOT expose embeddings; default is OpenAI).

export interface EmbeddingConfig {
  id: string;
  tenant_id: string | null; // null = platform-wide
  api_key_hint: string; // masked, e.g. "sk-***wxyz"
  base_url: string;
  model: string; // single model (no selectable list)
  is_active: boolean;
  updated_at: string;
}

export interface EmbeddingConfigUpdate {
  api_key?: string; // omit/empty = keep stored key
  base_url?: string;
  model?: string;
}

// ============= knowledge base / RAG (priority 57) =============

export interface DocumentRead {
  id: string;
  tenant_id: string;
  name: string;
  source_type: string; // "text" | "upload"
  content: string;
  chunk_count: number;
  status: string; // pending | indexed | failed
  created_at: string;
  updated_at: string;
}

export interface DocumentCreate {
  name: string;
  content: string;
  source_type?: "text" | "upload";
}

export interface RetrieveHit {
  content: string;
  score: number; // cosine similarity (0-1, higher = better)
  document_id: string;
  document_name: string;
}

export interface RetrieveResult {
  query: string;
  hits: RetrieveHit[];
}

// ============= tenant branding config (white-label, priority 52) =============

/** One tenant's white-label brand: display name, logo, theme color, login text.
 * null fields mean "use the platform default". One row per tenant. */
export interface TenantConfig {
  id: string;
  tenant_id: string;
  display_name: string | null; // overrides the default tenant name in the top bar
  logo_url: string | null;
  theme_color: string | null; // #RRGGBB; applied globally as the --primary CSS var
  login_text: string | null; // shown on the login page
  created_at: string;
  updated_at: string;
}

/** Payload for PUT /tenant-config. All fields optional; the frontend sends all
 * four on save, so null means "clear this field". theme_color is #RRGGBB. */
export interface TenantConfigUpdate {
  display_name: string | null;
  logo_url: string | null;
  theme_color: string | null;
  login_text: string | null;
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
  // All currently-effective permission codes (api like "customers:read" + menu
  // like "menu:agents"), aggregated by the backend from the user's roles.
  // Drives nav visibility + button guards. Empty for super_admin (frontend
  // bypasses on platform_role === "super_admin").
  permissions: string[];
  // Self-service profile fields (priority 49): exposed so the profile page can
  // pre-fill rather than starting blank.
  display_name?: string | null;
  real_name?: string | null;
  phone?: string | null;
  avatar?: string | null;
}

// Self-service profile edit (PUT /auth/me). Only editable profile columns —
// platform_role/status/username are intentionally absent so the caller cannot
// escalate. All optional: omit a field to leave it unchanged.
export interface ProfileUpdate {
  display_name?: string | null;
  real_name?: string | null;
  phone?: string | null;
  avatar?: string | null;
}

// Self-service password change (PUT /auth/me/password). old_password is
// verified against the stored bcrypt hash before the new one is applied.
export interface PasswordChange {
  old_password: string;
  new_password: string; // min 8 chars (backend-enforced)
}

export interface Conversation {
  id: string;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  // Optional customer attribution (Token 费用管理系列 3/4). Null = internal
  // staff query (not tied to a customer).
  customer_id: string | null;
  // conversation-management (priority 50). tags defaults to [] (backend
  // server_default '[]'); is_pinned/is_starred default false.
  tags: string[];
  is_pinned: boolean;
  is_starred: boolean;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

// conversation-management (priority 50): optional filters for the chat list.
// Both are substring/contains filters on the backend (title OR message content
// for search; tags array for tag). Empty/undefined = match all.
export interface ConversationFilters {
  search?: string;
  tag?: string;
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

/**
 * Aggregate AI usage attributed to a customer (Token 费用管理系列 3/4).
 * Powers the "AI 服务" dimension on the customer 360 view. Store-scoped for
 * tenant users; global for cross-tenant viewers.
 */
export interface CustomerUsage {
  customer_id: string;
  conversation_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost: number | null;
  last_active_at: string | null;
}

// ============= billing (Token 费用管理系列 4/4) =============
//
// Aligns with app/schemas/billing.py. The wallet carries the live balance +
// lifetime counters; transactions are the append-only ledger; pricing rows
// hold per-model token prices (platform default + tenant override).

/** The prepaid token wallet for one tenant (WalletRead). */
export interface Wallet {
  id: string;
  tenant_id: string;
  balance: number;
  total_recharged: number;
  total_consumed: number;
  low_balance_threshold: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** One append-only ledger row (recharge / consume / refund / adjust). */
export type WalletTransactionType =
  | "recharge"
  | "consume"
  | "refund"
  | "adjust";

export interface WalletTransaction {
  id: string;
  wallet_id: string;
  tenant_id: string;
  type: string;
  amount: number; // signed: +recharge -consume
  balance_after: number;
  usage_event_id: string | null;
  model: string | null;
  remark: string | null;
  operator_id: string | null;
  created_at: string;
}

/** Super-admin payload for POST /billing/recharge. */
export interface RechargeRequest {
  tenant_id: string;
  amount: number; // positive integer token count
  remark?: string;
}

/** One per-model pricing row (platform default or tenant override). */
export interface ModelPricing {
  id: string;
  tenant_id: string | null; // null = platform default; set = tenant override
  model: string;
  input_price_per_1k: number;
  output_price_per_1k: number;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** Payload for POST/PUT /billing/pricing. */
export interface ModelPricingUpsert {
  tenant_id?: string | null;
  model: string;
  input_price_per_1k: number;
  output_price_per_1k: number;
  currency?: string;
  is_active?: boolean;
}

/**
 * One usage-event row in the /billing/usage drill-down. The backend returns
 * these as a plain dict (not a Pydantic schema), so this mirrors that shape.
 */
export interface UsageEventItem {
  id: string;
  conversation_id: string | null;
  message_id: string | null;
  agent_id: string | null;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost: number | null;
  created_at: string | null;
}

/** Aggregate token totals returned alongside the usage rows. */
export interface UsageSummary {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/** Response shape of GET /billing/usage. */
export interface UsageDetail {
  items: UsageEventItem[];
  summary: UsageSummary;
}

// ============= dashboard analytics =============
//
// Aligns with app/schemas/dashboard.py + the per-entity statistics schemas
// (AgentStatistics / ConversationStatistics / CustomerStatistics). The dashboard
// page renders a store view (per-tenant stats + trend) and an HQ view
// (super_admin platform totals + per-tenant activity Top N).

/** GET /agents/statistics. Agents have no status column, so active === total. */
export interface AgentStatistics {
  total: number;
  active: number;
}

/** GET /conversations/statistics. Windows are on created_at. */
export interface ConversationStatistics {
  total: number;
  last_7d: number;
  last_30d: number;
}

/**
 * GET /customers/statistics. Store scope = live profile counts in this store;
 * HQ scope (super_admin) = global identity counts (Customer table).
 */
export interface CustomerStatistics {
  total: number;
  active: number;
  last_7d_new: number;
}

/** One day of activity in a DashboardTrends series. date is YYYY-MM-DD. */
export interface TrendPoint {
  date: string;
  conversations: number;
  messages: number;
}

/** GET /dashboard/trends?days=N. Points are oldest → newest, zero-filled. */
export interface DashboardTrends {
  days: number;
  points: TrendPoint[];
}

/** One store's activity for the HQ overview "store Top N" panel. */
export interface TenantActivityItem {
  tenant_id: string;
  tenant_name: string;
  conversations: number;
}

/** Platform-wide counts for the HQ overview cards. */
export interface PlatformTotals {
  tenants: number;
  users: number;
  conversations: number;
  agents: number;
  customers: number;
}

/** GET /dashboard/overview (super_admin only). */
export interface DashboardOverview {
  totals: PlatformTotals;
  top_tenants: TenantActivityItem[];
}

// ============= global cross-entity search (priority 51) =============
//
// GET /search?q=&limit_per_type= aggregates hits across agents / customers /
// conversations (+ users / tenants for super_admin / hq_staff). The top-bar
// dropdown renders each non-empty section as a clickable list; selecting an
// item navigates to that entity's list/detail page.

/** One lightweight search hit (id + label + type discriminator). */
export interface SearchResultItem {
  id: string;
  label: string;
  type: string;
}

/** Grouped cross-entity search response. Every key is always present. */
export interface GlobalSearchResult {
  agents: SearchResultItem[];
  customers: SearchResultItem[];
  conversations: SearchResultItem[];
  users: SearchResultItem[];
  tenants: SearchResultItem[];
}

/** Filter params for GET /logs (audit log). All optional. */
export interface LogFilters {
  user_id?: string;
  action?: string;
  resource_type?: string;
  tenant_id?: string; // super_admin/hq_staff only; ignored for store users
  date_from?: string; // ISO-8601
  date_to?: string; // ISO-8601
  limit?: number;
  offset?: number;
}

/** One audit-log row (read-side DTO). Mirrors SystemLogRead. */
export interface SystemLog {
  id: string;
  level: string;
  action: string;
  module: string;
  message: string;
  details_json: Record<string, unknown> | null;
  resource_type: string | null;
  resource_id: string | null;
  old_values: Record<string, unknown> | null; // before snapshot
  new_values: Record<string, unknown> | null; // after snapshot
  user_id: string | null; // operator (FK users), NOT operator_id
  session_id: string | null;
  tenant_id: string | null;
  user_agent: string | null;
  ip: string | null;
  request_id: string | null;
  duration_ms: number | null;
  created_at: string;
}

/** Paginated audit-log envelope (GET /logs). */
export interface SystemLogListResponse {
  items: SystemLog[];
  total: number;
  limit: number;
  offset: number;
}

// ============= in-app notifications (priority 54) =============

/** One in-app notification row. Mirrors app/schemas/notification.py NotificationRead. */
export interface Notification {
  id: string;
  tenant_id: string | null;
  // null = tenant-wide broadcast (every user in the tenant sees it).
  user_id: string | null;
  // balance_warning | recharge | role_change | usage_report | system
  type: string;
  title: string;
  content: string;
  // Optional in-app path the bell navigates to on click (e.g. "/billing").
  link: string | null;
  is_read: boolean;
  created_at: string;
}

/** Paginated notification envelope (GET /notifications). */
export interface NotificationListResponse {
  items: Notification[];
  total: number;
  limit: number;
  offset: number;
}

/** Reply for the bell's badge poll (GET /notifications/unread-count). */
export interface UnreadCountResponse {
  count: number;
}

/** Filter params for GET /notifications. */
export interface NotificationFilters {
  unread_only?: boolean;
  limit?: number;
  offset?: number;
}
