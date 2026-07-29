/**
 * bookings/ HqView — cross-tenant panorama + write surface for platform
 * writers (super_admin / hq_staff).
 *
 * Extracted from the original bookings-page.tsx (plan-bookings-page-split.md)
 * as a read-only panorama. platform-cross-tenant-write slice 04 lifts it from
 * read-only to write-capable: a「目标门店」picker at the top + per-row write
 * actions (the same DropdownMenu + Dialog bodies the store view uses, reused
 * via ``shared-dialog.tsx``). The HQ endpoint already expands
 * tenant_name/device_name/customer_name server-side (BookingHqRead), so the
 * list still needs no client-side lookups.
 *
 * booking-schedule-grid 切片 04b adds a Tabs row (列表 / 网格) once a target is
 * picked — the grid Tab renders the device×time ``ScheduleGrid`` (切片 04a) fed
 * by ``useTenantBookingsByDate`` (切片 02 endpoint) + ``useBookingConfigEffective``
 * (切片 01), with a「⚙ 设置」button opening ``BookingConfigDialog`` (切片 03) and
 * empty-cell clicks prefilling ``BookingCreateDialog`` (device + slot). The list
 * Tab stays the default; the grid is an alternate view onto the same target
 * store, NOT a replacement.
 *
 * Cross-tenant write contract (plan §4.5.4a 补丁 5):
 * - Platform writers MUST select a target tenant before any write action —
 *   the row action menu stays hidden until a target is picked (AC9).
 * - The selected target rides the ``tenantId`` closure param on every write
 *   hook (cancel/start/end/no_show → ?tenant_id= query; create/update → body
 *   field). The backend resolves ``effective_tenant_id`` from it (plan §1).
 * - The customer field degrades to a free-text global-id input (plan §4.5.5
 *   D2-ii: HQ operators can't see the target store's customer list without
 *   leaking cross-tenant data — they type a global id or leave blank for
 *   walk-in). ``profiles`` is always ``[]`` here.
 *
 * Cache key safety (AC7): the bookings list query itself is cross-tenant
 * (returns BookingHqRead[] for every store), so switching target doesn't
 * change the list data — no per-target cache key needed for the read. The
 * risk AC7 guards against is "stale scoped data after a target switch"; here
 * the only scoped feed is ``profiles`` and we deliberately don't fetch it.
 * As a belt-and-braces measure we still invalidate ``qk.bookings`` on target
 * switch so the panorama refreshes against the latest server state.
 *
 * Bookings feed: ``useBookingsAll()`` (not the store-scoped ``useBookings``) —
 * it returns ``BookingHqRead[]`` natively, no view-boundary cast. The device
 * feed likewise uses ``useDevicesAll()`` (returns ``DeviceHqRead[]`` natively,
 * plan-union-cast-split slice 2) — both unions are now fixed at the hook layer,
 * so this component has zero view-boundary casts.
 */
import { useMemo, useState } from "react";

import { CalendarX, Plus, Settings } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/components/auth/auth-context";
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
import type {
  Booking,
  BookingConfigUpsert,
  BookingCreate,
  BookingEndPayload,
  BookingHqRead,
  BookingUpdate,
  DeviceHqRead,
} from "@/api/types";
import {
  qk,
  useAllTenants,
  useBookingConfigEffective,
  useBookingsAll,
  useCancelBooking,
  useCreateBooking,
  useDevicesAll,
  useEndBooking,
  useNoShowBooking,
  usePlatformBookingConfig,
  useStartBooking,
  useTenantBookingsByDate,
  useTenantBookingConfig,
  useUpdateBooking,
  useUpdatePlatformBookingConfig,
  useUpdateTenantBookingConfig,
} from "@/hooks/queries";
import { isSuperAdmin } from "@/lib/permission";
import { formatDateTime as fmt } from "@/lib/format";
// Deep imports per plan-shared-tsx-split 切片 2 (D4/D5): BookingStatusBadge
// stays in ./shared (D2 — cross-view display primitive); date helpers move to
// ./date-utils; fmt sourced directly from @/lib/format (no re-export indirection).
import { BookingStatusBadge } from "./shared";
import { isoDate, startOfToday } from "./date-utils";
import { BookingConfigDialog, DEFAULT_BOOKING_CONFIG } from "./config-dialog";
import { ScheduleGrid } from "./schedule-grid";
import {
  BookingCancelDialog,
  BookingCreateDialog,
  BookingEditDialog,
  BookingEndDialog,
  BookingNoShowDialog,
  BookingRowMenu,
} from "./shared-dialog";

export function HqView() {
  const toast = useToast();
  const qc = useQueryClient();
  const { data: bookings, isLoading } = useBookingsAll();
  const { data: tenants } = useAllTenants();
  // HQ viewers get DeviceHqRead[] from useDevicesAll (the HQ-panorama variant
  // of the devices feed; the union is fixed at the hook layer, plan-union-cast-
  // split slice 2). We filter to the selected target so the create dialog's
  // device picker only offers that store's active devices — the dialog would
  // otherwise show an empty dropdown (no target-scoped feed exists; plan
  // §4.5.5 前端 says "复用 StoreView Dialog" — reusing the cross-store feed
  // + filtering client-side is the natural fit, no new endpoint needed).
  const { data: devices } = useDevicesAll();

  // useBookingsAll() returns BookingHqRead[] natively (the union is fixed at
  // the hook layer, plan-union-cast-split slice 1), so no narrowing cast is
  // needed here. A store viewer never reaches this component — the top-level
  // BookingsPage branch sees to that.
  const list = bookings ?? [];

  // ---------- target tenant picker ----------
  // Platform writers MUST pick a target before any write. Empty = no write
  // controls rendered (AC9). The picker is sourced from useAllTenants
  // (GET /tenants/all, super_admin + hq_staff authorised; plan §4.5.5 前端).
  const [targetTenantId, setTargetTenantId] = useState<string>("");

  // useDevicesAll() returns DeviceHqRead[] natively, so the filter takes a
  // typed array — no view-boundary ``as`` cast (plan-union-cast-split slice 2).
  //
  // MUST come after the ``const [targetTenantId, ...]`` declaration above: the
  // .filter callback reads targetTenantId, and JS ``const`` does not hoist its
  // initializer — referencing it earlier throws a TDZ ReferenceError that
  // crashes HqView (white screen on /bookings for HQ roles). Regression test:
  // "useDevices 返回非空数组时不抛 TDZ ReferenceError" in hq-view.test.tsx.
  const targetDevices = (devices ?? []).filter(
    (d) => d.tenant_id === targetTenantId && d.status === "active",
  );

  // Switching target invalidates the bookings query (AC7). The cross-tenant
  // list itself is unaffected (its data is the same regardless of target);
  // this is belt-and-braces so the panorama refreshes against the latest
  // server state right after a target switch. Cheap (HQ viewers don't render
  // the schedule grid).
  const onTargetChange = (id: string) => {
    setTargetTenantId(id);
    qc.invalidateQueries({ queryKey: qk.bookings });
    // 切片 04b: a stale createPrefill belongs to the OLD target store (its
    // device id isn't valid for the new store). Clear it so the next create
    // Dialog open — whether from the list button or a fresh grid click —
    // starts clean for the newly-picked store.
    setCreatePrefill(null);
  };

  // ---------- write hooks (closure-bound to the selected target) ----------
  // Constructed once per render with ``targetTenantId``; the same
  // ``mutateAsync(id)`` call site as the store view transparently carries
  // the target. Undefined target (no selection) → no query param / no body
  // field → backend 400s on "platform writer must specify target"
  // (plan §4.5.4a 补丁 5). The hooks are inert in that state because the
  // menu is hidden until a target is picked (AC9).
  const createMut = useCreateBooking();
  const updateMut = useUpdateBooking();
  const cancelMut = useCancelBooking(targetTenantId || undefined);
  const startMut = useStartBooking(targetTenantId || undefined);
  const endMut = useEndBooking(targetTenantId || undefined);
  const noShowMut = useNoShowBooking(targetTenantId || undefined);

  // ---------- 切片 04b: schedule-grid view mode + data ----------
  // Tabs appear only after a target is picked (canWrite). The grid Tab is an
  // alternate view onto the SAME target store the list shows — same target,
  // same write hooks, just a different presentation. ``viewMode`` defaults to
  // "list" (AC: 默认列表); the user can flip to "grid" to see the device×time
  // sheet. Hand-rolled Button row (FilterChips 范式, no shadcn Tabs — plan §8
  // out-of-scope).
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  // Grid date: defaults to today (local), clamped to ≥ today via the input's
  // ``min`` attr (AC: min=今天默认今天). ``isoDate`` gives local YYYY-MM-DD so
  // the value matches the user's calendar regardless of tz (toISOString would
  // drift a day in the evening east of UTC). Memoised once — the default
  // doesn't change across renders; the user overrides it via the input.
  const todayISO = useMemo(() => isoDate(startOfToday()), []);
  const [gridDate, setGridDate] = useState<string>(todayISO);

  // Grid data (切片 02 endpoint + 切片 01 effective config). Both gated on a
  // picked target — useTenantBookingsByDate is ``enabled: !!tenantId``
  // internally, and useBookingConfigEffective tolerates undefined the same
  // way. They only fire when viewMode==="grid" && canWrite, but react-query
  // doesn't support conditional hooks — so we always call them and let
  // ``enabled`` + the component tree gate actual fetches. Cheap: the grid Tab
  // isn't rendered until viewMode flips, and these stay dormant meanwhile.
  const { data: gridBookings, isLoading: gridLoading } = useTenantBookingsByDate(
    targetTenantId || undefined,
    gridDate,
  );
  const { data: effectiveConfig } = useBookingConfigEffective(
    targetTenantId || undefined,
  );

  // Config Dialog (切片 03): super_admin sees two columns (platform + tenant),
  // hq_staff sees one (tenant). The two read hooks + two write hooks mirror
  // the backend's two-level config router. ``isSuperAdmin(me)`` is computed
  // in render (cheap, mirrors dashboard-page's pattern) — kept out of the
  // Dialog so the Dialog stays a pure body.
  const { me } = useAuth();
  const admin = isSuperAdmin(me);
  const { data: platformConfig } = usePlatformBookingConfig();
  const { data: tenantConfig } = useTenantBookingConfig(targetTenantId || "");
  const updatePlatformConfigMut = useUpdatePlatformBookingConfig();
  const updateTenantConfigMut = useUpdateTenantBookingConfig(
    targetTenantId || "",
  );
  const [configOpen, setConfigOpen] = useState(false);

  // Prefill for the create Dialog when opened from a grid cell click (AC:
  // 点击空 cell → 复用 BookingCreateDialog 预填 device + start/end). Null on
  // the list Tab's「创建预约」button path → the Dialog opens blank as before.
  const [createPrefill, setCreatePrefill] = useState<{
    deviceId: string;
    start: string;
    end: string;
  } | null>(null);

  // ---------- dialog state ----------
  // Edit target is typed BookingHqRead (the row shape we render); the shared
  // Dialog accepts Booking (BookingHqRead extends Booking — subtype OK). We
  // keep the richer type here so we can read device_name for the read-only
  // device field without a client-side lookup.
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<BookingHqRead | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Booking | null>(null);
  const [endTarget, setEndTarget] = useState<Booking | null>(null);
  const [noShowTarget, setNoShowTarget] = useState<Booking | null>(null);

  // ---------- write handlers ----------
  // Mirror StoreView's handler shape; the only difference is the target
  // tenantId is threaded via the closure-bound hooks above (no explicit
  // payload.tenant_id needed in the handler — the hook adds it for the
  // query-param actions). Create + edit still pass tenant_id in the body
  // via the Dialog's ``tenantId`` prop.
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

  // 切片 04b: config Dialog submit. Routes scope → the matching two-level
  // write hook, surfaces the toast, and closes the Dialog on success. The
  // hooks already invalidate BOOKING_CONFIG_WRITE_KEYS (the whole config
  // family), so effectiveConfig + both columns refresh automatically — no
  // manual invalidateQueries needed here. Mirrors the create/edit handler
  // shape (parent owns mutation + toast + close).
  const handleConfigSubmit = async (
    scope: "platform" | "tenant",
    payload: BookingConfigUpsert,
  ) => {
    try {
      if (scope === "platform") {
        await updatePlatformConfigMut.mutateAsync(payload);
      } else {
        await updateTenantConfigMut.mutateAsync(payload);
      }
      toast.success(scope === "platform" ? "平台配置已保存" : "门店配置已保存");
      setConfigOpen(false);
    } catch (err) {
      toast.error("保存配置失败", apiErrorMessage(err));
    }
  };

  // 切片 04b: empty-cell click on the grid → prefill the create Dialog with
  // the clicked device + slot, then open it. Mirrors how the list Tab's
  // 「创建预约」button opens the same Dialog (just without prefill). The
  // ScheduleGrid hands us (device, startISO, endISO); we stash them and let
  // BookingCreateDialog's defaultDeviceId/defaultStart/defaultEnd props do
  // the actual form prefill.
  const handleSlotClick = (
    device: DeviceHqRead,
    startISO: string,
    endISO: string,
  ) => {
    setCreatePrefill({ deviceId: device.id, start: startISO, end: endISO });
    setCreateOpen(true);
  };

  // HQ operators bypass casbin require server-side (plan §4.5.4a 补丁 2), so
  // the row menu's canUpdate/canCancel guards reduce to "a target is picked".
  // Without a target the menu is hidden entirely (AC9); with one, every
  // status-driven action is available just like a store owner.
  const canWrite = !!targetTenantId;

  return (
    <div className="space-y-6">
      <PageHeader
        title="预约（总部视图）"
        subtitle="跨店聚合：查看所有门店的设备预约，并选定目标门店代为运营(创建/改约/取消/开机/结束/爽约)。"
        actions={
          canWrite && (
            <Button
              onClick={() => {
                // List Tab's create button: open the Dialog with NO prefill
                // (the prefill is a grid-cell-click concern only). Resetting
                // here also clears any stale prefill from a previous grid
                // click so the operator gets a blank form.
                setCreatePrefill(null);
                setCreateOpen(true);
              }}
            >
              <Plus className="mr-2 h-4 w-4" /> 创建预约
            </Button>
          )
        }
      />

      <Card>
        <CardHeader className="space-y-4">
          <div>
            <CardTitle>全局预约列表</CardTitle>
            <CardDescription>
              共 {list.length} 条预约（跨全部门店）
              {canWrite ? "" : " — 请先选择目标门店才能代为操作"}
            </CardDescription>
          </div>
          {/* Target tenant picker. Required before any write — the row action
              menu is hidden until a target is selected (AC9). Sourced from
              GET /tenants/all (super_admin + hq_staff authorised). */}
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">目标门店：</span>
            <Select value={targetTenantId} onValueChange={onTargetChange}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="选择目标门店" />
              </SelectTrigger>
              <SelectContent>
                {(tenants ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {canWrite && (
              <span className="text-xs text-muted-foreground">
                写操作目标 →{" "}
                {tenants?.find((t) => t.id === targetTenantId)?.name ??
                  targetTenantId}
              </span>
            )}
          </div>
          {/* 切片 04b: view-mode Tabs. Hand-rolled Button row (FilterChips
              范式 — no shadcn Tabs, plan §8 out-of-scope). Shown only after a
              target is picked: the grid needs a target to query, and the list
              is the default. aria-pressed mirrors config-dialog's preset
              buttons so the active Tab is announced to screen readers. */}
          {canWrite && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant={viewMode === "list" ? "default" : "outline"}
                aria-pressed={viewMode === "list"}
                onClick={() => setViewMode("list")}
              >
                列表
              </Button>
              <Button
                size="sm"
                variant={viewMode === "grid" ? "default" : "outline"}
                aria-pressed={viewMode === "grid"}
                onClick={() => setViewMode("grid")}
              >
                网格
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {viewMode === "list" || !canWrite ? (
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
                  {canWrite && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
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
                    {canWrite && (
                      <TableCell className="text-right">
                        {/* BookingRowMenu narrows booking to Booking (the
                            menu logic uses status only, which is on the base
                            type). The cast is safe — BookingHqRead extends
                            Booking. */}
                        <BookingRowMenu
                          booking={b as Booking}
                          canUpdate={canWrite}
                          canCancel={canWrite}
                          onEdit={(bk) => setEditTarget(bk as BookingHqRead)}
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
          ) : (
            /* 切片 04b: grid view. Date picker (min=今天默认今天, AC) + ⚙ 设置
             * button (opens 切片 03 BookingConfigDialog) + ScheduleGrid (切片
             * 04a). The grid is fed by useTenantBookingsByDate (切片 02) +
             * useBookingConfigEffective (切片 01); an empty-cell click prefills
             * + opens BookingCreateDialog (handleSlotClick). Effective config
             * may be undefined while loading — fall back to the backend's
             * hardcoded defaults (45/08:00/22:00) so the grid renders rows
             * immediately rather than blanking on first paint. */
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <label
                  htmlFor="grid-date"
                  className="text-sm font-medium"
                >
                  日期：
                </label>
                <input
                  id="grid-date"
                  type="date"
                  value={gridDate}
                  min={todayISO}
                  onChange={(e) => setGridDate(e.target.value || todayISO)}
                  className="rounded-md border border-input bg-transparent px-3 py-1.5 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfigOpen(true)}
                >
                  <Settings className="mr-2 h-4 w-4" /> 设置
                </Button>
              </div>
              {gridLoading ? (
                <ListState
                  isLoading
                  isEmpty={false}
                  loadingVariant="skeleton"
                  skeletonRows={8}
                >
                  <></>
                </ListState>
              ) : (
                <ScheduleGrid
                  devices={targetDevices}
                  bookings={gridBookings ?? []}
                  config={effectiveConfig ?? DEFAULT_BOOKING_CONFIG}
                  selectedDate={new Date(`${gridDate}T00:00:00`)}
                  onSlotClick={handleSlotClick}
                />
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---------------- shared Dialogs (reused from store-view) ---------------- */}
      {/* HQ path: tenantId = selected target (closure on the picked store);
          profiles = [] (D2-ii: HQ can't see the target store's customer list
          — the customer field degrades to a free-text global-id input).
          devices = [] (HQ doesn't fetch a target-store device list; the
          create dialog's empty-devices branch shows a placeholder until a
          target-scoped feed exists — out of scope for slice 04). */}
      <BookingCreateDialog
        open={createOpen}
        devices={targetDevices}
        profiles={[]}
        tenantId={targetTenantId || undefined}
        isPending={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
        /* 切片 04b: grid-cell-click prefill. Null on the list Tab's create
           button (we reset it there) → Dialog opens blank. Set on a grid
           empty-cell click → device + slot prefilled (P7 spy-on-children
           test asserts these props). */
        defaultDeviceId={createPrefill?.deviceId}
        defaultStart={createPrefill?.start}
        defaultEnd={createPrefill?.end}
      />
      <BookingEditDialog
        target={editTarget}
        deviceName={
          editTarget
            ? editTarget.device_name ??
              (editTarget.device_id
                ? `设备(${editTarget.device_id.slice(0, 8)})`
                : "—")
            : ""
        }
        profiles={[]}
        tenantId={targetTenantId || undefined}
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
      {/* 切片 04b: schedule-grid config Dialog (切片 03 body). super_admin →
          two columns (platform + tenant); hq_staff → one (tenant). The two
          read hooks supply the seeded rows (null when not customised yet);
          onSubmit routes scope → the matching two-level write hook. The
          tenant column's name is the picked store (tenants lookup); falls
          back to the raw id when the tenant row somehow isn't in the
          all-tenants feed (defensive — the picker sourced from the same
          feed so this is unreachable in practice). */}
      <BookingConfigDialog
        open={configOpen}
        isSuperAdmin={admin}
        targetTenantName={
          tenants?.find((t) => t.id === targetTenantId)?.name ??
          targetTenantId
        }
        platformConfig={platformConfig ?? null}
        tenantConfig={tenantConfig ?? null}
        isPending={
          updatePlatformConfigMut.isPending || updateTenantConfigMut.isPending
        }
        onClose={() => setConfigOpen(false)}
        onSubmit={handleConfigSubmit}
      />
    </div>
  );
}
