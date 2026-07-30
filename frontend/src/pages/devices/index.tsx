/**
 * devices/ index — two-way view router (the public page entry).
 *
 * 从原 1083 行 devices-page.tsx 抽出(plan-devices-page-split.md)。镜像
 * ``bookings/index.tsx``(两路版,devices 无 customer view)。Pure locality
 * move: zero behaviour change.
 *
 * Top-level two-way branch:
 *
 *   isSuperAdmin(me) || isHQStaff(me) ? <HqView/>    // cross-tenant panorama
 *   : <StoreView/>                                   // within-tenant CRUD
 *
 * super_admin / hq_staff see the cross-tenant panorama; everyone else (store
 * owner/admin/member) lands on the within-tenant StoreView. The HQ backend
 * guard mirrors this branch (require_cross_tenant_viewer), so both roles get
 * DeviceHqRead[] from the same endpoint.
 */
import { useAuth } from "@/components/auth/auth-context";
import { isHQStaff, isSuperAdmin } from "@/lib/permission";
import { HqView } from "./hq-view";
import { StoreView } from "./store-view";

export function DevicesPage() {
  const { me } = useAuth();
  return isSuperAdmin(me) || isHQStaff(me) ? <HqView /> : <StoreView />;
}
