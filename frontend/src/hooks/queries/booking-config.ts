/**
 * queries/booking-config — booking schedule-grid config (booking-schedule-grid 切片 03).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery, type QueryKey } from "@tanstack/react-query";
import {
  fetchEffectiveBookingConfig,
  fetchPlatformBookingConfig,
  fetchTenantBookingConfig,
  updatePlatformBookingConfig,
  updateTenantBookingConfig,
} from "@/api/endpoints";
import type {
  BookingConfigUpsert,
} from "@/api/types";
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
 * store roles (anti-forgery, enforced server-side).
 *
 * ``enabled: !!tenantId`` mirrors ``useTenantBookingsByDate``: the HQ grid must
 * not fire before a target store is picked. The backend 403s platform writers
 * that hit /effective without ``tenant_id`` (anti-forgery, see
 * app/api/v1/booking_config.py:166-179), so an unguarded hook emits a spurious
 * 403 on first paint when ``targetTenantId`` is still "". Store-path callers
 * always have a resolved tenant id, so this gate never blocks them. */
export function useBookingConfigEffective(tenantId?: string) {
  return useQuery({
    queryKey: qk.bookingConfigEffective,
    queryFn: () => fetchEffectiveBookingConfig(tenantId),
    enabled: !!tenantId,
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

