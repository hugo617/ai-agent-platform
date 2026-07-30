/**
 * devices/ shared.tsx — 共享 React 显示原语 + ModelOption 类型投影。
 *
 * 从原 1083 行 devices-page.tsx 抽出(plan-devices-page-split.md)。镜像
 * ``bookings/shared.tsx`` 的范式:跨 store-view / hq-view 共享的「显示原语」
 * 集中一处,view 按需 import。无逻辑变更,纯 locality move。
 *
 * 符号:
 * - ``StatusSelect`` / ``StatusBadge``: 状态 Select + 徽章,create/edit Dialog
 *   与两 view 的列表行均用。
 * - ``customerNameOf``: customer_id → 显示名解析(store view 列表用;HQ view
 *   的 customer_name 已服务端展开,直接读)。
 * - ``ModelOption``: device-models dropdown 的最小投影类型 {id, name}。
 *   useDeviceModels 返回 DeviceModelPublic[],picker 只需 {id, name},投影到
 *   这个最小 pick(一个 C 类字段投影 cast,非角色分支 cast —— union-cast-split
 *   裁决 D2 保留)。两 view 都用 model dropdown,故放 shared 而非各 view 内。
 */
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CustomerProfileRead, DeviceStatus } from "@/api/types";
import { STATUS_META, STATUS_OPTIONS } from "./device-status-meta";

// Forward declaration of the DeviceModelRead-like shape used by the model
// dropdown. useDeviceModels returns DeviceModelPublic[] (store path) — the
// model picker only needs {id, name}, so we project onto that minimal pick for
// the dropdown (a C-class field-projection cast, NOT a role-branching cast —
// kept out of plan-union-cast-split per decision D2).
export type ModelOption = { id: string; name: string };

/** Three-state status Select shared by the create + edit dialogs (extracted to
 * avoid duplicating the STATUS_OPTIONS mapping in two places). */
export function StatusSelect({
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

export function StatusBadge({ status }: { status: DeviceStatus }) {
  const meta = STATUS_META[status];
  return <Badge variant={`dot-${meta.badge}`}>{meta.label}</Badge>;
}

/** Resolve a device's customer_id to a display name from the profiles list.
 * Returns "-" when unbound (or when the profiles list hasn't loaded yet and
 * the id is non-null — a rare transient state that resolves on next render). */
export function customerNameOf(
  customerId: string | null,
  profiles: CustomerProfileRead[] | undefined,
): string {
  if (!customerId) return "-";
  const hit = profiles?.find((p) => p.customer_id === customerId);
  return hit?.customer.name ?? "—";
}
