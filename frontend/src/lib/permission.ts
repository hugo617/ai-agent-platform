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

/** Tenant-scoped role codes that grant user-management access. */
const USER_MANAGER_ROLES = new Set(["owner", "admin"]);

/**
 * @deprecated Use `hasPermission(me, obj, act)` instead. This helper hardcodes
 *   the {owner, admin} role set and cannot express finer-grained checks. It is
 *   retained while call sites migrate to permission-code-based guards.
 *
 * True for platform super admins and for tenant owners/admins. Plain members
 * get the user-management UI hidden and its routes blocked.
 */
export function canManageUsers(me: MeResponse | null | undefined): boolean {
  if (!me) return false;
  if (me.platform_role === "super_admin") return true;
  return me.roles.some((r) => USER_MANAGER_ROLES.has(r));
}
