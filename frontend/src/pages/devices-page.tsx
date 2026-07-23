/**
 * Devices page — slice 06 StoreView (devices-crud-ui 系列 2/4).
 *
 * Store owners/admins manage their tenant's device instances here: list,
 * onboard (create), edit status, bind/unbind a customer, and soft-delete.
 * Members are read-only (write buttons hidden by ``hasPermission``).
 *
 * The top-level branch is ``isSuperAdmin(me) || isHQStaff(me) ? <HqView/> :
 * <StoreView/>``. The HqView lands in slice 07 — this slice ships only the
 * StoreView, with the branch stubbed so the route keeps working. Slice 05
 * already wired the data hooks (useDevices / useDeviceModels / bind-unbind
 * family) and types; this file just consumes them.
 *
 * Backend guard notes (see plan-devices-crud-ui.md):
 * - ``DeviceRead`` (store view) carries only ``model_id`` — no ``model_name``.
 *   We build the name locally from ``useDeviceModels()``. A device whose
 *   model_id is NOT in the live-models list was bound to a since-soft-deleted
 *   model; the edit dialog renders it read-only/greyed (plan §3 boundary #1-c).
 * - bind/unbind are dedicated sub-resource endpoints (POST/DELETE
 *   /devices/{id}/bind); customer_id is intentionally NOT part of DeviceUpdate.
 */
import { useMemo, useState } from "react";

import {
  Cpu,
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
  DeviceStatus,
  DeviceUpdate,
} from "@/api/types";
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

export function DevicesPage() {
  const { me } = useAuth();
  // HQ panorama (super_admin / hq_staff) lands in slice 07. Until then, HQ
  // viewers still need a reachable route, so we fall back to a read-only
  // note. The branch shape (isSuperAdmin || isHQStaff) is final — slice 07
  // only swaps this placeholder for <HqView/>.
  return isSuperAdmin(me) || isHQStaff(me) ? <HqPlaceholder /> : <StoreView />;
}

// ============================================================ store view
function StoreView() {
  const toast = useToast();
  const { me } = useAuth();

  const { data: devices, isLoading } = useDevices();
  const { data: models } = useDeviceModels();

  const createMut = useCreateDevice();
  const updateMut = useUpdateDevice();
  const deleteMut = useDeleteDevice();
  const bindMut = useBindDeviceCustomer();
  const unbindMut = useUnbindDeviceCustomer();

  // model_id → live model. Built once per render from the (small) models list;
  // used to resolve the device's model name and to detect soft-deleted models.
  const modelMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const model of models ?? []) m.set(model.id, model.name);
    return m;
  }, [models]);

  // ---------- dialog state ----------
  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [createModel, setCreateModel] = useState("");
  const [createSerial, setCreateSerial] = useState("");
  const [createStatus, setCreateStatus] = useState<DeviceStatus>("active");
  // Edit dialog
  const [editTarget, setEditTarget] = useState<Device | null>(null);
  const [editSerial, setEditSerial] = useState("");
  const [editStatus, setEditStatus] = useState<DeviceStatus>("active");
  // Bind dialog
  const [bindTarget, setBindTarget] = useState<Device | null>(null);
  const [bindCustomerId, setBindCustomerId] = useState<string>(NONE);
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

  const list = devices ?? [];

  // ---------- create ----------
  const openCreate = () => {
    setCreateModel("");
    setCreateSerial("");
    setCreateStatus("active");
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    if (!createModel) {
      toast.error("请选择设备型号");
      return;
    }
    if (!createSerial.trim()) {
      toast.error("请填写序列号");
      return;
    }
    const payload: DeviceCreate = {
      model_id: createModel,
      serial_number: createSerial.trim(),
      status: createStatus,
    };
    try {
      await createMut.mutateAsync(payload);
      toast.success("设备已入库", createSerial.trim());
      setCreateOpen(false);
    } catch (err) {
      toast.error("入库失败", apiErrorMessage(err));
    }
  };

  // ---------- edit ----------
  const openEdit = (d: Device) => {
    setEditTarget(d);
    setEditSerial(d.serial_number);
    setEditStatus(d.status);
  };

  const submitEdit = async () => {
    if (!editTarget) return;
    if (!editSerial.trim()) {
      toast.error("请填写序列号");
      return;
    }
    const payload: DeviceUpdate = {
      serial_number: editSerial.trim(),
      status: editStatus,
    };
    try {
      await updateMut.mutateAsync({ id: editTarget.id, payload });
      toast.success("已更新设备", editSerial.trim());
      setEditTarget(null);
    } catch (err) {
      toast.error("更新失败", apiErrorMessage(err));
    }
  };

  // ---------- bind / unbind ----------
  const openBind = (d: Device) => {
    setBindTarget(d);
    // Pre-select the current binding so re-confirming is a no-op (the backend
    // returns already_bound:true, 200). An unbound device opens on "_none".
    setBindCustomerId(d.customer_id ?? NONE);
  };

  const submitBind = async () => {
    if (!bindTarget) return;
    // "_none" → unbind (DELETE /devices/{id}/bind, idempotent 204 even if the
    // device was already unbound). Any real id → bind (POST, 200 + already_bound).
    try {
      if (bindCustomerId === NONE) {
        await unbindMut.mutateAsync(bindTarget.id);
        toast.success("已解绑客户", bindTarget.serial_number);
      } else {
        await bindMut.mutateAsync({
          deviceId: bindTarget.id,
          customerId: bindCustomerId,
        });
        toast.success("已绑定客户", bindTarget.serial_number);
      }
      setBindTarget(null);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };

  // ---------- delete ----------
  const submitDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMut.mutateAsync(deleteTarget.id);
      toast.success("已删除设备", deleteTarget.serial_number);
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
            <Button onClick={openCreate}>
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
                              <DropdownMenuItem onClick={() => openEdit(d)}>
                                <Pencil className="mr-2 h-4 w-4" /> 编辑
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => openBind(d)}>
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

      {/* ---------------- create dialog ---------------- */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>设备入库</DialogTitle>
            <DialogDescription>
              选择活型号、填写序列号并设置初始状态。序列号在本店内不可重复。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Field label="设备型号 *">
              <Select value={createModel} onValueChange={setCreateModel}>
                <SelectTrigger>
                  <SelectValue placeholder="选择设备型号" />
                </SelectTrigger>
                <SelectContent>
                  {(models ?? []).map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="序列号 *">
              <Input
                value={createSerial}
                onChange={(e) => setCreateSerial(e.target.value)}
                placeholder="如：SN-2026-0001"
              />
            </Field>
            <Field label="初始状态">
              <StatusSelect
                value={createStatus}
                onValueChange={setCreateStatus}
              />
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button onClick={submitCreate} disabled={createMut.isPending}>
              入库
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------------- edit dialog ---------------- */}
      <Dialog
        open={!!editTarget}
        onOpenChange={(o) => !o && setEditTarget(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑设备</DialogTitle>
            <DialogDescription>
              修改序列号与运行状态。型号为设备身份，不可在此变更。
            </DialogDescription>
          </DialogHeader>
          {editTarget && (
            <div className="space-y-4">
              {/* model_id is read-only: changing it is semantically "swap the
                  device", which should go through delete + recreate (plan
                  §前端实施-4 edit-dialog bullet lists serial+status+customer,
                  NOT model_id). If the bound model was soft-deleted, its id is
                  the only handle we have — DeviceRead has no model_name and the
                  live-models endpoint filters soft-deleted rows out, so we show
                  the id greyed (plan §3 #1-c: read-only, can't switch to a
                  soft-deleted model). */}
              {(() => {
                const modelName = modelMap.get(editTarget.model_id);
                return modelName ? (
                  <Field label="型号(不可修改)">
                    <Input value={modelName} disabled />
                  </Field>
                ) : (
                  <Field
                    label="型号(不可修改)"
                    error="该型号已被软删除，仅作展示"
                  >
                    <Input
                      value={`型号已删除(${editTarget.model_id.slice(0, 8)})`}
                      disabled
                      className="text-muted-foreground"
                    />
                  </Field>
                );
              })()}
              <Field label="序列号 *">
                <Input
                  value={editSerial}
                  onChange={(e) => setEditSerial(e.target.value)}
                />
              </Field>
              <Field label="状态">
                <StatusSelect value={editStatus} onValueChange={setEditStatus} />
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

      {/* ---------------- bind/unbind dialog ---------------- */}
      {/* Inline Select pattern mirrors chat-page.tsx:685-707. "_none" both
          represents "leave unbound" and triggers unbind on submit. */}
      <Dialog
        open={!!bindTarget}
        onOpenChange={(o) => !o && setBindTarget(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>绑定客户</DialogTitle>
            <DialogDescription>
              {bindTarget
                ? `为设备「${bindTarget.serial_number}」选择关联客户。选择「不绑定」将解除当前绑定。`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <Field label="关联客户">
            <Select value={bindCustomerId} onValueChange={setBindCustomerId}>
              <SelectTrigger>
                <SelectValue placeholder="选择客户(可选)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>不绑定</SelectItem>
                {(profiles ?? []).map((p) => (
                  <SelectItem key={p.customer_id} value={p.customer_id}>
                    {p.customer.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBindTarget(null)}>
              取消
            </Button>
            <Button
              onClick={submitBind}
              // Grey the button while a request is in flight, or when the
              // operator picked "不绑定" on an already-unbound device (a pure
              // no-op — submitting would just close the dialog).
              disabled={
                bindMut.isPending ||
                unbindMut.isPending ||
                (!!bindTarget &&
                  bindCustomerId === NONE &&
                  !bindTarget.customer_id)
              }
            >
              {bindCustomerId === NONE ? (
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

      {/* ---------------- delete confirm dialog ---------------- */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除设备</DialogTitle>
            <DialogDescription>
              确定删除设备「{deleteTarget?.serial_number}」？
              该操作为软删除，序列号可被新设备重新使用。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={submitDelete}
              disabled={deleteMut.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" /> 删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ============================================================ HQ placeholder
// Slice 07 replaces this with the real cross-tenant panorama (<HqView/>).
// Kept minimal so the /devices route stays reachable for super_admin / hq_staff
// between slices, and the final branch shape is already in place.
function HqPlaceholder() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Monitor className="h-5 w-5 text-muted-foreground" />
            <CardTitle>设备(总部视图)</CardTitle>
          </div>
          <CardDescription>
            跨租户设备全景视图将在切片 07 上线。当前请切换到门店视角查看本店设备。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
          <Cpu className="h-4 w-4" />
          全景表格建设中。
        </CardContent>
      </Card>
    </div>
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
