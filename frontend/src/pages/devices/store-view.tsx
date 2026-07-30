/**
 * devices/ StoreView — within-tenant device CRUD surface.
 *
 * 从原 1083 行 devices-page.tsx 抽出(plan-devices-page-split.md),镜像
 * ``bookings/store-view.tsx``。Pure locality move: zero behaviour change.
 *
 * StoreView (devices-crud-ui slice 06) is the within-tenant CRUD surface — a
 * device list with create / edit / bind-customer / delete gated behind
 * ``hasPermission(me, "devices", act)`` (members only hold ``devices:read`` so
 * the write actions stay hidden).
 *
 * Data feeds (plan-union-cast-split slice 2 fixed the union at the hook layer):
 * - ``useDevices()`` returns ``Device[]`` natively — no view-boundary cast.
 * - ``DeviceRead`` (store view) carries only ``model_id`` (no ``model_name``),
 *   so the model name is built locally from ``useDeviceModels()``. A device
 *   whose model_id is NOT in the live-models list was bound to a since-soft-
 *   deleted model; the edit dialog renders it read-only/greyed
 *   (plan §3 boundary #1-c).
 *
 * platform-cross-tenant-write slice 04: the four Dialog bodies are lifted to
 * ``device-dialogs.tsx`` so HqView reuses them with ``tenantId`` set. StoreView
 * is a thin caller: it owns the dialog-open state + mutation hooks, and passes
 * ``tenantId={undefined}`` (store path — backend uses ``user.tenant_id``,
 * behaviour unchanged from before slice 04).
 */
import { useMemo, useState } from "react";

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
import type { Device, DeviceCreate, DeviceUpdate } from "@/api/types";
import {
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
import { NONE } from "./device-status-meta";
import {
  DeviceBindDialog,
  DeviceCreateDialog,
  DeviceDeleteDialog,
  DeviceEditDialog,
} from "./device-dialogs";
import { StatusBadge, customerNameOf, type ModelOption } from "./shared";

export function StoreView() {
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

  // useDevices() returns Device[] natively now (plan-union-cast-split slice 2),
  // so no view-boundary cast.
  const list = devices ?? [];

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
