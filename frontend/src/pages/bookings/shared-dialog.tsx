/**
 * bookings/ shared booking Dialog components (platform-cross-tenant-write
 * slice 04).
 *
 * Extracted from store-view.tsx so the HQ panorama view can reuse the same
 * create / edit / cancel / end / no-show dialogs parameterised by a target
 * tenant. StoreView is now a thin caller that wires its own state and the
 * write hooks; HqView adds a「目标门店」picker and reuses the same Dialog
 * bodies with ``tenantId`` set + ``profiles=[]`` (HQ operators can't see the
 * target store's customer list — plan §4.5.5 D2-ii UX trade-off; the customer
 * field degrades to a free-text global-id input when ``profiles`` is empty).
 *
 * Design notes:
 * - Each Dialog owns its own form state. ``open`` + ``target`` are the parent's
 *   only controls — the Dialog resets its inputs from ``target`` via useEffect
 *   when it opens. The parent never has to thread per-field state.
 * - ``onSubmit`` returns a Promise that the parent controls: it runs the
 *   mutation, surfaces the success/error toast, and closes the Dialog. The
 *   Dialog does NOT catch — a rejected promise propagates so the parent's
 *   ``try/catch`` decides whether to close + toast-success or toast-error and
 *   keep the Dialog open. This keeps the Dialog a pure presentational body
 *   (no toast wiring duplicated between store + HQ callers).
 * - ``tenantId`` is threaded into every submit payload. Store callers pass
 *   ``undefined`` → the field is omitted → backend uses ``user.tenant_id``
 *   (store path, zero behaviour change). Platform callers pass the selected
 *   target → the field/query param carries it (plan §4.5.4a 补丁 5).
 * - The customer field is a Select when ``profiles`` is non-empty (store view,
 *   picks from this tenant's profiles) and a free-text Input otherwise (HQ
 *   view, plan §4.5.5 D2-ii: platform writer types a global customer id or
 *   leaves blank for walk-in). The empty-profiles branch is unreachable in
 *   the store path (store callers always have profiles loaded), so the dual
 *   shape stays a clean UX split rather than a runtime branch in store.
 */
import { useEffect, useState } from "react";

import { MoreHorizontal, Plus, Square, UserX, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { FormField as Field } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toDatetimeLocalValue } from "@/lib/format";
import type {
  Booking,
  BookingCreate,
  BookingEndPayload,
  BookingUpdate,
  CustomerProfileRead,
  Device,
} from "@/api/types";
import {
  ACTIONABLE_STATUS,
  MUTABLE_STATUS,
  NONE,
  fromDatetimeLocalValue,
} from "./shared";

// ============================================================ customer field
//
// Dual-shape customer input. ``profiles`` non-empty → Select dropdown (store
// view); empty → free-text global-customer-id Input (HQ view). The choice is
// driven by what the caller passes: StoreView always has profiles, HqView
// always passes ``[]`` (it can't fetch a target store's profiles without
// leaking cross-tenant data — plan §4.5.5 D2-ii).
function CustomerField({
  label,
  value,
  profiles,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  profiles: CustomerProfileRead[];
  onChange: (v: string) => void;
  hint?: string;
}) {
  if (profiles.length === 0) {
    // HQ path: free-text global customer id. NONE sentinel ("_none") is the
    // empty / walk-in value; we prefill it so an untouched field submits as
    // walk-in (matching the store path's default Select option).
    return (
      <Field
        label={label}
        hint={hint ?? "手填客户全局 ID(可选) — 留空 = 散客(walk-in)"}
      >
        <Input
          value={value === NONE ? "" : value}
          onChange={(e) => onChange(e.target.value.trim() || NONE)}
          placeholder="如 cust_xxx(留空 = 散客)"
        />
      </Field>
    );
  }
  return (
    <Field label={label} hint={hint}>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder="选择客户(可选)" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>不指定(散客)</SelectItem>
          {profiles.map((p) => (
            <SelectItem key={p.customer_id} value={p.customer_id}>
              {p.customer.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

// ============================================================ create dialog
export function BookingCreateDialog({
  open,
  devices,
  profiles,
  tenantId,
  isPending,
  onClose,
  onSubmit,
  defaultDeviceId,
  defaultStart,
  defaultEnd,
}: {
  open: boolean;
  devices: Device[];
  profiles: CustomerProfileRead[];
  tenantId?: string;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (payload: BookingCreate) => Promise<void>;
  /** Prefill the device + time window when the Dialog opens (booking-schedule-
   * grid 切片 04b: clicking an empty grid cell opens this Dialog with the
   * clicked device + slot already filled). Undefined on the StoreView path →
   * the Dialog opens blank as before (zero behaviour change for store callers).
   * ``defaultStart`` / ``defaultEnd`` are ISO timestamps (the grid's
   * slotHourToISO output); they're converted to datetime-local values here. */
  defaultDeviceId?: string;
  defaultStart?: string;
  defaultEnd?: string;
}) {
  const [deviceId, setDeviceId] = useState("");
  const [customerId, setCustomerId] = useState<string>(NONE);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [notes, setNotes] = useState("");
  // Local validation error — surfaced inline via toast. Cleared on open.
  const [missing, setMissing] = useState<string | null>(null);

  // Reset the form when the dialog opens. Without this, the inputs would
  // retain stale values from the previous open (React keeps the component
  // mounted across open/close because the parent keeps it in the tree).
  //
  // 切片 04b: when the HQ grid opens this Dialog from a cell click, the parent
  // passes ``defaultDeviceId`` / ``defaultStart`` / ``defaultEnd`` to prefill
  // the clicked slot. StoreView doesn't pass them → the Dialog opens blank
  // (zero behaviour change). The prefill is read on every open, so a fresh
  // cell click while the Dialog is closed-and-reopened picks up the new slot.
  useEffect(() => {
    if (open) {
      setDeviceId(defaultDeviceId ?? "");
      setCustomerId(NONE);
      setStart(defaultStart ? toDatetimeLocalValue(defaultStart) : "");
      setEnd(defaultEnd ? toDatetimeLocalValue(defaultEnd) : "");
      setNotes("");
      setMissing(null);
    }
  }, [open, defaultDeviceId, defaultStart, defaultEnd]);

  const submit = async () => {
    if (!deviceId) {
      setMissing("请选择设备");
      return;
    }
    if (!start || !end) {
      setMissing("请填写预约时段");
      return;
    }
    setMissing(null);
    const payload: BookingCreate = {
      device_id: deviceId,
      customer_id: customerId === NONE ? null : customerId,
      scheduled_start_at: fromDatetimeLocalValue(start),
      scheduled_end_at: fromDatetimeLocalValue(end),
      notes: notes.trim() || null,
      // Omit tenant_id when undefined (store path) so the field is absent
      // from the body — backend then uses user.tenant_id (plan §4.5.4a
      // 补丁 5). Platform writers pass the selected target via tenantId.
      ...(tenantId ? { tenant_id: tenantId } : {}),
    };
    // Intentionally NOT catching: the parent's try/catch decides toast +
    // close-on-success. A rejected promise propagates so the Dialog stays
    // open on failure (the operator can fix + retry).
    await onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>创建预约</DialogTitle>
          <DialogDescription>
            选择设备、可选客户与预约时段。时段冲突由后端校验,提交后如有冲突会提示。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="设备 *" error={missing && !deviceId ? missing : undefined}>
            <Select value={deviceId} onValueChange={setDeviceId}>
              <SelectTrigger>
                <SelectValue placeholder="选择设备" />
              </SelectTrigger>
              <SelectContent>
                {devices
                  .filter((d) => d.status === "active")
                  .map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.serial_number}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </Field>
          <CustomerField
            label="客户"
            value={customerId}
            profiles={profiles}
            onChange={setCustomerId}
            hint={
              profiles.length === 0
                ? undefined
                : "可不选 — 散客(walk-in)预约不绑定客户"
            }
          />
          <Field
            label="预约开始时间 *"
            error={missing && deviceId && (!start || !end) ? missing : undefined}
          >
            <Input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </Field>
          <Field label="预约结束时间 *">
            <Input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </Field>
          <Field label="备注">
            <Input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="可选"
            />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={isPending}>
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ edit (reschedule) dialog
export function BookingEditDialog({
  target,
  deviceName,
  profiles,
  tenantId,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Booking | null;
  deviceName: string;
  profiles: CustomerProfileRead[];
  tenantId?: string;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (id: string, payload: BookingUpdate) => Promise<void>;
}) {
  const [customerId, setCustomerId] = useState<string>(NONE);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [notes, setNotes] = useState("");
  const [missing, setMissing] = useState<string | null>(null);

  // Sync the form from the target whenever it changes (open with a new
  // booking, or the parent swaps targets while open). The dependency on
  // ``target`` (object identity) is intentional — a new target object means
  // "open with this booking"; the same target across renders is a no-op.
  useEffect(() => {
    if (target) {
      setCustomerId(target.customer_id ?? NONE);
      setStart(toDatetimeLocalValue(target.scheduled_start_at));
      setEnd(toDatetimeLocalValue(target.scheduled_end_at));
      setNotes(target.notes ?? "");
      setMissing(null);
    }
  }, [target]);

  const submit = async () => {
    if (!target) return;
    if (!start || !end) {
      setMissing("请填写预约时段");
      return;
    }
    setMissing(null);
    const payload: BookingUpdate = {
      customer_id: customerId === NONE ? null : customerId,
      scheduled_start_at: fromDatetimeLocalValue(start),
      scheduled_end_at: fromDatetimeLocalValue(end),
      notes: notes.trim() || null,
      ...(tenantId ? { tenant_id: tenantId } : {}),
    };
    await onSubmit(target.id, payload);
  };

  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>改约</DialogTitle>
          <DialogDescription>
            调整预约时段、客户或备注。设备为预约身份,不可变更(如需换设备请取消后重建)。
          </DialogDescription>
        </DialogHeader>
        {target && (
          <div className="space-y-4">
            {/* device_id is immutable (D10) — rendered read-only/greyed. Only
                pending bookings reach this dialog (the menu hides for other
                states), so no extra gating is needed inside. */}
            <Field label="设备(不可修改)">
              <Input value={deviceName} disabled />
            </Field>
            <CustomerField
              label="客户"
              value={customerId}
              profiles={profiles}
              onChange={setCustomerId}
              hint={
                profiles.length === 0
                  ? undefined
                  : "可不选 — 散客(walk-in)预约不绑定客户"
              }
            />
            <Field
              label="预约开始时间 *"
              error={missing ?? undefined}
            >
              <Input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </Field>
            <Field label="预约结束时间 *">
              <Input
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </Field>
            <Field label="备注">
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
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

// ============================================================ cancel confirm dialog
export function BookingCancelDialog({
  target,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Booking | null;
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
          <DialogTitle>确认取消预约</DialogTitle>
          <DialogDescription>
            确定取消该预约?取消后预约状态变为「已取消」,不可在此恢复
            (如需重新预约请新建)。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            返回
          </Button>
          <Button variant="destructive" onClick={submit} disabled={isPending}>
            <XCircle className="mr-2 h-4 w-4" /> 取消预约
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ end-service dialog
export function BookingEndDialog({
  target,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Booking | null;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (id: string, payload?: BookingEndPayload) => Promise<void>;
}) {
  const [feedback, setFeedback] = useState("");

  // Clear the textarea whenever the target changes (open with a new booking,
  // or close→reopen). Mirrors the create dialog's reset-on-target pattern.
  useEffect(() => {
    setFeedback("");
  }, [target]);

  const submit = async () => {
    if (!target) return;
    const trimmed = feedback.trim();
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
    await onSubmit(target.id, payload);
  };

  return (
    <Dialog
      open={!!target}
      onOpenChange={(o) => {
        if (!o) onClose();
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
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder='{"rating": 5, "note": "客户反馈"}'
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            rows={3}
          />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={isPending}>
            <Square className="mr-2 h-4 w-4" /> 结束服务
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ no-show confirm dialog
export function BookingNoShowDialog({
  target,
  isPending,
  onClose,
  onSubmit,
}: {
  target: Booking | null;
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
          <DialogTitle>确认标记爽约</DialogTitle>
          <DialogDescription>
            确定将该预约标记为「爽约」?爽约记录会影响排期释放与统计,操作不可撤销。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            返回
          </Button>
          <Button variant="destructive" onClick={submit} disabled={isPending}>
            <UserX className="mr-2 h-4 w-4" /> 标记爽约
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ inline row action menu
//
// Per-row action menu (the three-dot trigger + items). Extracted so both the
// store view and the HQ view render the same status-driven menu. ``onEdit`` /
// ``onCancel`` / ``onStart`` / ``onEnd`` / ``onNoShow`` are the parent's
// state-setter callbacks (open the corresponding Dialog); the visibility flags
// mirror StoreView's status logic verbatim (MUTABLE_STATUS for edit/cancel;
// ACTIONABLE_STATUS + status-specific gating for the lifecycle actions).
export function BookingRowMenu({
  booking,
  canUpdate,
  canCancel,
  onEdit,
  onCancel,
  onStart,
  onEnd,
  onNoShow,
}: {
  booking: Booking;
  canUpdate: boolean;
  canCancel: boolean;
  onEdit: (b: Booking) => void;
  onCancel: (b: Booking) => void;
  onStart: (b: Booking) => void;
  onEnd: (b: Booking) => void;
  onNoShow: (b: Booking) => void;
}) {
  const mutable = MUTABLE_STATUS.has(booking.status);
  const actionable = ACTIONABLE_STATUS.has(booking.status);
  // Per-state action visibility: start guards on canUpdate (:update);
  // end/no-show guard on canCancel (:delete, owner-only on store path,
  // always-true on HQ path since platform writers bypass require).
  const canStart =
    actionable &&
    (booking.status === "pending" || booking.status === "confirmed") &&
    canUpdate;
  const canEnd = booking.status === "in_service" && canCancel;
  const canMarkNoShow = actionable && canCancel;
  const showMenu =
    (canUpdate || canCancel) &&
    actionable &&
    (mutable || canStart || canEnd || canMarkNoShow);

  if (!showMenu) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {mutable && canUpdate && (
          <DropdownMenuItem onClick={() => onEdit(booking)}>
            改约
          </DropdownMenuItem>
        )}
        {canStart && (
          <DropdownMenuItem onClick={() => onStart(booking)}>
            确认开机
          </DropdownMenuItem>
        )}
        {canEnd && (
          <DropdownMenuItem onClick={() => onEnd(booking)}>
            结束服务
          </DropdownMenuItem>
        )}
        {canMarkNoShow && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onNoShow(booking)}
            >
              标记爽约
            </DropdownMenuItem>
          </>
        )}
        {mutable && canCancel && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onCancel(booking)}
            >
              取消预约
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// Re-export Plus so the HQ view's PageHeader action button can import everything
// from one place (matches the shared.tsx convention).
export { Plus };
