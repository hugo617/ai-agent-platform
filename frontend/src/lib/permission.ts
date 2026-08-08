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

import type { KnowledgeScope, MeResponse } from "@/api/types";

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

/**
 * Is the current user a derived group admin (knowledge-tiered)?
 *
 * knowledge-tiered admin-ui F3 — ``me.is_group_admin`` is the backend-derived
 * flag: true when the user is the owner/admin of a group's headquarters tenant
 * (see ``_build_me_response`` in app/api/v1/auth.py). A group_admin has
 * cross-store management rights *within their own group* only — distribute to
 * branch stores, create scope=group documents/categories, see aggregate views.
 *
 * Distinct from ``isSuperAdmin`` (platform-level everything) and ``isHQStaff``
 * (read-only panorama). Use ``isGroupAdmin(me) || isSuperAdmin(me)`` for the
 * "may distribute / see manage-distribution" gate (F5/F7), since both roles
 * hold ``knowledge:distribute`` but group_admin is scoped to own group.
 *
 * Mirrors ``is_group_admin(db, user_id, group_id)`` on the backend — the MeResponse
 * flag is populated so the frontend never has to re-derive it.
 */
export function isGroupAdmin(me: MeResponse | null | undefined): boolean {
  return !!me?.is_group_admin;
}

/**
 * Which document/category scopes may the current user create? (F3)
 *
 * knowledge-tiered admin-ui F3 — drives the scope dropdown in the admin create-
 * document form and the category-manager. Mirrors the backend
 * ``_resolve_create_target`` / ``_enforce_scope_role`` role→scope mapping so
 * the frontend's offered scopes exactly match what the backend will accept
 * (prevents "UI shows platform but API 400s"):
 *
 *   super_admin  → [platform, group, store]  (may create any tier)
 *   group_admin  → [group, store]            (own group + own store; never platform)
 *   owner/admin  → [store]                   (own store only)
 *   member       → []                         (no create; manage tab hidden anyway)
 *
 * Note: a derived group_admin is NOT a super_admin, so platform is withheld
 * even though they have cross-store rights — pinned by backend test
 * ``test_service_create_platform_category_by_group_admin_rejected``.
 */
export function getAvailableScopes(
  me: MeResponse | null | undefined,
): KnowledgeScope[] {
  if (isSuperAdmin(me)) return ["platform", "group", "store"];
  if (isGroupAdmin(me)) return ["group", "store"];
  if (hasPermission(me, "knowledge", "create")) return ["store"];
  return [];
}
