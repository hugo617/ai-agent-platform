/**
 * endpoints/branding — tenant branding config (white-label, priority 52).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  TenantConfig,
  TenantConfigUpdate,
} from "../types";
// ---------- tenant branding config (white-label, priority 52) ----------
// Read is open to any authenticated user of the tenant (branding applies to
// everyone); write requires settings:update (owner/admin). The caller's tenant
// is resolved from the token, so there is no tenant_id in the URL.
export async function fetchTenantConfig(): Promise<TenantConfig | null> {
  const { data } = await api.get<TenantConfig | null>("/tenant-config");
  return data;
}

export async function updateTenantConfig(
  payload: TenantConfigUpdate,
): Promise<TenantConfig> {
  const { data } = await api.put<TenantConfig>("/tenant-config", payload);
  return data;
}

