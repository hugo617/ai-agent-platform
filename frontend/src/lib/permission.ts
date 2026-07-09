/**
 * Frontend permission helpers.
 *
 * The backend is the source of truth for authorization (every endpoint is
 * guarded by `require_permission`); these helpers only drive UX — which nav
 * items to show and which routes a user may enter directly. They are derived
 * from `MeResponse` (`platform_role` + tenant-scoped `roles`), mirroring the
 * casbin role codes (`super_admin` / `owner` / `admin` / `member`).
 *
 * Never rely on these alone for security — they're a convenience layer that
 * keeps unauthorized UI out of sight. The API will still return 403 if
 * something slips through.
 */

import type { MeResponse } from "@/api/types";

/** Tenant-scoped role codes that grant user-management access. */
const USER_MANAGER_ROLES = new Set(["owner", "admin"]);

/**
 * Can the current user manage users (list/create/update/delete)?
 *
 * True for platform super admins and for tenant owners/admins. Plain members
 * get the user-management UI hidden and its routes blocked.
 */
export function canManageUsers(me: MeResponse | null | undefined): boolean {
  if (!me) return false;
  if (me.platform_role === "super_admin") return true;
  return me.roles.some((r) => USER_MANAGER_ROLES.has(r));
}
