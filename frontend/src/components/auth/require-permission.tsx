import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./auth-context";
import { canViewMenu, hasPermission } from "@/lib/permission";

/**
 * Route guard for the user-management pages (users / roles / permissions /
 * members / settings).
 *
 * Used as a layout route (`<Route element={<RequireUserManagement />}>`), so it
 * renders an `<Outlet />` for the nested children. `ProtectedRoute` only checks
 * authentication; this wrapper adds the authorization check, so a user who
 * navigates to a management page directly is redirected to the dashboard unless
 * they hold that page's menu permission. The backend still enforces the
 * boundary (403) — this is purely a UX guard.
 *
 * Each route maps to a menu permission code; the guard checks the code for the
 * *current* path so that, e.g., a role with `menu:roles` but not `menu:users`
 * can still reach `/roles`.
 */
const PATH_MENU: Record<string, string> = {
  "/users": "menu:users",
  "/roles": "menu:roles",
  "/permissions": "menu:permissions",
  "/members": "menu:members",
  "/settings": "menu:settings",
};

export function RequireUserManagement() {
  const { me, isLoading } = useAuth();
  const location = useLocation();

  // While /me is loading we can't decide yet — render nothing to avoid a
  // false redirect flash (ProtectedRoute already shows a skeleton for auth
  // loading, so this is a safe empty state during the brief window).
  if (isLoading || !me) return null;

  const menuCode = PATH_MENU[location.pathname];
  // Unknown path under this guard: default to denying (redirect home) rather
  // than silently showing a page the user may not be entitled to.
  if (!menuCode || !canViewMenu(me, menuCode)) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }
  return <Outlet />;
}

/**
 * Paths gated on an api permission code (obj:act) rather than a menu code.
 * Used by features that ship an api permission but no menu permission — e.g.
 * the store-level billing page is gated on `wallet:read` (Token 费用管理系列
 * 4/4). super_admin short-circuits true via `hasPermission`.
 */
const PATH_API_PERM: Record<string, { obj: string; act: string }> = {
  "/billing": { obj: "wallet", act: "read" },
  "/logs": { obj: "logs", act: "read" },
};

/**
 * Layout guard for api-permission-gated routes. Mirrors
 * {@link RequireUserManagement} but checks the api permission code for the
 * current path. The backend still enforces 403 — this is a UX guard.
 */
export function RequireApiPermission() {
  const { me, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading || !me) return null;

  const perm = PATH_API_PERM[location.pathname];
  if (!perm || !hasPermission(me, perm.obj, perm.act)) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }
  return <Outlet />;
}
