/**
 * bookings/ MyBookingsView — customer-bound principal's own bookings list.
 *
 * Extracted from the original bookings-page.tsx (plan-bookings-page-split.md).
 * Pure locality move: zero behaviour change. The ``as Booking[]`` cast on the
 * union return of ``useMyBookings()`` is preserved verbatim — see candidate 8
 * in the 2026-07-25 architecture review (out of scope here).
 *
 * A token carrying ``customer_id``. The GET /me/bookings endpoint (slice 04)
 * already filters server-side to the caller's own bookings — no client-side
 * filter needed. Read-only except for the device-poweron (切片 02) self-service
 * 「确认开机」 button (creating a booking is a store-staff responsibility: a
 * customer can't book for itself).
 *
 * A customer never sees a walk-in booking on this surface (those have
 * customer_id null and are excluded by the backend predicate), so every row
 * has a real scheduled window. Device name isn't in BookingRead (it carries
 * only device_id); we don't fetch the devices feed here to keep this view
 * cheap — the device_id prefix is shown as a fallback identifier, matching the
 * store view's soft-delete transient handling.
 */
import { CalendarX } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useMyBookings, useStartBooking } from "@/hooks/queries";
import type { Booking } from "@/api/types";
import { BookingStatusBadge, fmt } from "./shared";

export function MyBookingsView() {
  const { data: bookings, isLoading } = useMyBookings();
  // 切片 02:customer 自助「确认开机」(pending → in_service)。后端按 caller
  // 的 customer_id 做 own 校验(防越权)+ walk-in 拦截(散客预约仅门店可开机),
  // 故前端无需传 customer_id,真调 startBooking(id) 即可。失败 toast 透传后端
  // 信息(非法态 400 / 无权 403)。
  const startMut = useStartBooking();
  const toast = useToast();

  // Note(candidate-8): useMyBookings() return shape — preserved as-is here.
  const list = (bookings ?? []) as Booking[];

  async function confirmStart(b: Booking) {
    try {
      await startMut.mutateAsync(b.id);
      toast.success("已开机");
    } catch (err) {
      toast.error("开机失败", apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="我的预约"
        subtitle="查看您的设备预约记录。如需预约或修改，请联系门店工作人员。"
      />

      <Card>
        <CardHeader>
          <CardTitle>我的预约列表</CardTitle>
          <CardDescription>共 {list.length} 条预约</CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            loadingVariant="skeleton"
            skeletonRows={6}
            emptyContent={
              <EmptyState
                icon={CalendarX}
                title="暂无预约"
                description="您目前没有任何设备预约记录"
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>设备</TableHead>
                  <TableHead>预约时段</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">
                      {/* BookingRead carries only device_id (no device_name —
                          that's a BookingHqRead field). We don't pull the
                          devices feed here (keeps this view cheap + avoids
                          surfacing other tenants' devices for a customer
                          principal); the id prefix is a stable fallback.
                          device_id null is unreachable (a booking always has a
                          device FK) but typed nullable, so guard defensively. */}
                      {b.device_id ? `设备(${b.device_id.slice(0, 8)})` : "—"}
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
                    <TableCell className="text-right">
                      {/* 状态机:pending → in_service 合法跳转。其余态
                          (in_service/done/cancelled/no_show/confirmed)均无按钮。
                          注:``confirmed`` 是前向兼容占位态(device-booking 无
                          /confirm 端点,运行期不可达),按 spec L259 不渲染按钮。 */}
                      {b.status === "pending" && (
                        <Button
                          size="sm"
                          onClick={() => confirmStart(b)}
                          disabled={startMut.isPending}
                        >
                          确认开机
                        </Button>
                      )}
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
