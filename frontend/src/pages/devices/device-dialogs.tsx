/**
 * devices/ device-dialogs.tsx — 4 共享 Dialog bodies(platform-cross-tenant-write
 * slice 04 抽出)。
 *
 * 从原 1083 行 devices-page.tsx 抽出(plan-devices-page-split.md),对应
 * ``bookings/shared-dialog.tsx``。StoreView 与 HqView 双视图复用同一组
 * Dialog,通过参数区分租户写路径。
 *
 * Lifted to module-level functions so both StoreView and HqView reuse them.
 * Each Dialog owns its form state (reset on open via useEffect); ``onSubmit``
 * is the parent's mutation + toast + close-on-success wrapper.
 *
 * tenantId 机制(platform-cross-tenant-write 的核心 adapter,原样保留):
 * - ``DeviceCreateDialog`` / ``DeviceEditDialog`` 有 ``tenantId`` prop。
 *   StoreView 传 ``undefined`` → payload 省略 tenant_id 字段 → 后端用
 *   ``user.tenant_id``(store path, 零行为变化);HqView 传目标 id →
 *   payload 带 tenant_id(平台代写)。
 * - ``DeviceBindDialog`` / ``DeviceDeleteDialog`` 无 ``tenantId`` prop。
 *   它们的跨租户写靠 hook closure 机制:HqView 调
 *   ``useBindDeviceCustomer(targetTenantId)`` / ``useDeleteDevice(targetTenantId)``,
 *   targetTenantId 闭包绑定进 hook(非 Dialog prop)。
 *
 * Pure locality move: zero behaviour change.
 */
import { useEffect, useState } from "react";

import { Link2Off, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FormField as Field } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  CustomerProfileRead,
  Device,
  DeviceCreate,
  DeviceStatus,
  DeviceUpdate,
} from "@/api/types";
import { NONE } from "./device-status-meta";
import { StatusSelect, type ModelOption } from "./shared";

export function DeviceCreateDialog({
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

export function DeviceEditDialog({
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

export function DeviceBindDialog({
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

export function DeviceDeleteDialog({
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
