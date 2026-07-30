/**
 * endpoints/bookings — bookings (设备预约订单, device-booking 系列 3/4).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Booking,
  BookingCreate,
  BookingEndPayload,
  BookingHqRead,
  BookingUpdate,
  DeviceSchedule,
} from "../types";
// ---------- bookings (设备预约订单, device-booking 系列 3/4) ----------
//
// Reads branch on the caller's platform role on the backend, mirroring
// devices:
// - tenant roles (owner/admin/member) → Booking[] scoped to this tenant
// - super_admin / hq_staff            → BookingHqRead[] cross-tenant panorama
// The two role-specific shapes are surfaced as ``fetchBookings`` (store) +
// ``fetchBookingsAll`` (HQ) below, each declaring the narrow return type at
// this seam rather than a union the caller must narrow with ``as`` at the
// view boundary (plan-union-cast-split §1/§4.0 D1). Writes (create/update/
// cancel) are tenant-scoped and return Booking.
//
// Cancel is POST /bookings/{id}/cancel (NOT DELETE — D8: bookings are
// cancelled, not deleted; the row stays as the audit trail). Returns 204 and
// is idempotent (re-cancelling an already-cancelled booking is a no-op that
// still returns 204), so the client needs no response body.
//
// The schedule + my-bookings reads live on different routers but both serve
// bookings data: GET /devices/{id}/schedule (device sub-resource URL, day-
// grouped grid — ``{ "2030-01-01": [booking, ...] }``, only days with ≥1
// booking; ``start`` / ``end`` are ISO datetimes, both optional, backend
// defaults to today ±7 days; a foreign / missing device → 404) and
// GET /me/bookings (customer-principal own view — ``customer_id`` is read off
// the resolved principal, never from request input, so store-staff principals
// get 403; returns plain Booking[], no HQ panorama fields).
// GET /bookings/ branches on platform_role (store roles get Booking[],
// HQ roles get BookingHqRead[]). Rather than return a union and force callers
// to narrow with ``as`` at every view boundary, we expose two role-specific
// fetch functions that each declare the narrow shape for their audience. Both
// hit the same URL; the type is fixed at this seam, with zero runtime
// difference (a session's platform_role is fixed, so only one of the two is
// ever called for a given user — the two caches never collide on the shared
// ``qk.bookings`` key). See plan-union-cast-split §1/§4.0 D1.
export async function fetchBookings(): Promise<Booking[]> {
  const { data } = await api.get<Booking[]>("/bookings/");
  return data;
}

/** HQ panorama variant of ``fetchBookings`` — returns ``BookingHqRead[]``
 * (``Booking`` + tenant_name / device_name / customer_name) for the super_admin
 * / hq_staff cross-tenant view. Same endpoint as ``fetchBookings``; the backend
 * returns the panorama shape for HQ roles. */
export async function fetchBookingsAll(): Promise<BookingHqRead[]> {
  const { data } = await api.get<BookingHqRead[]>("/bookings/");
  return data;
}

export async function fetchBooking(
  id: string,
): Promise<Booking | BookingHqRead> {
  const { data } = await api.get<Booking | BookingHqRead>(`/bookings/${id}`);
  return data;
}

export async function createBooking(payload: BookingCreate): Promise<Booking> {
  const { data } = await api.post<Booking>("/bookings/", payload);
  return data;
}

export async function updateBooking(
  id: string,
  payload: BookingUpdate,
): Promise<Booking> {
  const { data } = await api.put<Booking>(`/bookings/${id}`, payload);
  return data;
}

// POST /bookings/{id}/cancel — body-less (idempotent 204). The cross-store
// target rides a ``tenant_id`` query param for platform writers
// (platform-cross-tenant-write plan §4.5.4a 补丁 5); store principals omit it.
export async function cancelBooking(
  id: string,
  tenantId?: string,
): Promise<void> {
  await api.post(`/bookings/${id}/cancel`, undefined, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
}

// POST /bookings/{id}/start (device-poweron 切片 02) — pending → in_service,
// backend fills ``started_at``. Body-less POST (pure status flip).
// ``tenantId`` query param = platform-writer cross-store target (plan §4.5.4a
// 补丁 5).
export async function startBooking(
  id: string,
  tenantId?: string,
): Promise<Booking> {
  const { data } = await api.post<Booking>(`/bookings/${id}/start`, undefined, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
  return data;
}

// POST /bookings/{id}/end (device-poweron 切片 03) — in_service → done, backend
// fills ``ended_at`` + persists optional ``feedback``. Body is optional; omit it
// to end the booking with no service note. Returns the updated booking so the
// store list reflects the new status + ended_at immediately.
//
// Authorization is store owner only (``bookings:delete``) — admin has no such
// perm (per B2), so the「结束」button is hidden for admin client-side.
// ``tenantId`` query param = platform-writer cross-store target (plan §4.5.4a
// 补丁 5); orthogonal to the body's feedback dict.
export async function endBooking(
  id: string,
  payload?: BookingEndPayload,
  tenantId?: string,
): Promise<Booking> {
  const { data } = await api.post<Booking>(`/bookings/${id}/end`, payload, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
  return data;
}

// POST /bookings/{id}/no-show (device-poweron 切片 03) — pending / confirmed /
// in_service → no_show. Pure status flip (no timestamp); returns 204 like
// ``/cancel`` so there's no body to consume. Authorization: store owner only.
// ``tenantId`` query param = platform-writer cross-store target (plan §4.5.4a
// 补丁 5).
export async function noShowBooking(
  id: string,
  tenantId?: string,
): Promise<void> {
  await api.post(`/bookings/${id}/no-show`, undefined, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
}

export async function fetchDeviceSchedule(
  deviceId: string,
  start?: string,
  end?: string,
): Promise<DeviceSchedule> {
  const { data } = await api.get<DeviceSchedule>(
    `/devices/${deviceId}/schedule`,
    { params: { start, end } },
  );
  return data;
}

export async function fetchMyBookings(): Promise<Booking[]> {
  const { data } = await api.get<Booking[]>("/me/bookings");
  return data;
}

/** GET /bookings/schedule-grid?date=&tenant_id= — one store's bookings for a
 * single calendar day, as ``BookingHqRead[]`` (booking-schedule-grid 切片 02).
 *
 * Anti-forgery contract mirrors the config ``effective`` read: ``tenantId`` is
 * REQUIRED for platform roles (HQ view passes its picked target) and MUST be
 * omitted by store roles (the backend resolves their own tenant from the
 * token; carrying it is a forgery attempt → 403). ``dateISO`` is a
 * "YYYY-MM-DD" string; the backend validates it (FastAPI native ``date`` Query
 * → 422 on malformed). */
export async function fetchTenantBookingsByDate(
  dateISO: string,
  tenantId?: string,
): Promise<BookingHqRead[]> {
  const { data } = await api.get<BookingHqRead[]>("/bookings/schedule-grid", {
    params: { date: dateISO, ...(tenantId ? { tenant_id: tenantId } : {}) },
  });
  return data;
}

