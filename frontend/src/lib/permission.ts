/**
 * Frontend permission helpers.
 *
 * The backend is the source of truth for authorization (every endpoint is
 * guarded by `require_permission`); these helpers only drive UX — which nav
 * items to show, which routes a user may enter, and which action buttons are
 * enabled. They are derived from `MeResponse` (`platform_role` +
 * `tenant-scoped roles` + `permissions`), where `permissions` is the aggregated
 * list of currently-effective codes (both `api` units like `customers:read` and
 * `menu` UX codes like `menu:agents`).
 *
 * Never rely on these alone for security — they're a convenience layer that
 * keeps unauthorized UI out of sight. The API will still return 403 if
 * something slips through.
 */

import type { MeResponse } from "@/api/types";

/**
 * Is the current user a platform super admin?
 *
 * A thin helper so call sites read ``isSuperAdmin(me)`` instead of the raw
 * ``me?.platform_role === "super_admin"`` string compare repeated across 9+
 * pages. The backend treats super_admin as a short-circuit for every
 * permission check, so this is the platform-level "everything" gate.
 */
export function isSuperAdmin(me: MeResponse | null | undefined): boolean {
  return me?.platform_role === "super_admin";
}

/**
 * Is the current user HQ staff (cross-tenant read-only viewer)?
 *
 * Mirrors ``isSuperAdmin``: hq_staff is the dedicated HQ-panorama role — it
 * has no tenant role, so ``require_permission("devices","read")`` would 403 it
 * before the panorama branch in the service runs. The bypass lives in
 * ``permission_service.check`` (hq_staff + read short-circuit). Call sites that
 * branch the UI between store view and HQ panorama should test
 * ``isSuperAdmin(me) || isHQStaff(me)`` — super_admin falls in the same
 * cross-tenant-viewer bucket (see ``is_cross_tenant_viewer`` on the backend).
 */
export function isHQStaff(me: MeResponse | null | undefined): boolean {
  return me?.platform_role === "hq_staff";
}

/**
 * Does the current user carry a customer identity?
 *
 * Customer-bound tokens expose ``me.customer_id`` (slice 07); store-staff
 * tokens leave it null. The /bookings page uses this to route a customer
 * principal to the read-only "my bookings" view (creating bookings is a store-
 * staff responsibility). Mirrors ``isHQStaff``'s shape so the top-level three-
 * way fork reads symmetrically:
 *
 *   isSuperAdmin(me) || isHQStaff(me) ? <HqView/>
 *   : hasCustomerIdentity(me)         ? <MyBookingsView/>
 *   : <StoreView/>
 *
 * HQ / super_admin viewers take precedence — a customer binding is irrelevant
 * to a cross-tenant panorama viewer (and an HQ role wouldn't carry one anyway).
 */
export function hasCustomerIdentity(me: MeResponse | null | undefined): boolean {
  return !!me?.customer_id;
}

/**
 * Does the current user hold the `<obj>:<act>` permission?
 *
 * super_admin short-circuits to true (bypasses all checks; the backend returns
 * an empty permissions list for it precisely because every check passes).
 * Otherwise this is a membership test against `me.permissions`.
 */
export function hasPermission(
  me: MeResponse | null | undefined,
  obj: string,
  act: string,
): boolean {
  if (!me) return false;
  if (me.platform_role === "super_admin") return true;
  return me.permissions.includes(`${obj}:${act}`);
}

/**
 * May the current user see the nav item / enter the route for a menu?
 *
 * `menuCode` is the full code (e.g. `"menu:agents"`). super_admin short-
 * circuits to true. `menu:tenants` is platform-level and intentionally has no
 * permission row — callers gate it separately on `platform_role ===
 * "super_admin"` (see NAV_ITEMS handling in dashboard-layout).
 */
export function canViewMenu(
  me: MeResponse | null | undefined,
  menuCode: string,
): boolean {
  if (!me) return false;
  if (me.platform_role === "super_admin") return true;
  return me.permissions.includes(menuCode);
}
