import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./auth-context";
import { canViewMenu } from "@/lib/permission";

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
