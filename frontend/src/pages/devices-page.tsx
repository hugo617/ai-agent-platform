/**
 * Devices page — devices-crud-ui 系列 2/4(切片 06 StoreView + 切片 07 HqView)。
 *
 * Top-level branch: ``isSuperAdmin(me) || isHQStaff(me) ? <HqView/> :
 * <StoreView/>``. StoreView is the within-tenant CRUD surface (slice 06);
 * HqView is the cross-tenant panorama (slice 07) — lifted from read-only to
 * write-capable in platform-cross-tenant-write slice 04 (target tenant picker
 * + row write actions + shared Dialog bodies). Both consume the same
 * ``useDevices()`` hook — the backend ``GET /devices/`` branches on
 * ``platform_role`` and returns ``Device[]`` (store) or ``DeviceHqRead[]``
 * (HQ, with tenant_name/model_name/customer_name pre-expanded server-side).
 *
 * Backend guard notes (see plan-devices-crud-ui.md):
 * - ``DeviceRead`` (store view) carries only ``model_id`` — no ``model_name``.
 *   We build the name locally from ``useDeviceModels()``. A device whose
 *   model_id is NOT in the live-models list was bound to a since-soft-deleted
 *   model; the edit dialog renders it read-only/greyed (plan §3 boundary #1-c).
 * - ``DeviceHqRead`` (HQ view) pre-expands the three display names so the
 *   panorama table renders without N client-side lookups or a models/tenants
 *   feed — the HQ endpoint joins them server-side.
 * - bind/unbind are dedicated sub-resource endpoints (POST/DELETE
 *   /devices/{id}/bind); customer_id is intentionally NOT part of DeviceUpdate.
 *
 * platform-cross-tenant-write slice 04:
 * - Shared Dialog bodies (DeviceCreateDialog / EditDialog / BindDialog /
 *   DeleteDialog) are lifted to module-level functions so HqView reuses them
 *   with ``tenantId`` set. StoreView passes ``tenantId={undefined}`` (store
 *   path, zero behaviour change — backend uses user.tenant_id).
 * - HqView adds a「目标门店」picker + row DropdownMenu; target selection is
 *   required before any write (AC9). customer_id in the bind dialog degrades
 *   to a free-text global-id input when ``profiles`` is empty (HQ path —
 *   plan §4.5.5 D2-ii).
 */
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  Link2,
  Link2Off,
  Monitor,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
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
import { hasPermission, isHQStaff, isSuperAdmin } from "@/lib/permission";
import type {
  CustomerProfileRead,
  Device,
  DeviceCreate,
  DeviceHqRead,
  DeviceStatus,
  DeviceUpdate,
  Tenant,
} from "@/api/types";
import {
  qk,
  useAllTenants,
  useBindDeviceCustomer,
  useCreateDevice,
  useCustomerProfiles,
  useDeleteDevice,
  useDeviceModels,
  useDevices,
  useUnbindDeviceCustomer,
  useUpdateDevice,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

// active → 运行中 / maintenance → 维护中 / retired → 已退役. Mirrors the
// backend DeviceStatus Literal. Drives the status Badge colour (dot-* variants)
// and the Select options in create/edit dialogs.
const STATUS_OPTIONS: DeviceStatus[] = ["active", "maintenance", "retired"];
const STATUS_META: Record<DeviceStatus, { label: string; badge: "success" | "warning" | "destructive" }> = {
  active: { label: "运行中", badge: "success" },
  maintenance: { label: "维护中", badge: "warning" },
  retired: { label: "已退役", badge: "destructive" },
};

// SelectValue can't render an empty string; "_none" is the sentinel for the
// "no customer bound" option in the bind dialog (mirrors chat-page.tsx:685-707).
const NONE = "_none";

// Forward declaration of the DeviceModelRead-like shape used by the model
// dropdown. useDeviceModels returns DeviceModelPublic[] | DeviceModelRead[]
// depending on platform_role; both have at least {id, name}, so we narrow to
// that minimal pick for the dropdown.
type ModelOption = { id: string; name: string };

export function DevicesPage() {
  const { me } = useAuth();
  // super_admin and hq_staff see the cross-tenant panorama; everyone else
  // (store owner/admin/member) lands on the within-tenant StoreView. The HQ
  // backend guard mirrors this branch (require_cross_tenant_viewer), so both
  // roles get DeviceHqRead[] from the same endpoint.
  return isSuperAdmin(me) || isHQStaff(me) ? <HqView /> : <StoreView />;
}

// ============================================================ store view
function StoreView() {
  const toast = useToast();
  const { me } = useAuth();

  const { data: devices, isLoading } = useDevices();
  const { data: models } = useDeviceModels();

  // Store path: no tenantId → backend uses user.tenant_id (zero behaviour
  // change from before slice 04). The hooks are constructed once and reused
  // across all four dialogs.
  const createMut = useCreateDevice();
  const updateMut = useUpdateDevice();
  const deleteMut = useDeleteDevice();
  const bindMut = useBindDeviceCustomer();
  const unbindMut = useUnbindDeviceCustomer();

  // model_id → live model. Built once per render from the (small) models list;
  // used to resolve the device's model name and to detect soft-deleted models.
  const modelMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const model of (models ?? []) as ModelOption[]) m.set(model.id, model.name);
    return m;
  }, [models]);

  // ---------- dialog state ----------
  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);
  // Edit dialog
  const [editTarget, setEditTarget] = useState<Device | null>(null);
  // Bind dialog
  const [bindTarget, setBindTarget] = useState<Device | null>(null);
  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null);

  // Customer profiles feed the bind dialog's dropdown (useCustomerProfiles is
  // enabled for store users; HQ viewers never reach this view).
  const { data: profiles } = useCustomerProfiles();

  // Button-level guards. super_admin bypasses (hasPermission returns true);
  // members only hold devices:read so the write actions stay hidden.
  const canCreate = hasPermission(me, "devices", "create");
  const canUpdate = hasPermission(me, "devices", "update");
  const canDelete = hasPermission(me, "devices", "delete");

  const list = (devices ?? []) as Device[];

  // ---------- dialog submit handlers ----------
  // Each handler runs the mutation + surfaces the success/error toast +
  // closes the Dialog on success. The shared Dialog bodies own their form
  // state; they call onSubmit and let the promise reject propagate.
  const handleCreate = async (payload: DeviceCreate) => {
    try {
      await createMut.mutateAsync(payload);
      toast.success("设备已入库", payload.serial_number);
      setCreateOpen(false);
    } catch (err) {
      toast.error("入库失败", apiErrorMessage(err));
    }
  };
  const handleEdit = async (id: string, payload: DeviceUpdate) => {
    try {
      await updateMut.mutateAsync({ id, payload });
      toast.success("已更新设备", payload.serial_number ?? "");
      setEditTarget(null);
    } catch (err) {
      toast.error("更新失败", apiErrorMessage(err));
    }
  };
  const handleBind = async (deviceId: string, customerId: string) => {
    try {
      await bindMut.mutateAsync({ deviceId, customerId });
      toast.success(
        customerId === NONE ? "已解绑客户" : "已绑定客户",
        bindTarget?.serial_number ?? "",
      );
      setBindTarget(null);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };
  const handleUnbind = async (deviceId: string) => {
    try {
      await unbindMut.mutateAsync(deviceId);
      toast.success("已解绑客户", bindTarget?.serial_number ?? "");
      setBindTarget(null);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };
  const handleDelete = async (id: string) => {
    try {
      await deleteMut.mutateAsync(id);
      toast.success("已删除设备", deleteTarget?.serial_number ?? "");
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="设备"
        subtitle="管理本店设备实例：入库、状态切换、绑定客户与软删除。"
        actions={
          canCreate && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> 设备入库
            </Button>
          )
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>设备列表</CardTitle>
          <CardDescription>
            共 {list.length} 台设备
            {!canCreate && "（只读视图）"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            loadingVariant="skeleton"
            skeletonRows={6}
            emptyContent={
              <EmptyState
                icon={Monitor}
                title="暂无设备"
                description={
                  canCreate ? "点击右上角「设备入库」" : "本店暂无设备实例"
                }
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>序列号</TableHead>
                  <TableHead>型号</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>绑定客户</TableHead>
                  <TableHead>创建时间</TableHead>
                  {canUpdate && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((d) => {
                  const modelName = modelMap.get(d.model_id);
                  const modelDeleted = !modelName; // bound to a soft-deleted model
                  return (
                    <TableRow key={d.id}>
                      <TableCell className="font-medium">
                        {d.serial_number}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {modelDeleted ? (
                          <span className="text-destructive">
                            型号已删除
                          </span>
                        ) : (
                          modelName
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={d.status} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {customerNameOf(d.customer_id, profiles ?? [])}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {fmt(d.created_at)}
                      </TableCell>
                      {canUpdate && (
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setEditTarget(d)}>
                                <Pencil className="mr-2 h-4 w-4" /> 编辑
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => setBindTarget(d)}>
                                <Link2 className="mr-2 h-4 w-4" />
                                {d.customer_id ? "更换/解绑客户" : "绑定客户"}
                              </DropdownMenuItem>
                              {canDelete && (
                                <>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem
                                    className="text-destructive focus:text-destructive"
                                    onClick={() => setDeleteTarget(d)}
                                  >
                                    <Trash2 className="mr-2 h-4 w-4" /> 删除设备
                                  </DropdownMenuItem>
                                </>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
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

      {/* ---------------- shared Dialogs (platform-cross-tenant-write 切片 04 抽出) ---------------- */}
      {/* Store path: tenantId undefined → backend uses user.tenant_id. */}
      <DeviceCreateDialog
        open={createOpen}
        models={(models ?? []) as ModelOption[]}
        tenantId={undefined}
        isPending={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />
      <DeviceEditDialog
        target={editTarget}
        modelName={editTarget ? modelMap.get(editTarget.model_id) : undefined}
        tenantId={undefined}
        isPending={updateMut.isPending}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEdit}
      />
      <DeviceBindDialog
        target={bindTarget}
        profiles={profiles ?? []}
        isPending={bindMut.isPending || unbindMut.isPending}
        onClose={() => setBindTarget(null)}
        onSubmit={(deviceId, customerId) =>
          customerId === NONE
            ? handleUnbind(deviceId)
            : handleBind(deviceId, customerId)
        }
      />
      <DeviceDeleteDialog
        target={deleteTarget}
        isPending={deleteMut.isPending}
        onClose={() => setDeleteTarget(null)}
        onSubmit={handleDelete}
      />
    </div>
  );
}

// ============================================================ HQ panorama view
// Cross-tenant view (super_admin / hq_staff), lifted from read-only to write-
// capable in platform-cross-tenant-write slice 04. The HQ endpoint
// (GET /devices/ behind require_cross_tenant_viewer) already expands
// tenant_name/model_name/customer_name server-side. A「目标门店」picker gates
// all write actions (AC9); the same shared Dialog bodies are reused with
// ``tenantId`` set (plan §4.5.4a 补丁 1).
function HqView() {
  const toast = useToast();
  const qc = useQueryClient();
  const { data: devices, isLoading } = useDevices();
  const { data: models } = useDeviceModels();
  const { data: tenants } = useAllTenants();
  // HQ viewers get DeviceHqRead[] from useDevices. The list itself is cross-
  // tenant (shows every store); we use ``targetDevices`` (filtered client-side
  // to the selected target) for the create dialog's model picker so the
  // operator sees the target store's serial namespace. (No new endpoint —
  // reusing the cross-store feed + filtering is the natural fit.)
  const list = (devices ?? []) as DeviceHqRead[];

  // ---------- target tenant picker ----------
  // Required before any write (AC9). Sourced from GET /tenants/all.
  const [targetTenantId, setTargetTenantId] = useState<string>("");

  // Switching target invalidates the devices query (AC7). The cross-tenant
  // list itself is unaffected (its data is the same regardless of target);
  // this is belt-and-braces for any scoped feed a future change might add.
  const onTargetChange = (id: string) => {
    setTargetTenantId(id);
    qc.invalidateQueries({ queryKey: qk.devices });
  };

  // ---------- write hooks (closure-bound to the selected target) ----------
  // Constructed once per render with ``targetTenantId``; same ``mutateAsync``
  // call site as StoreView transparently carries the target. Undefined target
  // (no selection) → backend 400s on "platform writer must specify target"
  // (plan §4.5.4a 补丁 1). Inert in that state because the menu is hidden.
  const createMut = useCreateDevice();
  const updateMut = useUpdateDevice();
  const deleteMut = useDeleteDevice(targetTenantId || undefined);
  const bindMut = useBindDeviceCustomer(targetTenantId || undefined);
  const unbindMut = useUnbindDeviceCustomer(targetTenantId || undefined);

  // model_id → live model name (DeviceHqRead pre-expands model_name, so we
  // could read ``d.model_name`` directly — but useDeviceModels gives us the
  // live catalogue the create dialog needs).
  const modelMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const model of (models ?? []) as ModelOption[]) m.set(model.id, model.name);
    return m;
  }, [models]);

  // ---------- dialog state ----------
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<DeviceHqRead | null>(null);
  const [bindTarget, setBindTarget] = useState<DeviceHqRead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeviceHqRead | null>(null);

  // ---------- dialog submit handlers ----------
  // Same shape as StoreView's; tenantId is threaded via the closure-bound
  // hooks above for delete/unbind (query param) + via the Dialog ``tenantId``
  // prop for create/update/bind (body field).
  const handleCreate = async (payload: DeviceCreate) => {
    try {
      await createMut.mutateAsync(payload);
      toast.success("设备已入库", payload.serial_number);
      setCreateOpen(false);
    } catch (err) {
      toast.error("入库失败", apiErrorMessage(err));
    }
  };
  const handleEdit = async (id: string, payload: DeviceUpdate) => {
    try {
      await updateMut.mutateAsync({ id, payload });
      toast.success("已更新设备", payload.serial_number ?? "");
      setEditTarget(null);
    } catch (err) {
      toast.error("更新失败", apiErrorMessage(err));
    }
  };
  const handleBind = async (deviceId: string, customerId: string) => {
    try {
      await bindMut.mutateAsync({ deviceId, customerId });
      toast.success(
        customerId === NONE ? "已解绑客户" : "已绑定客户",
        bindTarget?.serial_number ?? "",
      );
      setBindTarget(null);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };
  const handleUnbind = async (deviceId: string) => {
    try {
      await unbindMut.mutateAsync(deviceId);
      toast.success("已解绑客户", bindTarget?.serial_number ?? "");
      setBindTarget(null);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };
  const handleDelete = async (id: string) => {
    try {
      await deleteMut.mutateAsync(id);
      toast.success("已删除设备", deleteTarget?.serial_number ?? "");
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  const canWrite = !!targetTenantId;

  return (
    <div className="space-y-6">
      <PageHeader
        title="设备（总部视图）"
        subtitle="跨店聚合：查看所有门店的设备实例，并选定目标门店代为入库/编辑/删除/绑定客户。"
        actions={
          canWrite && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> 设备入库
            </Button>
          )
        }
      />

      <Card>
        <CardHeader className="space-y-4">
          <div>
            <CardTitle>全局设备列表</CardTitle>
            <CardDescription>
              共 {list.length} 台设备（跨全部门店）
              {canWrite ? "" : " — 请先选择目标门店才能代为操作"}
            </CardDescription>
          </div>
          {/* Target tenant picker. Required before any write (AC9). */}
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">目标门店：</span>
            <Select value={targetTenantId} onValueChange={onTargetChange}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="选择目标门店" />
              </SelectTrigger>
              <SelectContent>
                {(tenants ?? []).map((t: Tenant) => (
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
                icon={Monitor}
                title="暂无设备"
                description="跨全部门店暂无设备实例"
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>所属门店</TableHead>
                  <TableHead>序列号</TableHead>
                  <TableHead>型号</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>绑定客户</TableHead>
                  <TableHead>创建时间</TableHead>
                  {canWrite && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="text-muted-foreground">
                      {/* tenant_name is null only if the tenant row was hard-
                          deleted — the FK is CASCADE so this is effectively
                          unreachable, but we guard for display safety. */}
                      {d.tenant_name ?? "（门店已删除）"}
                    </TableCell>
                    <TableCell className="font-medium">
                      {d.serial_number}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {d.model_name ?? (
                        <span className="text-destructive">型号已删除</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={d.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {d.customer_name ?? "-"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(d.created_at)}
                    </TableCell>
                    {canWrite && (
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => setEditTarget(d)}>
                              <Pencil className="mr-2 h-4 w-4" /> 编辑
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setBindTarget(d)}>
                              <Link2 className="mr-2 h-4 w-4" />
                              {d.customer_id ? "更换/解绑客户" : "绑定客户"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteTarget(d)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> 删除设备
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      {/* ---------------- shared Dialogs (reused from StoreView) ---------------- */}
      {/* HQ path: tenantId = selected target (closure on the picked store);
          profiles = [] (D2-ii: HQ can't see the target store's customer list
          — the bind dialog's customer field degrades to a free-text input). */}
      <DeviceCreateDialog
        open={createOpen}
        models={(models ?? []) as ModelOption[]}
        tenantId={targetTenantId || undefined}
        isPending={createMut.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />
      <DeviceEditDialog
        target={editTarget}
        modelName={editTarget ? editTarget.model_name ?? modelMap.get(editTarget.model_id) : undefined}
        tenantId={targetTenantId || undefined}
        isPending={updateMut.isPending}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEdit}
      />
      <DeviceBindDialog
        target={bindTarget}
        profiles={[]}
        isPending={bindMut.isPending || unbindMut.isPending}
        onClose={() => setBindTarget(null)}
        onSubmit={(deviceId, customerId) =>
          customerId === NONE
            ? handleUnbind(deviceId)
            : handleBind(deviceId, customerId)
        }
      />
      <DeviceDeleteDialog
        target={deleteTarget}
        isPending={deleteMut.isPending}
        onClose={() => setDeleteTarget(null)}
        onSubmit={handleDelete}
      />
    </div>
  );
}

// ============================================================ shared Dialog bodies
//
// Lifted to module-level functions (platform-cross-tenant-write slice 04) so
// both StoreView and HqView reuse them. Each Dialog owns its form state
// (reset on open via useEffect); ``onSubmit`` is the parent's mutation +
// toast + close-on-success wrapper. ``tenantId`` threads into the create/
// update/bind payloads — undefined (store path) omits the field → backend
// uses user.tenant_id; a real id (HQ path) carries the target store.

function DeviceCreateDialog({
  open,
  models,
  tenantId,
  isPending,
  onClose,
  onSubmit,
}: {
  open: boolean;
  models: ModelOption[];
  tenantId?: string;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (payload: DeviceCreate) => Promise<void>;
}) {
  const [model, setModel] = useState("");
  const [serial, setSerial] = useState("");
  const [status, setStatus] = useState<DeviceStatus>("active");
  const [missing, setMissing] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setModel("");
      setSerial("");
      setStatus("active");
      setMissing(null);
    }
  }, [open]);

  const submit = async () => {
    if (!model) {
      setMissing("请选择设备型号");
      return;
    }
    if (!serial.trim()) {
      setMissing("请填写序列号");
      return;
    }
    setMissing(null);
    const payload: DeviceCreate = {
      model_id: model,
      serial_number: serial.trim(),
      status,
      ...(tenantId ? { tenant_id: tenantId } : {}),
    };
    await onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>设备入库</DialogTitle>
          <DialogDescription>
            选择活型号、填写序列号并设置初始状态。序列号在目标门店内不可重复。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="设备型号 *" error={missing && !model ? missing : undefined}>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger>
                <SelectValue placeholder="选择设备型号" />
              </SelectTrigger>
              <SelectContent>
                {models.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field
            label="序列号 *"
            error={missing && model && !serial.trim() ? missing : undefined}
          >
            <Input
              value={serial}
              onChange={(e) => setSerial(e.target.value)}
              placeholder="如：SN-2026-0001"
            />
          </Field>
          <Field label="初始状态">
            <StatusSelect value={status} onValueChange={setStatus} />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={isPending}>
            入库
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeviceEditDialog({
  target,
  modelName,
  tenantId,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Device | null;
  modelName: string | undefined;
  tenantId?: string;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (id: string, payload: DeviceUpdate) => Promise<void>;
}) {
  const [serial, setSerial] = useState("");
  const [status, setStatus] = useState<DeviceStatus>("active");
  const [missing, setMissing] = useState<string | null>(null);

  useEffect(() => {
    if (target) {
      setSerial(target.serial_number);
      setStatus(target.status);
      setMissing(null);
    }
  }, [target]);

  const submit = async () => {
    if (!target) return;
    if (!serial.trim()) {
      setMissing("请填写序列号");
      return;
    }
    setMissing(null);
    const payload: DeviceUpdate = {
      serial_number: serial.trim(),
      status,
      ...(tenantId ? { tenant_id: tenantId } : {}),
    };
    await onSubmit(target.id, payload);
  };

  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>编辑设备</DialogTitle>
          <DialogDescription>
            修改序列号与运行状态。型号为设备身份，不可在此变更。
          </DialogDescription>
        </DialogHeader>
        {target && (
          <div className="space-y-4">
            {/* model_id is read-only: changing it is semantically "swap the
                device", which should go through delete + recreate (plan
                §前端实施-4 edit-dialog bullet lists serial+status+customer,
                NOT model_id). If the bound model was soft-deleted, its id is
                the only handle we have — show it greyed. */}
            {modelName ? (
              <Field label="型号(不可修改)">
                <Input value={modelName} disabled />
              </Field>
            ) : (
              <Field
                label="型号(不可修改)"
                error="该型号已被软删除，仅作展示"
              >
                <Input
                  value={`型号已删除(${target.model_id.slice(0, 8)})`}
                  disabled
                  className="text-muted-foreground"
                />
              </Field>
            )}
            <Field label="序列号 *" error={missing ?? undefined}>
              <Input
                value={serial}
                onChange={(e) => setSerial(e.target.value)}
              />
            </Field>
            <Field label="状态">
              <StatusSelect value={status} onValueChange={setStatus} />
            </Field>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={isPending}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeviceBindDialog({
  target,
  profiles,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Device | null;
  profiles: CustomerProfileRead[];
  isPending: boolean;
  onClose: () => void;
  onSubmit: (deviceId: string, customerId: string) => Promise<void>;
}) {
  const [customerId, setCustomerId] = useState<string>(NONE);

  useEffect(() => {
    if (target) {
      // Pre-select the current binding so re-confirming is a no-op (the
      // backend returns already_bound:true, 200). An unbound device opens on
      // "_none".
      setCustomerId(target.customer_id ?? NONE);
    }
  }, [target]);

  const submit = async () => {
    if (!target) return;
    await onSubmit(target.id, customerId);
  };

  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>绑定客户</DialogTitle>
          <DialogDescription>
            {target
              ? `为设备「${target.serial_number}」选择关联客户。选择「不绑定」将解除当前绑定。`
              : ""}
          </DialogDescription>
        </DialogHeader>
        <Field label="关联客户">
          {profiles.length === 0 ? (
            // HQ path: free-text global customer id (D2-ii). NONE sentinel
            // ("_none") is the empty / unbind value.
            <Input
              value={customerId === NONE ? "" : customerId}
              onChange={(e) => setCustomerId(e.target.value.trim() || NONE)}
              placeholder="如 cust_xxx(留空 = 不绑定)"
            />
          ) : (
            <Select value={customerId} onValueChange={setCustomerId}>
              <SelectTrigger>
                <SelectValue placeholder="选择客户(可选)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>不绑定</SelectItem>
                {profiles.map((p) => (
                  <SelectItem key={p.customer_id} value={p.customer_id}>
                    {p.customer.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={submit}
            // Grey the button while a request is in flight, or when the
            // operator picked "不绑定" on an already-unbound device (a pure
            // no-op — submitting would just close the dialog).
            disabled={
              isPending ||
              (!!target && customerId === NONE && !target.customer_id)
            }
          >
            {customerId === NONE ? (
              <>
                <Link2Off className="mr-2 h-4 w-4" /> 解绑
              </>
            ) : (
              "保存"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeviceDeleteDialog({
  target,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Device | null;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (id: string) => Promise<void>;
}) {
  const submit = async () => {
    if (!target) return;
    await onSubmit(target.id);
  };
  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认删除设备</DialogTitle>
          <DialogDescription>
            确定删除设备「{target?.serial_number}」？
            该操作为软删除，序列号可被新设备重新使用。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button variant="destructive" onClick={submit} disabled={isPending}>
            <Trash2 className="mr-2 h-4 w-4" /> 删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------- shared bits ----------------

/** Three-state status Select shared by the create + edit dialogs (extracted to
 * avoid duplicating the STATUS_OPTIONS mapping in two places). */
function StatusSelect({
  value,
  onValueChange,
}: {
  value: DeviceStatus;
  onValueChange: (v: DeviceStatus) => void;
}) {
  return (
    <Select value={value} onValueChange={(v) => onValueChange(v as DeviceStatus)}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {STATUS_OPTIONS.map((s) => (
          <SelectItem key={s} value={s}>
            {STATUS_META[s].label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function StatusBadge({ status }: { status: DeviceStatus }) {
  const meta = STATUS_META[status];
  return <Badge variant={`dot-${meta.badge}`}>{meta.label}</Badge>;
}

/** Resolve a device's customer_id to a display name from the profiles list.
 * Returns "-" when unbound (or when the profiles list hasn't loaded yet and
 * the id is non-null — a rare transient state that resolves on next render). */
function customerNameOf(
  customerId: string | null,
  profiles: CustomerProfileRead[] | undefined,
): string {
  if (!customerId) return "-";
  const hit = profiles?.find((p) => p.customer_id === customerId);
  return hit?.customer.name ?? "—";
}
