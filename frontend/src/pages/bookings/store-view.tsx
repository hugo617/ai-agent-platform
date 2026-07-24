/**
 * bookings/ StoreView — within-tenant booking CRUD surface.
 *
 * Extracted from the original bookings-page.tsx (plan-bookings-page-split.md).
 * Pure locality move: zero behaviour change. The ``as Booking[]`` / ``as
 * Device[]`` casts on union returns are preserved verbatim — narrowing them
 * is candidate 8 in the 2026-07-25 architecture review, intentionally out of
 * scope here.
 *
 * StoreView (device-booking slice 06) is the within-tenant CRUD surface — a
 * filterable booking list + per-device 7-day schedule grid, gating create /
 * reschedule / cancel behind ``hasPermission(me, "bookings", act)`` (members
 * only hold ``bookings:read`` so the write actions stay hidden). device-poweron
 * (slice 03) added the DropdownMenu with three lifecycle actions (start /
 * end / no-show) gated on ACTIONABLE_STATUS (pending/confirmed/in_service).
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
  Play,
  Plus,
  Square,
  UserX,
  XCircle,
} from "lucide-react";

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
import { hasPermission } from "@/lib/permission";
import {
  toDatetimeLocalValue,
} from "@/lib/format";
import type {
  Booking,
  BookingCreate,
  BookingEndPayload,
  BookingUpdate,
  Device,
} from "@/api/types";
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
  ACTIONABLE_STATUS,
  BookingStatusBadge,
  FilterChips,
  MUTABLE_STATUS,
  NONE,
  ScheduleGridCard,
  applyBookingFilter,
  deviceNameOf,
  fmt,
  fromDatetimeLocalValue,
  type BookingFilter,
} from "./shared";

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

  const createMut = useCreateBooking();
  const updateMut = useUpdateBooking();
  const cancelMut = useCancelBooking();
  // device-poweron (切片 03):three lifecycle mutations. ``start`` reuses the
  // same hook as the customer view (store path needs ``:update``); ``end`` /
  // ``no-show`` are owner-only (``:delete``). Each invalidates the same
  // BOOKING_WRITE_KEYS set on success (see queries.ts).
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
  // device-poweron (切片 03):end-service dialog (target booking + free-text
  // feedback). The dialog collects the optional service note in a textarea
  // (raw JSON string parsed at submit — matches the customers-page "标签 JSON"
  // convention; we don't ship a richer form here, the feedback dict is a free-
  // form audit trail). no-show has no body so it just needs a confirm dialog.
  const [endTarget, setEndTarget] = useState<Booking | null>(null);
  const [endFeedback, setEndFeedback] = useState("");
  const [noShowTarget, setNoShowTarget] = useState<Booking | null>(null);

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
  //
  // Note(candidate-8): split fetchBookings so this cast goes away.
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

  // ---------- device-poweron lifecycle actions ----------
  // ``start`` (pending/confirmed → in_service, walk-in OK). The same hook the
  // customer view uses; the store path is authorized by ``bookings:update``
  // server-side (owner/admin — member 403, button hidden via canUpdate).
  const submitStart = async (b: Booking) => {
    try {
      await startMut.mutateAsync(b.id);
      toast.success("已开机");
    } catch (err) {
      toast.error("开机失败", apiErrorMessage(err));
    }
  };

  // ``end`` (in_service → done). Parses the feedback textarea as JSON; a blank
  // or non-JSON input is treated as "no feedback" (the column stays null) — the
  // textarea is explicitly optional, mirroring the customers-page tags-JSON
  // convention. We do NOT block submit on parse failure (free-form audit note,
  // not structured data): the backend stores whatever dict we send verbatim.
  //
  // Note(candidate-7): move this JSON.parse fallback into the endpoint layer.
  const submitEnd = async () => {
    if (!endTarget) return;
    const trimmed = endFeedback.trim();
    let payload: BookingEndPayload | undefined;
    if (trimmed) {
      try {
        payload = { feedback: JSON.parse(trimmed) as Record<string, unknown> };
      } catch {
        // Fall back to wrapping the raw note so the audit trail isn't lost —
        // the operator clearly typed something, treat it as a text note.
        payload = { feedback: { note: trimmed } };
      }
    }
    try {
      await endMut.mutateAsync({ id: endTarget.id, payload });
      toast.success("已结束服务");
      setEndTarget(null);
      setEndFeedback("");
    } catch (err) {
      toast.error("结束失败", apiErrorMessage(err));
    }
  };

  // ``no-show`` (pending/confirmed/in_service → no_show). Pure status flip.
  const submitNoShow = async () => {
    if (!noShowTarget) return;
    try {
      await noShowMut.mutateAsync(noShowTarget.id);
      toast.success("已标记爽约");
      setNoShowTarget(null);
    } catch (err) {
      toast.error("标记爽约失败", apiErrorMessage(err));
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
                  // device-poweron (切片 03):the menu trigger is shown whenever
                  // the row still has ≥1 lifecycle / edit / cancel action
                  // available AND the principal holds a write perm. Terminal
                  // rows (done/cancelled/no_show) hide the menu entirely.
                  const actionable = ACTIONABLE_STATUS.has(b.status);
                  // Per-state action visibility (B3/B4):start guards on
                  // ``canUpdate`` (:update, owner/admin);end/no-show guard on
                  // ``canCancel`` (:delete, owner only — admin has no such perm
                  // per B2, the buttons stay hidden client-side).
                  const canStart =
                    actionable &&
                    (b.status === "pending" || b.status === "confirmed") &&
                    canUpdate;
                  const canEnd = b.status === "in_service" && canCancel;
                  const canMarkNoShow = actionable && canCancel;
                  const showMenu =
                    (canUpdate || canCancel) &&
                    actionable &&
                    (mutable || canStart || canEnd || canMarkNoShow);
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
                          {showMenu && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon">
                                  <MoreHorizontal className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                {/* 改约 + 取消预约 stay pending-only
                                    (MUTABLE_STATUS) — they are booking edits,
                                    not lifecycle actions. */}
                                {mutable && canUpdate && (
                                  <DropdownMenuItem onClick={() => openEdit(b)}>
                                    <Pencil className="mr-2 h-4 w-4" /> 改约
                                  </DropdownMenuItem>
                                )}
                                {/* 确认开机 (device-poweron):walk-in 散客
                                    预约也走这条 (B4)。``confirmed`` 行的按钮是
                                    防御性渲染 —— 状态机允许 pending/confirmed
                                    → in_service,但 device-booking 永不写
                                    confirmed,故运行期不可达。 */}
                                {canStart && (
                                  <DropdownMenuItem
                                    onClick={() => submitStart(b)}
                                  >
                                    <Play className="mr-2 h-4 w-4" /> 确认开机
                                  </DropdownMenuItem>
                                )}
                                {/* 结束服务 (device-poweron):弹 feedback
                                    dialog。owner only (canDelete). */}
                                {canEnd && (
                                  <DropdownMenuItem
                                    onClick={() => {
                                      setEndTarget(b);
                                      setEndFeedback("");
                                    }}
                                  >
                                    <Square className="mr-2 h-4 w-4" /> 结束服务
                                  </DropdownMenuItem>
                                )}
                                {/* 爽约 (device-poweron):确认 dialog →
                                    noShowBooking. owner only. */}
                                {canMarkNoShow && (
                                  <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      className="text-destructive focus:text-destructive"
                                      onClick={() => setNoShowTarget(b)}
                                    >
                                      <UserX className="mr-2 h-4 w-4" /> 标记爽约
                                    </DropdownMenuItem>
                                  </>
                                )}
                                {/* 取消预约 (device-booking,保留):pending
                                    only,owner only. */}
                                {mutable && canCancel && (
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

      {/* ---------------- end-service dialog (device-poweron 切片 03) ------------- */}
      {/* Owner only (``:delete``). The textarea is optional — a blank submit
          ends the booking with no service note. ``submitEnd`` accepts raw JSON
          (parsed into ``feedback``) or free text (wrapped as
          ``{ note: <text> }`` so the operator's typed note is never silently
          dropped on a JSON.parse failure). This fallback is a slice-03 UX
          decision (spec D10 only requires an optional free-form ``feedback``
          dict); it diverges from customers-page's "标签 JSON" textarea, which
          rejects non-JSON. */}
      <Dialog
        open={!!endTarget}
        onOpenChange={(o) => {
          if (!o) {
            setEndTarget(null);
            setEndFeedback("");
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>结束服务</DialogTitle>
            <DialogDescription>
              标记该预约为「已完成」并记录结束时间。可填写服务反馈(JSON 或纯文本,
              可选)。结束操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <Field
            label="服务反馈(可选)"
            hint='如 {"rating": 5, "note": "满意"} 或纯文本,留空则不记录'
          >
            <textarea
              value={endFeedback}
              onChange={(e) => setEndFeedback(e.target.value)}
              placeholder='{"rating": 5, "note": "客户反馈"}'
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              rows={3}
            />
          </Field>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setEndTarget(null);
                setEndFeedback("");
              }}
            >
              取消
            </Button>
            <Button onClick={submitEnd} disabled={endMut.isPending}>
              <Square className="mr-2 h-4 w-4" /> 结束服务
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------------- no-show confirm dialog (device-poweron 切片 03) --------- */}
      {/* Owner only (``:delete``). Pure status flip — no body, no extra input.
          Mirrors the cancel-confirm dialog shape. */}
      <Dialog
        open={!!noShowTarget}
        onOpenChange={(o) => !o && setNoShowTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认标记爽约</DialogTitle>
            <DialogDescription>
              确定将该预约标记为「爽约」?爽约记录会影响排期释放与统计,操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNoShowTarget(null)}>
              返回
            </Button>
            <Button
              variant="destructive"
              onClick={submitNoShow}
              disabled={noShowMut.isPending}
            >
              <UserX className="mr-2 h-4 w-4" /> 标记爽约
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
