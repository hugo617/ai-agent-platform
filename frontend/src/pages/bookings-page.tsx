/**
 * Bookings page — device-booking 系列 3/4(切片 06 StoreView + 切片 07 HqView /
 * MyBookingsView + 三叉路由,末切片)。
 *
 * Top-level three-way branch (slice 07):
 *
 *   isSuperAdmin(me) || isHQStaff(me) ? <HqView/>            // cross-tenant panorama
 *   : hasCustomerIdentity(me)         ? <MyBookingsView/>    // customer "my bookings"
 *   : <StoreView/>                                           // within-tenant CRUD
 *
 * HQ viewers take precedence over a customer binding (an HQ role wouldn't carry
 * one anyway). StoreView (slice 06) is the within-tenant CRUD surface — a
 * filterable booking list + per-device 7-day schedule grid, gating create /
 * reschedule / cancel behind ``hasPermission(me, "bookings", act)`` (members
 * only hold ``bookings:read`` so the write actions stay hidden). HqView is the
 * cross-tenant read-only panorama (no write controls). MyBookingsView is the
 * customer's read-only list (creating bookings is a store-staff responsibility).
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

import {
  CalendarX,
  MoreHorizontal,
  Pencil,
  Plus,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { FormField as Field } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { ListState } from "@/components/ui/list-state";
import { PageHeader } from "@/components/layout/page-header";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import {
  hasCustomerIdentity,
  hasPermission,
  isHQStaff,
  isSuperAdmin,
} from "@/lib/permission";
import {
  fromDatetimeLocalValue,
  formatDateTime as fmt,
  toDatetimeLocalValue,
} from "@/lib/format";
import type {
  Booking,
  BookingCreate,
  BookingHqRead,
  BookingStatus,
  BookingUpdate,
  Device,
} from "@/api/types";
import {
  useBookings,
  useCreateBooking,
  useCancelBooking,
  useCustomerProfiles,
  useDeviceSchedule,
  useDevices,
  useMyBookings,
  useStartBooking,
  useUpdateBooking,
} from "@/hooks/queries";

// 6-state status → {label, badge}. Each badge value is the literal Badge
// variant name (``dot-warning`` / ``dot-success`` / ``dot-muted`` /
// ``dot-destructive``), so STATUS_META reads as the plan's colour mapping
// verbatim with no intermediate token to collapse. pending/in_service/no_show
// pick a tinted dot; the neutral "settled" states (confirmed / done /
// cancelled) share the muted grey dot — informational, not warning/danger.
//
// ``confirmed`` is a forward-compat placeholder (no /confirm endpoint yet, see
// plan §0 D2) — the mapping is defined for completeness but unreachable in
// this feature; a booking never enters that state here.
const STATUS_META: Record<
  BookingStatus,
  {
    label: string;
    badge: "dot-warning" | "dot-success" | "dot-muted" | "dot-destructive";
  }
> = {
  pending: { label: "待确认", badge: "dot-warning" },
  confirmed: { label: "已确认", badge: "dot-muted" },
  in_service: { label: "服务中", badge: "dot-success" },
  done: { label: "已完成", badge: "dot-muted" },
  cancelled: { label: "已取消", badge: "dot-muted" },
  no_show: { label: "爽约", badge: "dot-destructive" },
};

// SelectValue can't render an empty string; "_none" is the sentinel for the
// "walk-in (no customer)" option in the create/edit dialog. Mirrors the
// devices-page bind dialog convention (chat-page.tsx:685-707 lineage).
const NONE = "_none";

// Only ``pending`` bookings are mutable (D10) — reschedule / cancel are hidden
// for every other state. ``confirmed`` is a forward-compat placeholder state
// that this feature never enters, so it's intentionally NOT in the mutable set
// (it would be cancelled via a future /confirm + /cancel flow, not here).
const MUTABLE_STATUS: ReadonlySet<BookingStatus> = new Set(["pending"]);

export function BookingsPage() {
  const { me } = useAuth();

  // Three-way view fork (slice 07). HQ viewers take precedence over a customer
  // binding — an HQ role wouldn't carry one anyway, but ordering the checks
  // this way keeps the cross-tenant panorama authoritative. StoreView (slice 06)
  // is the fallthrough for everyone else: tenant owners/admins/members with no
  // customer identity.
  if (isSuperAdmin(me) || isHQStaff(me)) return <HqView />;
  if (hasCustomerIdentity(me)) return <MyBookingsView />;
  return <StoreView />;
}

// ============================================================ store view
function StoreView() {
  const toast = useToast();
  const { me } = useAuth();

  const { data: bookings, isLoading } = useBookings();
  const { data: devices } = useDevices();
  // Customer profiles feed the create/edit dialog's customer Select. Only
  // fetched here (the store view); slice 07's HqView is read-only + reads
  // HQ-pre-expanded names, so it won't need this feed.
  const { data: profiles } = useCustomerProfiles();

  const createMut = useCreateBooking();
  const updateMut = useUpdateBooking();
  const cancelMut = useCancelBooking();

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
  const [createDevice, setCreateDevice] = useState("");
  const [createCustomer, setCreateCustomer] = useState<string>(NONE);
  const [createStart, setCreateStart] = useState("");
  const [createEnd, setCreateEnd] = useState("");
  const [createNotes, setCreateNotes] = useState("");
  // Edit (reschedule) dialog
  const [editTarget, setEditTarget] = useState<Booking | null>(null);
  const [editCustomer, setEditCustomer] = useState<string>(NONE);
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");
  const [editNotes, setEditNotes] = useState("");
  // Cancel confirm dialog
  const [cancelTarget, setCancelTarget] = useState<Booking | null>(null);

  // device_id → serial_number, for resolving the list's "设备名" column from
  // the booking's device_id (BookingRead carries only device_id, no name —
  // devices have no ``name`` column; serial_number IS their identifier, per
  // BookingService._to_hq_read docstring).
  const deviceMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of (devices ?? []) as Device[]) {
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
  // The narrowing cast (Booking[] | BookingHqRead[] → Booking[]) lives INSIDE
  // the memo on purpose: a derived ``list = bookings ?? []`` would re-allocate
  // the empty array every render and trip react-hooks/exhaustive-deps. Keeping
  // ``bookings`` (the react-query result, stable until data changes) as the
  // sole data dep is the clean fix.
  const filtered = useMemo(
    () => applyBookingFilter((bookings ?? []) as Booking[], filter),
    [bookings, filter],
  );

  // ---------- create ----------
  const openCreate = () => {
    setCreateDevice("");
    setCreateCustomer(NONE);
    setCreateStart("");
    setCreateEnd("");
    setCreateNotes("");
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    if (!createDevice) {
      toast.error("请选择设备");
      return;
    }
    if (!createStart || !createEnd) {
      toast.error("请填写预约时段");
      return;
    }
    const payload: BookingCreate = {
      device_id: createDevice,
      customer_id: createCustomer === NONE ? null : createCustomer,
      scheduled_start_at: fromDatetimeLocalValue(createStart),
      scheduled_end_at: fromDatetimeLocalValue(createEnd),
      notes: createNotes.trim() || null,
    };
    try {
      await createMut.mutateAsync(payload);
      toast.success("预约已创建");
      setCreateOpen(false);
    } catch (err) {
      // 400 here covers: window invalid (end <= start), device/customer not in
      // tenant, AND time overlap. The backend message is human-readable, so we
      // surface it verbatim — no client-side overlap pre-check (plan §6 UX).
      toast.error("创建失败", apiErrorMessage(err));
    }
  };

  // ---------- edit (reschedule) ----------
  const openEdit = (b: Booking) => {
    setEditTarget(b);
    setEditCustomer(b.customer_id ?? NONE);
    setEditStart(toDatetimeLocalValue(b.scheduled_start_at));
    setEditEnd(toDatetimeLocalValue(b.scheduled_end_at));
    setEditNotes(b.notes ?? "");
  };

  const submitEdit = async () => {
    if (!editTarget) return;
    if (!editStart || !editEnd) {
      toast.error("请填写预约时段");
      return;
    }
    const payload: BookingUpdate = {
      customer_id: editCustomer === NONE ? null : editCustomer,
      scheduled_start_at: fromDatetimeLocalValue(editStart),
      scheduled_end_at: fromDatetimeLocalValue(editEnd),
      notes: editNotes.trim() || null,
    };
    try {
      await updateMut.mutateAsync({ id: editTarget.id, payload });
      toast.success("已改约");
      setEditTarget(null);
    } catch (err) {
      toast.error("改约失败", apiErrorMessage(err));
    }
  };

  // ---------- cancel ----------
  const submitCancel = async () => {
    if (!cancelTarget) return;
    try {
      await cancelMut.mutateAsync(cancelTarget.id);
      toast.success("已取消预约");
      setCancelTarget(null);
    } catch (err) {
      toast.error("取消失败", apiErrorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="预约"
        subtitle="管理本店设备预约：创建、改约、取消，查看今日/明日/本周预约与设备排期。"
        actions={
          canCreate && (
            <Button onClick={openCreate}>
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
                {filtered.map((b) => {
                  const mutable = MUTABLE_STATUS.has(b.status);
                  return (
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
                          {/* Non-pending bookings have nothing to mutate in
                              this feature (start/end/no-show land in device-
                              poweron), so hide the menu entirely. */}
                          {mutable && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon">
                                  <MoreHorizontal className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                {canUpdate && (
                                  <DropdownMenuItem onClick={() => openEdit(b)}>
                                    <Pencil className="mr-2 h-4 w-4" /> 改约
                                  </DropdownMenuItem>
                                )}
                                {canCancel && (
                                  <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      className="text-destructive focus:text-destructive"
                                      onClick={() => setCancelTarget(b)}
                                    >
                                      <XCircle className="mr-2 h-4 w-4" /> 取消预约
                                    </DropdownMenuItem>
                                  </>
                                )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          )}
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      {/* ---------------- schedule grid card ---------------- */}
      <ScheduleGridCard
        devices={(devices ?? []) as Device[]}
        selectedId={gridDeviceId}
        onSelect={setGridDeviceId}
      />

      {/* ---------------- create dialog ---------------- */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>创建预约</DialogTitle>
            <DialogDescription>
              选择设备、可选客户与预约时段。时段冲突由后端校验,提交后如有冲突会提示。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Field label="设备 *">
              <Select value={createDevice} onValueChange={setCreateDevice}>
                <SelectTrigger>
                  <SelectValue placeholder="选择设备" />
                </SelectTrigger>
                <SelectContent>
                  {(devices ?? [])
                    .filter(
                      (d): d is Device =>
                        "serial_number" in (d as Device) &&
                        (d as Device).status === "active",
                    )
                    .map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.serial_number}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="客户"
              hint="可不选 — 散客(walk-in)预约不绑定客户"
            >
              <Select value={createCustomer} onValueChange={setCreateCustomer}>
                <SelectTrigger>
                  <SelectValue placeholder="选择客户(可选)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>不指定(散客)</SelectItem>
                  {(profiles ?? []).map((p) => (
                    <SelectItem key={p.customer_id} value={p.customer_id}>
                      {p.customer.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="预约开始时间 *">
              <Input
                type="datetime-local"
                value={createStart}
                onChange={(e) => setCreateStart(e.target.value)}
              />
            </Field>
            <Field label="预约结束时间 *">
              <Input
                type="datetime-local"
                value={createEnd}
                onChange={(e) => setCreateEnd(e.target.value)}
              />
            </Field>
            <Field label="备注">
              <Input
                value={createNotes}
                onChange={(e) => setCreateNotes(e.target.value)}
                placeholder="可选"
              />
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button onClick={submitCreate} disabled={createMut.isPending}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------------- edit (reschedule) dialog ---------------- */}
      {/* device_id is immutable (D10) — rendered read-only/greyed. Only pending
          bookings reach this dialog (the menu is hidden for other states), so
          no extra gating is needed inside. */}
      <Dialog
        open={!!editTarget}
        onOpenChange={(o) => !o && setEditTarget(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>改约</DialogTitle>
            <DialogDescription>
              调整预约时段、客户或备注。设备为预约身份,不可变更(如需换设备请取消后重建)。
            </DialogDescription>
          </DialogHeader>
          {editTarget && (
            <div className="space-y-4">
              <Field label="设备(不可修改)">
                <Input
                  value={
                    deviceMap.get(editTarget.device_id ?? "") ??
                    (editTarget.device_id ?? "—")
                  }
                  disabled
                />
              </Field>
              <Field label="客户">
                <Select value={editCustomer} onValueChange={setEditCustomer}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择客户(可选)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>不指定(散客)</SelectItem>
                    {(profiles ?? []).map((p) => (
                      <SelectItem key={p.customer_id} value={p.customer_id}>
                        {p.customer.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="预约开始时间 *">
                <Input
                  type="datetime-local"
                  value={editStart}
                  onChange={(e) => setEditStart(e.target.value)}
                />
              </Field>
              <Field label="预约结束时间 *">
                <Input
                  type="datetime-local"
                  value={editEnd}
                  onChange={(e) => setEditEnd(e.target.value)}
                />
              </Field>
              <Field label="备注">
                <Input
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                />
              </Field>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>
              取消
            </Button>
            <Button onClick={submitEdit} disabled={updateMut.isPending}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------------- cancel confirm dialog ---------------- */}
      <Dialog
        open={!!cancelTarget}
        onOpenChange={(o) => !o && setCancelTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认取消预约</DialogTitle>
            <DialogDescription>
              确定取消该预约?取消后预约状态变为「已取消」,不可在此恢复
              (如需重新预约请新建)。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)}>
              返回
            </Button>
            <Button
              variant="destructive"
              onClick={submitCancel}
              disabled={cancelMut.isPending}
            >
              <XCircle className="mr-2 h-4 w-4" /> 取消预约
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ============================================================ HQ panorama view
//
// Cross-tenant read-only view (super_admin / hq_staff). The HQ endpoint
// (GET /bookings/ behind require_cross_tenant_viewer) already expands
// tenant_name/device_name/customer_name server-side (BookingHqRead), so this
// table needs no client-side lookups into the devices/profiles feeds — it just
// renders the rows it gets back. There are no write controls: HQ viewers
// observe bookings across stores, never mutate them. Mirrors devices-page's
// HqView (the cross-tenant read-only fleet view) — same skeleton, data source
// swapped (useDevices→useBookings) + field mapping (serial_number→device_name,
// model_name→customer_name, status Badge→scheduled window).
function HqView() {
  const { data: bookings, isLoading } = useBookings();
  // useBookings() returns a union (Booking[] | BookingHqRead[]). The backend
  // guarantees BookingHqRead[] for HQ roles (the same guard that routes us
  // here), so we narrow once at the view boundary. A store viewer never reaches
  // this component — the top-level BookingsPage branch sees to that.
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

// ============================================================ customer "my bookings" view
//
// Customer-bound principal (a token carrying ``customer_id``). The
// GET /me/bookings endpoint (slice 04) already filters server-side to the
// caller's own bookings — no client-side filter needed. Read-only: creating a
// booking is a store-staff responsibility (a customer can't book for itself),
// so there are no write controls here.
//
// A customer never sees a walk-in booking on this surface (those have
// customer_id null and are excluded by the backend predicate), so every row
// has a real scheduled window. Device name isn't in BookingRead (it carries
// only device_id); we don't fetch the devices feed here to keep this view
// cheap — the device_id prefix is shown as a fallback identifier, matching the
// store view's soft-delete transient handling.
export function MyBookingsView() {
  const { data: bookings, isLoading } = useMyBookings();
  // 切片 02:customer 自助「确认开机」(pending → in_service)。后端按 caller
  // 的 customer_id 做 own 校验(防越权)+ walk-in 拦截(散客预约仅门店可开机),
  // 故前端无需传 customer_id,真调 startBooking(id) 即可。失败 toast 透传后端
  // 信息(非法态 400 / 无权 403)。
  const startMut = useStartBooking();
  const toast = useToast();

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

// ============================================================ schedule grid
//
// The per-device 7-day grid. No calendar widget (plan: "别过度设计,不做日历
// 控件"). Layout: a device picker + one column per day for the next 7 days
// (today → today+6); each column lists that day's bookings as slot-box cards,
// tinted by the three display buckets (active = pending/confirmed/in_service,
// done = done, released = cancelled/no_show). Empty days render a muted
// placeholder so the column shape is stable.
//
// ``useDeviceSchedule(id, today, today+7d)`` returns only days with ≥1 booking,
// so we look up each of the 7 days in the result map (missing key → empty col).
function ScheduleGridCard({
  devices,
  selectedId,
  onSelect,
}: {
  devices: Device[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  // The 7-day window: today → today+7d (exclusive end, matching the backend's
  // left-closed/right-open overlap semantics). Computed once per render; the
  // user isn't paginating weeks in this slice.
  const { days, startIso, endIso } = useMemo(() => {
    const today = startOfToday();
    const end = addDays(today, 7);
    const arr: { iso: string; label: string }[] = [];
    for (let i = 0; i < 7; i++) {
      const d = addDays(today, i);
      arr.push({ iso: isoDate(d), label: dayLabel(d, i) });
    }
    return { days: arr, startIso: today.toISOString(), endIso: end.toISOString() };
  }, []);

  const { data: schedule, isLoading } = useDeviceSchedule(
    selectedId || null,
    startIso,
    endIso,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>设备排期</CardTitle>
        <CardDescription>
          选择一台设备,查看未来 7 天的预约排布。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label="设备">
          <Select value={selectedId} onValueChange={onSelect}>
            <SelectTrigger>
              <SelectValue placeholder="选择设备查看排期" />
            </SelectTrigger>
            <SelectContent>
              {devices.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.serial_number}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {!selectedId ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            选择一台设备以查看排期。
          </p>
        ) : (
          // The 7 columns always render (one per day), so there's no list-level
          // empty state — each empty day shows its own "空" placeholder inside
          // the column. ListState is used here purely as a loading gate while
          // the schedule fetch is in flight.
          <ListState isLoading={isLoading} isEmpty={false}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
              {days.map((day) => {
                const dayBookings = schedule?.[day.iso] ?? [];
                return (
                  <div
                    key={day.iso}
                    className="min-h-32 rounded-md border bg-muted/30 p-2"
                  >
                    <div className="mb-2 text-xs font-medium text-muted-foreground">
                      {day.label}
                    </div>
                    {dayBookings.length === 0 ? (
                      <p className="py-4 text-center text-xs text-muted-foreground/60">
                        空
                      </p>
                    ) : (
                      <div className="space-y-1.5">
                        {dayBookings.map((b) => (
                          <ScheduleSlot key={b.id} booking={b} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ListState>
        )}
      </CardContent>
    </Card>
  );
}

/** One booking inside a schedule day column. Colour-coded by the three display
 * buckets (active / done / released) so a glance reads the device's day. */
function ScheduleSlot({ booking }: { booking: Booking }) {
  const tone = slotTone(booking.status);
  const time = `${hhmm(booking.scheduled_start_at)}–${hhmm(booking.scheduled_end_at)}`;
  return (
    <div
      className={`rounded border px-2 py-1 text-xs ${tone.cls}`}
      title={`${time} · ${STATUS_META[booking.status].label}`}
    >
      <div className="font-medium">{time}</div>
      <div className="opacity-80">{STATUS_META[booking.status].label}</div>
    </div>
  );
}

// ============================================================ shared bits

/** List filter presets for the chip row. "all" = no filter. */
type BookingFilter =
  | "all"
  | "today"
  | "tomorrow"
  | "this_week"
  | "pending"
  | "no_show";

const FILTER_OPTIONS: { value: BookingFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "today", label: "今日" },
  { value: "tomorrow", label: "明日" },
  { value: "this_week", label: "本周" },
  { value: "pending", label: "待确认" },
  { value: "no_show", label: "爽约" },
];

/** Hand-rolled mutually-exclusive button row. Mirrors the dashboard trend-days
 * toggle (dashboard-page.tsx:244) — no shadcn Tabs primitive exists in this
 * project, and settings-page deliberately avoids adding one. */
function FilterChips({
  value,
  onChange,
}: {
  value: BookingFilter;
  onChange: (v: BookingFilter) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {FILTER_OPTIONS.map((opt) => (
        <Button
          key={opt.value}
          variant={value === opt.value ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}

function BookingStatusBadge({ status }: { status: BookingStatus }) {
  const meta = STATUS_META[status];
  return <Badge variant={meta.badge}>{meta.label}</Badge>;
}

/** Resolve a booking's device_id to its serial number for display. Falls back
 * to the id prefix when the device was soft-deleted between list fetches (the
 * backend's SET-NULL FK keeps the booking row, but a live device list filters
 * soft-deleted rows out — a rare transient). */
function deviceNameOf(
  deviceId: string | null,
  deviceMap: Map<string, string>,
): string {
  if (!deviceId) return "—";
  return deviceMap.get(deviceId) ?? `设备(${deviceId.slice(0, 8)})`;
}

// ------------------------------------------------------------- date helpers
//
// Local-time date math for the filter chips + schedule grid. All comparisons
// are on calendar days (``YYYY-MM-DD``), not timestamps — a "today" filter
// matches the whole local day, ignoring hours. Kept local (no UTC shift)
// because a store's booking sheet is read in wall-clock time.

function startOfToday(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

/** ``YYYY-MM-DD`` for a Date (local). Used as the DeviceSchedule map key. */
function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** ``HH:mm`` from an ISO timestamp (local). Slot card time label. */
function hhmm(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** ``周一 7/24`` style label for a schedule column header. ``offset`` is 0 for
 * today (rendered as "今天"). */
function dayLabel(d: Date, offset: number): string {
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const prefix = offset === 0 ? "今天" : offset === 1 ? "明天" : weekdays[d.getDay()];
  return `${prefix} ${d.getMonth() + 1}/${d.getDate()}`;
}

/** Apply a chip filter to the booking list. Time filters compare on the local
 * calendar day of ``scheduled_start_at``; status filters are an exact match. */
function applyBookingFilter(
  list: Booking[],
  filter: BookingFilter,
): Booking[] {
  if (filter === "all") return list;
  if (filter === "pending" || filter === "no_show") {
    return list.filter((b) => b.status === filter);
  }
  const today = startOfToday();
  const todayKey = isoDate(today);
  const tomorrowKey = isoDate(addDays(today, 1));
  // "本周" = the Monday-containing week of today (Mon→Sun), so a sheet printed
  // mid-week still shows the whole current week.
  const weekStart = addDays(today, -((today.getDay() + 6) % 7)); // Mon of this week
  const weekEnd = addDays(weekStart, 7); // exclusive
  return list.filter((b) => {
    const start = new Date(b.scheduled_start_at);
    const key = isoDate(start);
    if (filter === "today") return key === todayKey;
    if (filter === "tomorrow") return key === tomorrowKey;
    // this_week: start date within [weekStart, weekEnd)
    return start >= weekStart && start < weekEnd;
  });
}

/** Slot-box colour bucket for the schedule grid. Three display tones match the
 * plan's "booked/active/done 三态色" mapping (active = pending/confirmed/
 * in_service; done = done; released = cancelled/no_show). */
function slotTone(
  status: BookingStatus,
): { cls: string } {
  if (status === "done") {
    return { cls: "border-border bg-background text-muted-foreground" };
  }
  if (status === "cancelled" || status === "no_show") {
    return { cls: "border-destructive/30 bg-destructive/5 text-destructive/80 line-through" };
  }
  // active bucket: pending / confirmed / in_service
  return { cls: "border-primary/30 bg-primary/5 text-primary" };
}
