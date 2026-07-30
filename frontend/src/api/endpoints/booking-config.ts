/**
 * endpoints/booking-config — booking schedule-grid config (booking-schedule-grid 切片 01).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  BookingConfig,
  BookingConfigEffective,
  BookingConfigUpsert,
} from "../types";
// ---------- booking schedule-grid config (booking-schedule-grid 切片 01) ----------
//
// Two-level configuration for the schedule grid, mirroring the backend
// /bookings/config router (app/api/v1/booking_config.py):
// - GET  /bookings/config/platform         — super_admin read of the platform
//                                            default row (null body when none)
// - PUT  /bookings/config/platform         — super_admin upsert of that row
// - GET  /bookings/config/tenant/{id}      — settings:read view of one store's
//                                            override (own-tenant enforced
//                                            server-side; null body when none)
// - PUT  /bookings/config/tenant/{id}      — settings:update upsert of that
//                                            override
// - GET  /bookings/config/effective        — merged view the grid renders off
//                                            (tenant → platform → hardcoded
//                                            fallback); ``tenant_id`` query is
//                                            REQUIRED for platform roles and
//                                            FORBIDDEN for store roles (anti-
//                                            forgery, enforced server-side)
//
// GET platform / tenant return ``BookingConfig | null`` (200 + null body when
// the row doesn't exist — NOT 404). PUT is a full replace of the three upsert
// fields (the backend upserts: create-if-absent). ``window_*`` are "HH:MM"
// strings so they pass straight through ``<input type="time">`` values.

/** GET /bookings/config/platform — the platform-wide default row, or null
 * when none is seeded yet. super_admin only (route-level guard). */
export async function fetchPlatformBookingConfig(): Promise<BookingConfig | null> {
  const { data } = await api.get<BookingConfig | null>(
    "/bookings/config/platform",
  );
  return data;
}

/** PUT /bookings/config/platform — full-replace upsert of the platform default
 * row. Returns the persisted row (always non-null: upsert creates if absent).
 * super_admin only. */
export async function updatePlatformBookingConfig(
  payload: BookingConfigUpsert,
): Promise<BookingConfig> {
  const { data } = await api.put<BookingConfig>(
    "/bookings/config/platform",
    payload,
  );
  return data;
}

/** GET /bookings/config/tenant/{id} — one store's override row, or null when
 * that store hasn't customized (the grid would then fall back to platform).
 * Backend enforces own-tenant access for store roles; platform roles may read
 * any tenant. */
export async function fetchTenantBookingConfig(
  tenantId: string,
): Promise<BookingConfig | null> {
  const { data } = await api.get<BookingConfig | null>(
    `/bookings/config/tenant/${tenantId}`,
  );
  return data;
}

/** PUT /bookings/config/tenant/{id} — full-replace upsert of one store's
 * override. Backend enforces own-tenant write for store roles
 * (settings:update perm); platform roles may write any tenant. */
export async function updateTenantBookingConfig(
  tenantId: string,
  payload: BookingConfigUpsert,
): Promise<BookingConfig> {
  const { data } = await api.put<BookingConfig>(
    `/bookings/config/tenant/${tenantId}`,
    payload,
  );
  return data;
}

/** GET /bookings/config/effective — the merged config the grid renders off.
 * Anti-forgery contract: ``tenantId`` is REQUIRED for platform roles (they
 * must name the store they're viewing) and MUST be omitted by store roles
 * (the backend resolves their own tenant from the token). Callers therefore
 * pass ``undefined`` on the store path and the resolved target id on the HQ
 * path — the backend 403s on a mismatch. */
export async function fetchEffectiveBookingConfig(
  tenantId?: string,
): Promise<BookingConfigEffective> {
  const { data } = await api.get<BookingConfigEffective>(
    "/bookings/config/effective",
    { params: tenantId ? { tenant_id: tenantId } : undefined },
  );
  return data;
}

