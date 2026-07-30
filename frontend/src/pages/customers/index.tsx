/**
 * customers/ index — two-way view router (the public page entry).
 *
 * Extracted from the original customers-page.tsx (plan-customers-page-split.md).
 * Pure locality move: zero behaviour change.
 *
 * Top-level two-way branch:
 *
 *   isSuperAdmin(me) ? <HqView/>     // cross-tenant panorama (read-only)
 *                    : <StoreView/>  // within-tenant CRUD
 *
 * The backend enforces the boundary (HQ endpoints are require_super_admin),
 * so a non-super_admin calling useCustomers would get 403 — we split the query
 * by role to match.
 */
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { HqView } from "./hq-view";
import { StoreView } from "./store-view";

export function CustomersPage() {
  const { me } = useAuth();

  // super_admin sees the HQ aggregate view by default; everyone else sees
  // their own store's profiles.
  return isSuperAdmin(me) ? <HqView /> : <StoreView />;
}
