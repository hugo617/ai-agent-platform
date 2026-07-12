import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./auth-context";

/**
 * Route guard for platform-level (super_admin only) pages, e.g. store
 * management (`/tenants`).
 *
 * Mirrors {@link RequireUserManagement} but narrows the check to the platform
 * super_admin role. Tenant owners/admins are redirected to the dashboard
 * instead of seeing a broken "no data" page. The backend still enforces the
 * boundary (403 on `GET /tenants/all` for non-super-admins) — this is purely a
 * UX guard.
 */
export function RequireSuperAdmin() {
  const { me, isLoading } = useAuth();
  const location = useLocation();

  // While /me is loading we can't decide yet — render nothing to avoid a
  // false redirect flash (ProtectedRoute already shows a skeleton for auth
  // loading, so this is a safe empty state during the brief window).
  if (isLoading || !me) return null;

  if (me.platform_role !== "super_admin") {
    return <Navigate to="/" state={{ from: location }} replace />;
  }
  return <Outlet />;
}
