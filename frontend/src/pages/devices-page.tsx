/**
 * Devices page — slice 05 stub (devices-crud-ui 系列 2/4).
 *
 * This is the route target for ``/devices`` so the route is reachable and the
 * nav item lands somewhere. The real UI lands in slice 06 (StoreView: tenant
 * device CRUD + bind customer) and slice 07 (HqView: cross-tenant panorama
 * for super_admin / hq_staff), which will replace this stub with the
 * ``isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : <StoreView/>`` branch
 * mirroring ``customers-page.tsx``.
 *
 * The data hooks (``useDevices`` / ``useDeviceModels`` / bind-unbind family)
 * and types are already wired in slice 05 — slice 06 just consumes them here.
 */
import { Monitor } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function DevicesPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Monitor className="h-5 w-5 text-muted-foreground" />
            <CardTitle>设备管理</CardTitle>
          </div>
          <CardDescription>
            门店设备实例的入库、状态切换、绑定客户与软删。
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          页面建设中(切片 06/07 将上线列表与操作)。
        </CardContent>
      </Card>
    </div>
  );
}
