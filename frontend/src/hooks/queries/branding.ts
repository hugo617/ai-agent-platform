/**
 * queries/branding — tenant branding config (white-label, priority 52).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  fetchTenantConfig,
  updateTenantConfig,
} from "@/api/endpoints";
import type {
  TenantConfigUpdate,
} from "@/api/types";
import { useEffect } from "react";
import { applyThemeColor } from "@/lib/theme";
import { useTheme } from "@/components/theme/theme-provider";
// ---------- tenant branding config (white-label, priority 52) ----------
// Read is open to any authenticated user of the tenant (the theme color / logo /
// display name apply globally to everyone), so this hook has no `enabled` gate.
// Write (update) requires settings:update, checked by the caller before showing
// the card.
export function useTenantConfig() {
  return useQuery({
    queryKey: qk.tenantConfig,
    queryFn: fetchTenantConfig,
  });
}

export function useUpdateTenantConfig() {
  return useApiMutation(
    (payload: TenantConfigUpdate) => updateTenantConfig(payload),
    [qk.tenantConfig],
  );
}

/**
 * Apply the tenant theme color globally as the ``--primary`` CSS token.
 *
 * Reads the current tenant's branding config (open to any authenticated user),
 * converts ``#RRGGBB`` to the HSL token shadcn expects, and writes it onto
 * ``:root``. The cleanup restores the platform default on unmount / tenant
 * switch / logout so a stale brand never bleeds across tenants. No-op while the
 * config is still loading or when no color is set (defaults preserved).
 *
 * Theme-aware re-application (P0-2): when the user flips light/dark, the
 * ``--primary`` foreground contrast must be re-derived against the active mode
 * (the revert path restores mode-specific platform defaults). So this hook also
 * re-runs ``applyThemeColor`` whenever ``resolvedTheme`` changes.
 */
export function useApplyTenantTheme() {
  const { data } = useTenantConfig();
  const { resolvedTheme } = useTheme();
  useEffect(() => {
    applyThemeColor(data?.theme_color ?? null);
    return () => {
      // Restore platform defaults when the branded surface unmounts (logout,
      // tenant switch) so a stale brand never bleeds across tenants.
      applyThemeColor(null);
    };
  }, [data?.theme_color, resolvedTheme]);
}

