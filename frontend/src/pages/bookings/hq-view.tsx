/**
 * bookings/ HqView — cross-tenant read-only panorama (super_admin / hq_staff).
 *
 * Extracted from the original bookings-page.tsx (plan-bookings-page-split.md).
 * Pure locality move: zero behaviour change. The ``as BookingHqRead[]`` cast
 * on the union return of ``useBookings()`` is preserved verbatim — narrowing
 * it (splitting into ``useBookingsHq``) is candidate 8 in the 2026-07-25
 * architecture review, intentionally out of scope here.
 *
 * The HQ endpoint (GET /bookings/ behind require_cross_tenant_viewer) already
 * expands tenant_name/device_name/customer_name server-side (BookingHqRead),
 * so this table needs no client-side lookups into the devices/profiles feeds —
 * it just renders the rows it gets back. There are no write controls: HQ
 * viewers observe bookings across stores, never mutate them. Mirrors
 * devices-page's HqView (the cross-tenant read-only fleet view) — same
 * skeleton, data source swapped (useDevices→useBookings) + field mapping
 * (serial_number→device_name, model_name→customer_name, status
 * Badge→scheduled window).
 */
import { CalendarX } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ListState } from "@/components/ui/list-state";
import { PageHeader } from "@/components/layout/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useBookings } from "@/hooks/queries";
import type { BookingHqRead } from "@/api/types";
import { BookingStatusBadge, fmt } from "./shared";

export function HqView() {
  const { data: bookings, isLoading } = useBookings();
  // useBookings() returns a union (Booking[] | BookingHqRead[]). The backend
  // guarantees BookingHqRead[] for HQ roles (the same guard that routes us
  // here), so we narrow once at the view boundary. A store viewer never reaches
  // this component — the top-level BookingsPage branch sees to that.
  //
  // Note(candidate-8): split fetchBookings → fetchBookingsHq to drop this cast.
  const list = (bookings ?? []) as BookingHqRead[];

  return (
    <div className="space-y-6">
      <PageHeader
        title="预约（总部视图）"
        subtitle="跨店聚合：查看所有门店的设备预约。此视图为只读，写操作请切换到门店视角。"
      />

      <Card>
        <CardHeader>
          <CardTitle>全局预约列表</CardTitle>
          <CardDescription>
            共 {list.length} 条预约（跨全部门店）
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            loadingVariant="skeleton"
            skeletonRows={8}
            emptyContent={
              <EmptyState
                icon={CalendarX}
                title="暂无预约"
                description="跨全部门店暂无设备预约"
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>所属门店</TableHead>
                  <TableHead>设备</TableHead>
                  <TableHead>客户</TableHead>
                  <TableHead>预约时段</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="text-muted-foreground">
                      {/* tenant_name is null only if the tenant row was hard-
                          deleted — the FK is CASCADE so this is effectively
                          unreachable, but we guard for display safety. */}
                      {b.tenant_name ?? "（门店已删除）"}
                    </TableCell>
                    <TableCell className="font-medium">
                      {/* device_name is sourced from Device.serial_number on
                          the backend (devices have no ``name`` column).
                          device_id null is unreachable (a booking always has a
                          device FK) but typed nullable, so guard defensively. */}
                      {b.device_name ??
                        (b.device_id
                          ? `设备(${b.device_id.slice(0, 8)})`
                          : "—")}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {/* Walk-in bookings (customer_id null) arrive with
                          customer_name null — render as "散客" to match the
                          store view's convention. */}
                      {b.customer_name ?? "散客(walk-in)"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(b.scheduled_start_at)} → {fmt(b.scheduled_end_at)}
                    </TableCell>
                    <TableCell>
                      <BookingStatusBadge status={b.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(b.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>
    </div>
  );
}
