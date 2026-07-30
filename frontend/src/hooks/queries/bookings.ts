/**
 * queries/bookings — bookings (设备预约订单, device-booking 系列 3/4).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery, type QueryKey } from "@tanstack/react-query";
import {
  cancelBooking,
  createBooking,
  endBooking,
  fetchBooking,
  fetchBookings,
  fetchBookingsAll,
  fetchDeviceSchedule,
  fetchMyBookings,
  fetchTenantBookingsByDate,
  noShowBooking,
  startBooking,
  updateBooking,
} from "@/api/endpoints";
import type {
  BookingCreate,
  BookingEndPayload,
  BookingUpdate,
} from "@/api/types";
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

// useBookings / useBookingsAll both feed off GET /bookings/ but declare
// different narrow shapes: store roles get Booking[], HQ roles get
// BookingHqRead[]. The endpoint branches on platform_role server-side; here
// the union is fixed at the hook layer so callers never narrow with ``as``
// (plan-union-cast-split §1/§4.0 D1). queryKey is shared (qk.bookings): a
// session's platform_role is fixed so only one of the two hooks runs for a
// given user — the two caches never coexist (plan §4.0 D5).
export function useBookings() {
  return useQuery({ queryKey: qk.bookings, queryFn: fetchBookings });
}

/** HQ panorama bookings feed — ``BookingHqRead[]`` (store names pre-expanded).
 * Use this in cross-tenant views (super_admin / hq_staff); the store-scoped
 * ``useBookings`` is the within-tenant counterpart. Same queryKey as
 * ``useBookings`` (qk.bookings) — see D5 above. */
export function useBookingsAll() {
  return useQuery({ queryKey: qk.bookings, queryFn: fetchBookingsAll });
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

