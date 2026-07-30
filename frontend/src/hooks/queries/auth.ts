/**
 * queries/auth — auth.
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { useApiMutation } from "./core";
import { useMutation } from "@tanstack/react-query";
import {
  changePassword,
  updateMe,
} from "@/api/endpoints";
import type {
  PasswordChange,
  ProfileUpdate,
} from "@/api/types";
// ---------- auth ----------
// NOTE: there is no useLogin/useLogout hook by design. login-page.tsx calls the
// `login()` endpoint directly and hands the token to auth-context.signIn()
// (which already resets the /me query); dashboard-layout.tsx calls `logout()`
// directly before clearing local state. Wrapping them in mutations would just
// duplicate that wiring.

// Self-service profile + password (PUT /auth/me, PUT /auth/me/password).
// The /me query key is owned by auth-context (["auth","me",token]), so
// invalidating ["auth","me"] forces it to refetch the updated identity.
export function useUpdateMe() {
  return useApiMutation(
    (payload: ProfileUpdate) => updateMe(payload),
    [["auth", "me"]],
  );
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: PasswordChange) => changePassword(payload),
  });
}

