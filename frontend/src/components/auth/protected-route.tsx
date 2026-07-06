import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth-context";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Wraps protected routes. Redirects to /login if not authenticated, shows a
 * skeleton while /me is loading.
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth();
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
    );
  }

  // If we have a token but /me failed, the token is invalid → bounce to login.
  // We detect this lazily: AuthProvider marks isAuthenticated=false on failure,
  // and pages call useMe() themselves. Here we just render; the page will
  // surface an error and let the user re-sign-in.
  return <>{children}</>;
}
