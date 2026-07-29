/**
 * bookings/ StoreView — within-tenant booking CRUD surface.
 *
 * Extracted from the original bookings-page.tsx (plan-bookings-page-split.md).
 * Both feeds narrow at the hook layer now (``useBookings()`` returns
 * ``Booking[]`` and ``useDevices()`` returns ``Device[]`` natively,
 * plan-union-cast-split slices 1 + 2), so this component has zero
 * view-boundary casts on its data feeds.
 *
 * StoreView (device-booking slice 06) is the within-tenant CRUD surface — a
 * filterable booking list + per-device 7-day schedule grid, gating create /
 * reschedule / cancel behind ``hasPermission(me, "bookings", act)`` (members
 * only hold ``bookings:read`` so the write actions stay hidden). device-poweron
 * (slice 03) added the DropdownMenu with three lifecycle actions (start /
 * end / no-show) gated on ACTIONABLE_STATUS (pending/confirmed/in_service).
 *
 * platform-cross-tenant-write slice 04 lifted the five Dialog bodies + the
 * row action menu into ``shared-dialog.tsx`` so the HQ view can reuse them.
 * StoreView is now a thin caller: it owns the dialog-open state and the
 * mutation hooks, and passes ``tenantId={undefined}`` (the store path — the
 * backend uses ``user.tenant_id``, behaviour unchanged from before slice 04).
 *
 * Backend guard notes (see plan-device-booking.md):
 * - State-guard rule: the create/update payloads carry NO ``status`` /
 *   ``started_at`` / ``ended_at`` / ``feedback`` — the types make them
 *   unexpressible (BookingCreate / BookingUpdate omit them). Only ``pending``
 *   bookings are mutable; cancelled/done/etc. hide the reschedule/cancel
 *   actions.
 * - Time overlap (a 400 BizError, NOT 409 — D1) is surfaced via the generic
 *   ``apiErrorMessage(err)`` toast; the backend's conflict message is
 *   human-readable ("设备时段冲突:该设备在 ... 已有预约 {id}").
 * - Device identity is immutable on update (D10) — the edit dialog renders
 *   the device read-only / greyed; change-device = cancel + recreate.
 * - Cancel is POST /bookings/{id}/cancel (NOT DELETE — D8: bookings are
 *   cancelled, not deleted; the row stays as the audit trail).
 */
import { useMemo, useState } from "react";

import { CalendarX, Plus } from "lucide-react";

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
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission } from "@/lib/permission";
import type { Booking, BookingCreate, BookingEndPayload, BookingUpdate } from "@/api/types";
import {
  useBookings,
  useCancelBooking,
  useCreateBooking,
  useCustomerProfiles,
  useDevices,
  useEndBooking,
  useNoShowBooking,
  useStartBooking,
  useUpdateBooking,
} from "@/hooks/queries";
import {
  BookingCancelDialog,
  BookingCreateDialog,
  BookingEditDialog,
  BookingEndDialog,
  BookingNoShowDialog,
  BookingRowMenu,
} from "./shared-dialog";
// Deep imports per plan-shared-tsx-split 切片 2 (D4: no barrel). The shared
// badges (BookingStatusBadge) + deviceNameOf stay in ./shared (D2/D7); the
// filter logic + schedule grid card live in their own modules; fmt is sourced
// directly from @/lib/format (D5 — eliminate the convenience re-export).
import { BookingStatusBadge, deviceNameOf } from "./shared";
import {
  FilterChips,
  applyBookingFilter,
  type BookingFilter,
} from "./filter";
import { ScheduleGridCard } from "./schedule-grid-card";
import { formatDateTime as fmt } from "@/lib/format";

// Exported for component tests (vitest, slice 03 store-view.test.tsx). Not
// consumed anywhere else — the top-level ``BookingsPage`` is the public entry.
export function StoreView() {
  const toast = useToast();
  const { me } = useAuth();

  const { data: bookings, isLoading } = useBookings();
  const { data: devices } = useDevices();
  // Customer profiles feed the create/edit dialog's customer Select. Only
  // fetched here (the store view); HqView is read-only + reads
  // HQ-pre-expanded names, so it won't need this feed.
  const { data: profiles } = useCustomerProfiles();

  // Store path: no tenantId → backend uses user.tenant_id (zero behaviour
  // change from before slice 04). The hooks are constructed once and reused
  // across all five dialogs.
  const createMut = useCreateBooking();
  const updateMut = useUpdateBooking();
  const cancelMut = useCancelBooking();
  const startMut = useStartBooking();
  const endMut = useEndBooking();
  const noShowMut = useNoShowBooking();

  // ---------- filter chips ----------
  // Mutually-exclusive list filter. Five presets, plus "all". Matches the
  // hand-rolled button-row convention used by dashboard/billing trend toggles
  // (no shadcn Tabs primitive in this project — see dashboard-page.tsx:244).
  const [filter, setFilter] = useState<BookingFilter>("all");

  // ---------- schedule grid ----------
  // The device whose 7-day grid is expanded below the list. ``null`` = the grid
  // card is collapsed (shows the device picker only). Picking a device opens
  // the grid via useDeviceSchedule(id, today, today+7d).
  const [gridDeviceId, setGridDeviceId] = useState<string>("");

  // ---------- dialog state ----------
  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);
  // Edit (reschedule) dialog
  const [editTarget, setEditTarget] = useState<Booking | null>(null);
  // Cancel confirm dialog
  const [cancelTarget, setCancelTarget] = useState<Booking | null>(null);
  // device-poweron (切片 03):end-service + no-show confirm dialogs. Both are
  // single-target confirms; the end dialog carries an optional free-text
  // feedback payload (owned inside BookingEndDialog now).
  const [endTarget, setEndTarget] = useState<Booking | null>(null);
  const [noShowTarget, setNoShowTarget] = useState<Booking | null>(null);

  // device_id → serial_number, for resolving the list's "设备名" column from
  // the booking's device_id (BookingRead carries only device_id, no name —
  // devices have no ``name`` column; serial_number IS their identifier, per
  // BookingService._to_hq_read docstring). Also feeds the edit dialog's
  // read-only device field.
  //
  // useDevices() now returns Device[] natively (the union is fixed at the hook
  // layer, plan-union-cast-split slice 2), so the loop takes a typed array — no
  // ``as Device[]`` cast.
  const deviceMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of devices ?? []) {
      m.set(d.id, d.serial_number);
    }
    return m;
  }, [devices]);

  // customer_id → display name, for the "客户名" column. Walk-in bookings
  // (customer_id null) render as "散客(walk-in)".
  const customerMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of profiles ?? []) m.set(p.customer_id, p.customer.name);
    return m;
  }, [profiles]);

  // Button-level guards. super_admin bypasses (hasPermission returns true);
  // members only hold bookings:read so the write actions stay hidden.
  const canCreate = hasPermission(me, "bookings", "create");
  const canUpdate = hasPermission(me, "bookings", "update");
  const canCancel = hasPermission(me, "bookings", "delete"); // cancel uses :delete

  // Apply the active filter chip. Time filters key off scheduled_start_at (the
  // appointment time, not created_at). "本周" = the ISO calendar week
  // containing today (Mon→Sun), matching the dashboard trend windows' "last 7
  // days from now" intuition loosely — kept as calendar-week here because a
  // store's booking sheet is read by week.
  //
  // useBookings() now returns Booking[] natively (the union is fixed at the
  // hook layer, plan-union-cast-split slice 1), so no narrowing cast is needed
  // here. ``bookings`` (the react-query result, stable until data changes) is
  // the sole data dep — a derived ``list = bookings ?? []`` would re-allocate
  // the empty array every render and trip react-hooks/exhaustive-deps.
  const filtered = useMemo(
    () => applyBookingFilter(bookings ?? [], filter),
    [bookings, filter],
  );

  // ---------- row action handlers ----------
  // Each handler runs the mutation + surfaces the success/error toast +
  // closes the Dialog on success. The shared Dialog bodies own their form
  // state + local validation; they call onSubmit and let the promise
  // reject propagate (we catch here so a 400 keeps the Dialog open for the
  // operator to fix + retry).
  const handleStart = async (b: Booking) => {
    try {
      await startMut.mutateAsync(b.id);
      toast.success("已开机");
    } catch (err) {
      toast.error("开机失败", apiErrorMessage(err));
    }
  };
  const handleEnd = async (id: string, payload?: BookingEndPayload) => {
    try {
      await endMut.mutateAsync({ id, payload });
      toast.success("已结束服务");
      setEndTarget(null);
    } catch (err) {
      toast.error("结束失败", apiErrorMessage(err));
    }
  };
  const handleNoShow = async (id: string) => {
    try {
      await noShowMut.mutateAsync(id);
      toast.success("已标记爽约");
      setNoShowTarget(null);
    } catch (err) {
      toast.error("标记爽约失败", apiErrorMessage(err));
    }
  };
  const handleCancel = async (id: string) => {
    try {
      await cancelMut.mutateAsync(id);
      toast.success("已取消预约");
      setCancelTarget(null);
    } catch (err) {
      toast.error("取消失败", apiErrorMessage(err));
    }
  };
  const handleCreate = async (payload: BookingCreate) => {
    try {
      await createMut.mutateAsync(payload);
      toast.success("预约已创建");
      setCreateOpen(false);
    } catch (err) {
      // 400 here covers: window invalid (end <= start), device/customer not
      // in tenant, AND time overlap. The backend message is human-readable,
      // so we surface it verbatim (no client-side overlap pre-check).
      // We do NOT close the dialog on failure — the operator can adjust + retry.
      toast.error("创建失败", apiErrorMessage(err));
    }
  };
  const handleEdit = async (id: string, payload: BookingUpdate) => {
    try {
      await updateMut.mutateAsync({ id, payload });
      toast.success("已改约");
      setEditTarget(null);
    } catch (err) {
      toast.error("改约失败", apiErrorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="预约"
        subtitle="管理本店设备预约：创建、改约、取消，查看今日/明日/本周预约与设备排期。"
        actions={
          canCreate && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> 创建预约
            </Button>
          )
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>预约列表</CardTitle>
          <CardDescription>
            共 {filtered.length} 条{filter !== "all" ? "(已筛选)" : ""}
            {!canCreate && "（只读视图）"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filter chip row. Mutually-exclusive; "全部" resets. */}
          <FilterChips value={filter} onChange={setFilter} />

          <ListState
            isLoading={isLoading}
            isEmpty={filtered.length === 0}
            loadingVariant="skeleton"
            skeletonRows={6}
            emptyContent={
              <EmptyState
                icon={CalendarX}
                title="暂无预约"
                description={
                  canCreate
                    ? filter === "all"
                      ? "点击右上角「创建预约」"
                      : "该筛选条件下暂无预约"
                    : "本店暂无预约"
                }
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>设备</TableHead>
                  <TableHead>客户</TableHead>
                  <TableHead>预约时段</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                  {(canUpdate || canCancel) && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">
                      {deviceNameOf(b.device_id, deviceMap)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {b.customer_id
                        ? (customerMap.get(b.customer_id) ?? "—")
                        : "散客(walk-in)"}
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
                    {(canUpdate || canCancel) && (
                      <TableCell className="text-right">
                        <BookingRowMenu
                          booking={b}
                          canUpdate={canUpdate}
                          canCancel={canCancel}
                          onEdit={setEditTarget}
                          onCancel={setCancelTarget}
                          onStart={handleStart}
                          onEnd={setEndTarget}
                          onNoShow={setNoShowTarget}
                        />
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      {/* ---------------- schedule grid card ---------------- */}
      <ScheduleGridCard
        devices={devices ?? []}
        selectedId={gridDeviceId}
        onSelect={setGridDeviceId}
      />

      {/* ---------------- shared Dialogs (platform-cross-tenant-write 切片 04 抽出) ---------------- */}
      {/* Store path: tenantId undefined → backend uses user.tenant_id; profiles
          feed the customer dropdown. */}
      <BookingCreateDialog
        open={createOpen}
        devices={devices ?? []}
        profiles={profiles ?? []}
        tenantId={undefined}
        isPending={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />
      <BookingEditDialog
        target={editTarget}
        deviceName={
          editTarget
            ? deviceNameOf(editTarget.device_id, deviceMap)
            : ""
        }
        profiles={profiles ?? []}
        tenantId={undefined}
        isPending={updateMut.isPending}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEdit}
      />
      <BookingCancelDialog
        target={cancelTarget}
        isPending={cancelMut.isPending}
        onClose={() => setCancelTarget(null)}
        onSubmit={handleCancel}
      />
      <BookingEndDialog
        target={endTarget}
        isPending={endMut.isPending}
        onClose={() => setEndTarget(null)}
        onSubmit={handleEnd}
      />
      <BookingNoShowDialog
        target={noShowTarget}
        isPending={noShowMut.isPending}
        onClose={() => setNoShowTarget(null)}
        onSubmit={handleNoShow}
      />
    </div>
  );
}
