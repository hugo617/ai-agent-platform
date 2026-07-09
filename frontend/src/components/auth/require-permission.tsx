import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./auth-context";
import { canManageUsers } from "@/lib/permission";

/**
 * Route guard for user-management pages (users / roles / permissions).
 *
 * Used as a layout route (`<Route element={<RequireUserManagement />}>`), so it
 * renders an `<Outlet />` for the nested children. `ProtectedRoute` only checks
 * authentication; this wrapper adds the authorization check, so a plain member
 * who navigates to `/users` directly is redirected to the dashboard instead of
 * seeing a broken "no data" page. The backend still enforces the boundary
 * (403) — this is purely a UX guard.
 */
export function RequireUserManagement() {
  const { me, isLoading } = useAuth();
  const location = useLocation();

  // While /me is loading we can't decide yet — render nothing to avoid a
  // false redirect flash (ProtectedRoute already shows a skeleton for auth
  // loading, so this is a safe empty state during the brief window).
  if (isLoading || !me) return null;

  if (!canManageUsers(me)) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }
  return <Outlet />;
}
