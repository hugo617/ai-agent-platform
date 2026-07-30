/**
 * devices/ HqView — cross-tenant device panorama (super_admin / hq_staff).
 *
 * 从原 1083 行 devices-page.tsx 抽出(plan-devices-page-split.md),镜像
 * ``bookings/hq-view.tsx``。Pure locality move: zero behaviour change.
 *
 * Cross-tenant view, lifted from read-only to write-capable in
 * platform-cross-tenant-write slice 04. The HQ endpoint
 * (GET /devices/ behind require_cross_tenant_viewer) already expands
 * tenant_name/model_name/customer_name server-side. A「目标门店」picker gates
 * all write actions (AC9).
 *
 * tenantId 跨租户写传递机制(platform-cross-tenant-write 的核心 adapter,
 * 原样保留 —— 是本拆分的安全重点,plan §9 高风险项):
 * - **Create/Edit 的 tenantId prop 路径**:`DeviceCreateDialog` / `DeviceEditDialog`
 *   通过 ``tenantId`` prop 区分。HqView 传 ``targetTenantId || undefined`` →
 *   payload 带 ``tenant_id`` body 字段。StoreView 传 ``undefined``(payload 省略)。
 * - **Bind/Delete 的 hook closure 路径**:`DeviceBindDialog` / `DeviceDeleteDialog`
 *   无 ``tenantId`` prop。HqView 调 ``useBindDeviceCustomer(targetTenantId)`` /
 *   ``useDeleteDevice(targetTenantId)``,targetTenantId 闭包绑定进 hook(query
 *   param 传递)。StoreView 调这些 hook 不带参数(store path)。
 *
 * Data feed (plan-union-cast-split slice 2 fixed the union at the hook layer):
 * ``useDevicesAll()`` returns ``DeviceHqRead[]`` natively — no view-boundary
 * cast. The store-scoped ``useDevices`` returns ``Device[]`` (wrong shape here).
 */
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  Link2,
  Monitor,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import type { DeviceCreate, DeviceHqRead, DeviceUpdate, Tenant } from "@/api/types";
import {
  qk,
  useAllTenants,
  useBindDeviceCustomer,
  useCreateDevice,
  useDeleteDevice,
  useDeviceModels,
  useDevicesAll,
  useUnbindDeviceCustomer,
  useUpdateDevice,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import { NONE } from "./device-status-meta";
import {
  DeviceBindDialog,
  DeviceCreateDialog,
  DeviceDeleteDialog,
  DeviceEditDialog,
} from "./device-dialogs";
import { StatusBadge, type ModelOption } from "./shared";

export function HqView() {
  const toast = useToast();
  const qc = useQueryClient();
  // HQ viewers get DeviceHqRead[] from useDevicesAll (the HQ-panorama variant;
  // the union is fixed at the hook layer, plan-union-cast-split slice 2). The
  // store-scoped useDevices returns Device[] — wrong shape for this panorama.
  const { data: devices, isLoading } = useDevicesAll();
  const { data: models } = useDeviceModels();
  const { data: tenants } = useAllTenants();
  // useDevicesAll() returns DeviceHqRead[] natively, so no view-boundary cast.
  // The list itself is cross-tenant (shows every store); we use
  // ``targetDevices`` (filtered client-side to the selected target) for the
  // create dialog's model picker so the operator sees the target store's
  // serial namespace. (No new endpoint — reusing the cross-store feed +
  // filtering is the natural fit.)
  const list = devices ?? [];

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
