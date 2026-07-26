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
  bindDeviceCustomer,
  cancelBooking,
  changePassword,
  changeUserStatus,
  createAgent,
  createApiToken,
  createBooking,
  createCustomerProfile,
  createDevice,
  createDeviceModel,
  createGroup,
  createPricing,
  createRole,
  createTenant,
  createUser,
  deleteAgent,
  deleteConversation,
  deleteCustomerProfile,
  deleteDevice,
  deleteDeviceModel,
  deleteGroup,
  deletePricing,
  deleteRole,
  deleteUser,
  detachSpecialist,
  detachTenant,
  endBooking,
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
  fetchBooking,
  fetchBookings,
  fetchEffectiveBookingConfig,
  fetchPlatformBookingConfig,
  fetchTenantBookingConfig,
  fetchTenantBookingsByDate,
  fetchDeviceModels,
  fetchDevices,
  fetchDeviceSchedule,
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
  fetchMyBookings,
  fetchPermissionCatalogue,
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
  noShowBooking,
  recharge,
  removeConversationTag,
  removeMember,
  renameConversation,
  resetUserPassword,
  revokeApiToken,
  revokeRolePermission,
  setConversationPinned,
  setConversationStarred,
  startBooking,
  unbindDeviceCustomer,
  updateAgent,
  updateBooking,
  updateCustomerProfile,
  updateDevice,
  updateDeviceModel,
  updateGroup,
  updateMe,
  updateMember,
  updatePricing,
  updatePlatformBookingConfig,
  updateTenantBookingConfig,
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
  BookingConfigUpsert,
  BookingCreate,
  BookingEndPayload,
  BookingUpdate,
  ConversationFilters,
  CustomerProfileCreate,
  CustomerProfileUpdate,
  DeviceCreate,
  DeviceModelCreate,
  DeviceModelUpdate,
  DeviceUpdate,
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

// ---------- devices (设备实例 CRUD, devices-crud-ui 系列 2/4) ----------
//
// useDevices drives the /devices page list for both store view (Device[]) and
// HQ panorama (DeviceHqRead[]) — the endpoint branches on platform_role, but
// the cache key is the same. Writes invalidate qk.devices so the list refreshes;
// bind/unbind also invalidate (they mutate customer_id, which the list shows).
//
// useDeviceModels feeds both the store create/edit dialog's model dropdown
// (tenant users get DeviceModelPublic) and the super_admin catalogue page
// (DeviceModelRead). The endpoint branches on platform_role; callers narrow the
// union at render. `enabled` defaults to true — callers that want to suppress
// the fetch (e.g. HQ read-only view) pass `enabled=false`, mirroring useAllTenants.
export function useDevices() {
  return useQuery({ queryKey: qk.devices, queryFn: fetchDevices });
}

export function useCreateDevice() {
  // DeviceCreate.tenant_id (optional) carries the cross-store target for
  // platform writers; store principals omit it. No signature change — the
  // caller just includes ``tenant_id`` in the payload (platform-cross-tenant-
  // write plan §4.5.4a 补丁 1).
  return useApiMutation(
    (payload: DeviceCreate) => createDevice(payload),
    [qk.devices],
  );
}

export function useUpdateDevice() {
  // DeviceUpdate.tenant_id carries the platform-writer target like create.
  return useApiMutation(
    ({ id, payload }: { id: string; payload: DeviceUpdate }) =>
      updateDevice(id, payload),
    [qk.devices],
  );
}

// ``tenantId`` is the platform-writer cross-store target. We pass it through
// the hook closure rather than per-call so the store call site stays
// ``deleteMut.mutateAsync(id)`` (zero behaviour change for store callers +
// their tests). Platform callers (devices HqView) construct the hook with the
// selected target and the same ``mutateAsync(id)`` call transparently carries
// the target. ``tenantId`` undefined (store path) → no query param sent →
// backend uses ``user.tenant_id`` (plan §4.5.4a 补丁 1).
export function useDeleteDevice(tenantId?: string) {
  return useApiMutation(
    (id: string) => deleteDevice(id, tenantId),
    [qk.devices],
  );
}

export function useBindDeviceCustomer(tenantId?: string) {
  // Same closure pattern as useDeleteDevice. ``tenantId`` → body field
  // ``tenant_id`` (POST has a body); undefined (store path) omits the field.
  return useApiMutation(
    ({ deviceId, customerId }: { deviceId: string; customerId: string }) =>
      bindDeviceCustomer(deviceId, customerId, tenantId),
    [qk.devices],
  );
}

export function useUnbindDeviceCustomer(tenantId?: string) {
  // Same closure pattern as useDeleteDevice (query param on DELETE).
  return useApiMutation(
    (deviceId: string) => unbindDeviceCustomer(deviceId, tenantId),
    [qk.devices],
  );
}

export function useDeviceModels(enabled = true) {
  return useQuery({
    queryKey: qk.deviceModels,
    queryFn: fetchDeviceModels,
    enabled,
  });
}

// ---------- device-models admin writes (device-models-admin-ui,
//           super_admin catalogue management) ----------
//
// Reads reuse useDeviceModels above — the endpoint branches on platform_role,
// super_admin / hq_staff get DeviceModelRead (full fields), tenant users get
// DeviceModelPublic (dropdown view). The admin page (RequireSuperAdmin route)
// narrows the union to DeviceModelRead[] at render. These three mutations are
// super_admin-only writes (require_super_admin on the backend; RequireSuperAdmin
// route guard is the UX layer) that invalidate qk.deviceModels so every consumer
// (store dropdown + admin list) refreshes.
export function useCreateDeviceModel() {
  return useApiMutation(
    (payload: DeviceModelCreate) => createDeviceModel(payload),
    [qk.deviceModels],
  );
}

export function useUpdateDeviceModel() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: DeviceModelUpdate }) =>
      updateDeviceModel(id, payload),
    [qk.deviceModels],
  );
}

export function useDeleteDeviceModel() {
  return useApiMutation(
    (id: string) => deleteDeviceModel(id),
    [qk.deviceModels],
  );
}

// ---------- bookings (设备预约订单, device-booking 系列 3/4) ----------
//
// useBookings drives the /bookings page list for both store view (Booking[])
// and HQ panorama (BookingHqRead[]) — the endpoint branches on platform_role,
// but the cache key is the same. Writes invalidate qk.bookings so the list
// refreshes; they also invalidate the device-schedule family (a
// reschedule/cancel moves a booking between days, so any open device grid is
// stale — ["device-schedule"] prefixes every device's grid) and qk.myBookings
// (a customer's own view would otherwise lag behind).
//
// useDeviceSchedule is keyed by device + range so each device's grid caches
// independently; pass start/end as ISO strings (backend defaults to today ±7d
// when both are omitted). useMyBookings is the customer-principal own view
// (GET /me/bookings) — a store-staff token 403s there, so callers gate it on
// the caller having a customer identity (slice 07 wires that gate).
//
// BOOKING_WRITE_KEYS is the shared invalidate set for the three write hooks;
// see useDeleteConversation for the same literal-prefix-family convention.
// Includes ["schedule-grid"] (booking-schedule-grid 切片 04b): a create /
// reschedule / cancel moves a booking onto / off a day, so any open HQ grid
// is stale until refetched.
const BOOKING_WRITE_KEYS: QueryKey[] = [
  qk.bookings,
  ["device-schedule"],
  qk.myBookings,
  ["schedule-grid"],
];

export function useBookings() {
  return useQuery({ queryKey: qk.bookings, queryFn: fetchBookings });
}

/** One store's bookings for a single calendar day (booking-schedule-grid
 * 切片 02 endpoint, 切片 04b hook). Powers the HQ schedule grid. ``tenantId``
 * is REQUIRED for platform roles (HQ passes its picked target) and MUST be
 * omitted by store roles (anti-forgery). ``dateISO`` is "YYYY-MM-DD".
 * Gated on a truthy ``tenantId`` so the HQ grid doesn't fire before a target
 * is picked (the store path doesn't reach this hook — StoreView keeps its
 * ScheduleGridCard). */
export function useTenantBookingsByDate(
  tenantId: string | undefined,
  dateISO: string,
) {
  return useQuery({
    queryKey: qk.tenantSchedule(tenantId ?? "", dateISO),
    queryFn: () => fetchTenantBookingsByDate(dateISO, tenantId),
    enabled: !!tenantId,
  });
}

/** One booking (GET /bookings/{id}). Branches on platform_role like the list:
 * Booking for tenant roles, BookingHqRead for super_admin / hq_staff. Gated on
 * a non-empty id so the detail dialog doesn't fire before a row is selected. */
export function useBooking(id: string | null | undefined) {
  return useQuery({
    queryKey: [...qk.bookings, id ?? ""],
    queryFn: () => fetchBooking(id as string),
    enabled: !!id,
  });
}

export function useCreateBooking() {
  // BookingCreate.tenant_id carries the platform-writer target like
  // DeviceCreate; store callers omit the field. No signature change.
  return useApiMutation(
    (payload: BookingCreate) => createBooking(payload),
    BOOKING_WRITE_KEYS,
  );
}

export function useUpdateBooking() {
  // BookingUpdate.tenant_id carries the platform-writer target like create.
  return useApiMutation(
    ({ id, payload }: { id: string; payload: BookingUpdate }) =>
      updateBooking(id, payload),
    BOOKING_WRITE_KEYS,
  );
}

// ``tenantId`` is the platform-writer cross-store target (→ ?tenant_id= query,
// plan §4.5.4a 补丁 5). Closure pattern — store call site stays
// ``cancelMut.mutateAsync(id)``. Platform HqView constructs the hook with the
// selected target so the same ``mutateAsync(id)`` call transparently carries
// it. ``tenantId`` undefined (store path) → no query param → backend uses
// ``user.tenant_id``.
export function useCancelBooking(tenantId?: string) {
  return useApiMutation(
    (id: string) => cancelBooking(id, tenantId),
    BOOKING_WRITE_KEYS,
  );
}

/** Start a booking (POST /bookings/{id}/start, device-poweron 切片 02) —
 * pending/confirmed → in_service. Invalidates the same ``BOOKING_WRITE_KEYS``
 * set as the other writes so the customer's own list (``qk.myBookings``), the
 * store list (``qk.bookings``) and any open device grid all refresh.
 *
 * Slice 02 wires only this one; ``useEndBooking`` / ``useNoShowBooking`` land
 * in slice 03 alongside the store「结束」/「爽约」buttons (no pre-built empty
 * scaffolding, 铁律6).
 *
 * ``tenantId`` (platform-cross-tenant-write plan §4.5.4a 补丁 5) is the
 * platform-writer cross-store target; closure pattern — store callers omit it
 * (zero behaviour change). */
export function useStartBooking(tenantId?: string) {
  return useApiMutation(
    (id: string) => startBooking(id, tenantId),
    BOOKING_WRITE_KEYS,
  );
}

/** End a booking (POST /bookings/{id}/end, device-poweron 切片 03) —
 * in_service → done, backend fills ``ended_at`` + persists optional
 * ``feedback``. Authorization: store owner only (``bookings:delete``).
 *
 * The mutation accepts ``{ id, payload? }`` so callers can pass the optional
 * feedback dict gathered from the store「结束服务」dialog; omitting payload ends
 * the booking with no service note. Invalidates the same ``BOOKING_WRITE_KEYS``
 * set as the other writes so the store list / device grids all refresh.
 *
 * ``tenantId`` (platform-cross-tenant-write plan §4.5.4a 补丁 5) is the
 * platform-writer cross-store target (orthogonal to the feedback body);
 * closure pattern — store callers omit it (zero behaviour change). */
export function useEndBooking(tenantId?: string) {
  return useApiMutation(
    ({ id, payload }: { id: string; payload?: BookingEndPayload }) =>
      endBooking(id, payload, tenantId),
    BOOKING_WRITE_KEYS,
  );
}

/** Mark a booking as no-show (POST /bookings/{id}/no-show, device-poweron 切片 03)
 * — pending / confirmed / in_service → no_show. Pure status flip (no body, 204
 * like ``/cancel``). Authorization: store owner only.
 *
 * ``tenantId`` (platform-cross-tenant-write plan §4.5.4a 补丁 5) is the
 * platform-writer cross-store target; closure pattern — store callers omit it. */
export function useNoShowBooking(tenantId?: string) {
  return useApiMutation(
    (id: string) => noShowBooking(id, tenantId),
    BOOKING_WRITE_KEYS,
  );
}

/** Day-grouped booking grid for one device in [start, end). ``enabled`` gates
 * the fetch (callers suppress it until a device is selected). */
export function useDeviceSchedule(
  deviceId: string | null | undefined,
  start?: string,
  end?: string,
) {
  return useQuery({
    queryKey: qk.deviceSchedule(deviceId ?? "", start, end),
    queryFn: () => fetchDeviceSchedule(deviceId as string, start, end),
    enabled: !!deviceId,
  });
}

/** The calling customer-principal's own bookings (GET /me/bookings). Store-
 * staff principals 403 here; callers gate on the caller having a customer
 * identity (slice 07). */
export function useMyBookings() {
  return useQuery({ queryKey: qk.myBookings, queryFn: fetchMyBookings });
}

// ---------- booking schedule-grid config (booking-schedule-grid 切片 03) ----------
//
// Five hooks mirror the backend /bookings/config router. The two writes
// (updatePlatform / updateTenant) invalidate BOOKING_CONFIG_WRITE_KEYS — the
// literal-prefix ["booking-config"] family covers effective + platform + any
// tenant read, so every open consumer refetches after a config save. P4 keeps
// this set separate from BOOKING_WRITE_KEYS on purpose (see qk.bookingConfig).
//
// effective / tenant hooks are parameterised by tenantId to thread the
// anti-forgery contract through: platform roles MUST name their target store
// (the HQ view passes its picked targetTenantId), store roles MUST omit it
// (resolved server-side from the token). Passing ``undefined`` on the store
// path → no query param → backend uses user.tenant_id.
//
// BOOKING_CONFIG_WRITE_KEYS is the shared invalidate set for the two config
// writes; same literal-prefix-family convention as BOOKING_WRITE_KEYS above.
// References qk.bookingConfig (not a bare literal) per the qk-factory rule —
// the factory exists so the key string is spelled once.
const BOOKING_CONFIG_WRITE_KEYS: QueryKey[] = [qk.bookingConfig];

/** Effective merged config (tenant override → platform default → hardcoded
 * fallback). This is what the grid renders off. ``tenantId`` is REQUIRED for
 * platform roles (HQ view passes its picked target) and MUST be omitted by
 * store roles (anti-forgery, enforced server-side). */
export function useBookingConfigEffective(tenantId?: string) {
  return useQuery({
    queryKey: qk.bookingConfigEffective,
    queryFn: () => fetchEffectiveBookingConfig(tenantId),
  });
}

/** Platform-wide default config row, or null when none is seeded yet.
 * super_admin-only endpoint; the Dialog reads this for the「平台默认」column. */
export function usePlatformBookingConfig() {
  return useQuery({
    queryKey: qk.bookingConfig,
    queryFn: fetchPlatformBookingConfig,
  });
}

/** Upsert the platform default row (full-replace of the 3 upsert fields).
 * Invalidates the whole config family so the effective read + any open
 * tenant column refresh. super_admin-only. */
export function useUpdatePlatformBookingConfig() {
  return useApiMutation(
    (payload: BookingConfigUpsert) => updatePlatformBookingConfig(payload),
    BOOKING_CONFIG_WRITE_KEYS,
  );
}

/** One store's override row, or null when that store hasn't customized.
 * Backend enforces own-tenant access for store roles; platform roles may read
 * any tenant via the path id. */
export function useTenantBookingConfig(tenantId: string) {
  return useQuery({
    queryKey: [...qk.bookingConfig, "tenant", tenantId],
    queryFn: () => fetchTenantBookingConfig(tenantId),
    enabled: !!tenantId,
  });
}

/** Upsert one store's override (full-replace). Invalidates the whole config
 * family so effective + any open column refresh. Backend enforces own-tenant
 * write for store roles (settings:update); platform roles may write any tenant. */
export function useUpdateTenantBookingConfig(tenantId: string) {
  return useApiMutation(
    (payload: BookingConfigUpsert) =>
      updateTenantBookingConfig(tenantId, payload),
    BOOKING_CONFIG_WRITE_KEYS,
  );
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

// permission catalogue — the flat list of permission items, optionally
// filtered by type ("api" / "menu"). The API token issue dialog uses the
// "api" filter to render the scope picker (the selectable scopes a restricted
// token can be narrowed to).
export function usePermissionsCatalogue(type?: "api" | "menu") {
  return useQuery({
    queryKey: qk.permissionCatalogue(type),
    queryFn: () => fetchPermissionCatalogue(type),
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
