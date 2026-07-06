import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe } from "@/api/endpoints";
import { getStoredToken, setStoredToken } from "@/api/client";
import type { MeResponse } from "@/api/types";

/**
 * Auth context.
 *
 * Auth strategy (MVP): a Bearer token is stored in localStorage and attached
 * to every API request. The token can be obtained in two ways:
 *   1. (Production) Logto OIDC flow — TODO: integrate @logto/react.
 *   2. (Development) Paste a token in the Login page's "dev mode" field, e.g.
 *      one minted by the backend tests or a Logto-issued access token.
 *
 * The user's identity (``/auth/me``) is only fetched once a token is present.
 */

interface AuthState {
  token: string | null;
  me: MeResponse | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = React.createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [token, setToken] = React.useState<string | null>(getStoredToken());

  // Only fetch /me when a token exists.
  const meQuery = useQuery({
    queryKey: ["auth", "me", token],
    queryFn: fetchMe,
    enabled: !!token,
    retry: false,
  });

  const signIn = React.useCallback(
    (newToken: string) => {
      setStoredToken(newToken);
      setToken(newToken);
      qc.removeQueries({ queryKey: ["auth", "me"] });
    },
    [qc]
  );

  const signOut = React.useCallback(() => {
    setStoredToken(null);
    setToken(null);
    qc.clear();
  }, [qc]);

  const value: AuthState = {
    token,
    me: meQuery.data,
    isLoading: !!token && meQuery.isLoading,
    isAuthenticated: !!token && meQuery.isSuccess,
    signIn,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
