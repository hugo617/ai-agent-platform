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
 * The ``as BookingHqRead[]`` cast on the union return of ``useBookings()`` is
 * preserved verbatim — narrowing it (splitting into ``useBookingsHq``) is
 * candidate 8 in the 2026-07-25 architecture review, intentionally out of
 * scope here.
 */
import { useState } from "react";

import { CalendarX, Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

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
  BookingCreate,
  BookingEndPayload,
  BookingHqRead,
  BookingUpdate,
  DeviceHqRead,
} from "@/api/types";
import {
  qk,
  useAllTenants,
  useBookings,
  useCancelBooking,
  useCreateBooking,
  useDevices,
  useEndBooking,
  useNoShowBooking,
  useStartBooking,
  useUpdateBooking,
} from "@/hooks/queries";
import { BookingStatusBadge, fmt } from "./shared";
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
  const { data: bookings, isLoading } = useBookings();
  const { data: tenants } = useAllTenants();
  // HQ viewers get DeviceHqRead[] from useDevices (the same endpoint branches
  // on platform_role). We filter to the selected target so the create dialog's
  // device picker only offers that store's active devices — the dialog would
  // otherwise show an empty dropdown (no target-scoped feed exists; plan
  // §4.5.5 前端 says "复用 StoreView Dialog" — reusing the cross-store feed
  // + filtering client-side is the natural fit, no new endpoint needed).
  const { data: devices } = useDevices();
  const targetDevices = ((devices ?? []) as DeviceHqRead[]).filter(
    (d) => d.tenant_id === targetTenantId && d.status === "active",
  );

  // useBookings() returns a union (Booking[] | BookingHqRead[]). The backend
  // guarantees BookingHqRead[] for HQ roles (the same guard that routes us
  // here), so we narrow once at the view boundary. A store viewer never reaches
  // this component — the top-level BookingsPage branch sees to that.
  //
  // Note(candidate-8): split fetchBookings → fetchBookingsHq to drop this cast.
  const list = (bookings ?? []) as BookingHqRead[];

  // ---------- target tenant picker ----------
  // Platform writers MUST pick a target before any write. Empty = no write
  // controls rendered (AC9). The picker is sourced from useAllTenants
  // (GET /tenants/all, super_admin + hq_staff authorised; plan §4.5.5 前端).
  const [targetTenantId, setTargetTenantId] = useState<string>("");

  // Switching target invalidates the bookings query (AC7). The cross-tenant
  // list itself is unaffected (its data is the same regardless of target);
  // this is belt-and-braces so the panorama refreshes against the latest
  // server state right after a target switch. Cheap (HQ viewers don't render
  // the schedule grid).
  const onTargetChange = (id: string) => {
    setTargetTenantId(id);
    qc.invalidateQueries({ queryKey: qk.bookings });
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
            <Button onClick={() => setCreateOpen(true)}>
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
    </div>
  );
}
