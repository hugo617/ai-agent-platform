/**
 * queries/ core — shared foundation for all domain query hooks.
 *
 * Extracted from the original queries.ts monolith
 * (plan-queries-endpoints-domain-split.md). Pure locality move: zero behaviour
 * change. Holds the qk query-key factory (centralised invalidation invariant)
 * and the useApiMutation helper (68× leverage — every write hook shares it).
 *
 * Domain files import ``{ qk, useApiMutation }`` from here; the ``queries.ts``
 * barrel re-exports everything so ``@/hooks/queries`` callers are unchanged.
 */
import {
  useMutation,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import type {
  ConversationFilters,
  LogFilters,
  NotificationFilters,
  UserFilters,
} from "@/api/types";

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
  permissionCatalogue: (type?: "api" | "menu") =>
    ["permissions", "catalogue", type ?? "all"] as const,
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
  // knowledge base documents (RAG, priority 57). Key is parameterised by the
  // optional {scope, category_id} filter (knowledge-tiered reader-ui slice 01)
  // so each distinct filter set caches independently — clicking a different
  // category in the tree produces a new key and refetches only that cell.
  // Empty filter collapses to the bare key for the common unfiltered case.
  documents: (filter?: { scope?: string; category_id?: string }) =>
    (filter && (filter.scope || filter.category_id)
      ? (["knowledge", "documents", filter] as const)
      : (["knowledge", "documents"] as const)),
  // knowledge-tiered reader-ui slice 01 G6 — categories for the left-pane tree.
  // Flat key (no params): the category list is one global read per caller role.
  knowledgeCategories: ["knowledge", "categories"] as const,
  // knowledge-tiered admin-ui slice 02 — per-doc distribution list. Keyed by
  // docId so each doc's "管理下发" dialog caches independently; revoke (a write)
  // invalidates by the same key so the list refetches the flipped is_active.
  documentDistributions: (docId: string) =>
    ["knowledge", "documents", docId, "distributions"] as const,
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
  // devices: tenant-scoped device instances (devices-crud-ui). Single read key
  // covers both store (Device) and HQ (DeviceHqRead) views — the endpoint
  // branches on platform_role, but cache invalidation is the same either way.
  devices: ["devices"] as const,
  // device-models: platform-level catalogue dropdown source. Read is open to
  // any authenticated user; the picker only needs {id, name, specs}.
  deviceModels: ["device-models"] as const,
  // bookings (device-booking 系列 3/4). Single read key covers both store
  // (Booking) and HQ (BookingHqRead) views — the endpoint branches on
  // platform_role, but cache invalidation is the same either way. deviceSchedule
  // is keyed by device + range so each device's grid caches independently — a
  // dedicated top-level family ("device-schedule") so every device's grid
  // invalidates with one prefix invalidate after a reschedule/cancel;
  // myBookings is the customer-principal own view (GET /me/bookings).
  bookings: ["bookings"] as const,
  deviceSchedule: (deviceId: string, start?: string, end?: string) =>
    ["device-schedule", deviceId, start ?? null, end ?? null] as const,
  myBookings: ["me", "bookings"] as const,
  // booking-schedule-grid 切片 02/04b: per-store single-day grid feed
  // (GET /bookings/schedule-grid). Keyed by [target tenant, date] so each
  // store×day caches independently — switching target or paging the date
  // refetches only that one cell. The literal-prefix ["schedule-grid"]
  // family lets a write (create/reschedule/cancel) invalidate every open
  // grid in one shot (added to BOOKING_WRITE_KEYS below).
  tenantSchedule: (tenantId: string, dateISO: string) =>
    ["schedule-grid", tenantId, dateISO] as const,
  // booking schedule-grid config (booking-schedule-grid 切片 01/03). Two-level
  // config: platform default row + per-tenant overrides. The grid reads the
  // MERGED view (effective); the config Dialog reads/writes each tier.
  //
  // P4: the invalidate set below is deliberately a SEPARATE family from
  // BOOKING_WRITE_KEYS — a config write should refresh config reads (effective
  // + platform + tenant reads), NOT booking rows. Folding it into
  // BOOKING_WRITE_KEYS would be misleading (it'd over-invalidate booking
  // caches on every config save) and would couple two unrelated concerns.
  // The literal-prefix family ["booking-config"] matches the existing
  // convention (see useDeleteConversation's ["conversations"]).
  bookingConfig: ["booking-config"] as const,
  bookingConfigEffective: ["booking-config", "effective"] as const,
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
export function useApiMutation<TVars, TData>(
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

