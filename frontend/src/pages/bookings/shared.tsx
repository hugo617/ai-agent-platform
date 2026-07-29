/**
 * bookings/ shared display primitives — the small cross-view bits that stay
 * shared after the per-function split (plan-shared-tsx-split).
 *
 * 切片 1+2 之后这个文件瘦身为只剩 2 个真共享显示原语:
 * - ``BookingStatusBadge``: 状态徽章,跨 store-view / hq-view / my-bookings-view
 *   三 view 共享(列表里每一行都用它渲染状态列)。
 * - ``deviceNameOf``: device_id→序列号,单消费者 store-view,但语义是「显示
 *   原语」(与 BookingStatusBadge 同类),留 shared 避免孤儿文件(D7 决策)。
 *
 * 其余符号已按功能职责归位:状态领域模型 → ``status-meta.ts``,日期运算 →
 * ``date-utils.ts``,列表过滤 → ``filter.tsx``,StoreView 排期网格 →
 * ``schedule-grid-card.tsx``;``fmt``/``fromDatetimeLocalValue`` 已回源
 * ``@/lib/format``(D5,消除便利 re-export)。消费者按需 deep import 各功能文件。
 *
 * Pure locality move: zero behaviour change. Extracted from the original
 * 1373-line bookings-page.tsx (plan-bookings-page-split.md).
 */
import { Badge } from "@/components/ui/badge";
import type { BookingStatus } from "@/api/types";
import { STATUS_META } from "./status-meta";

export function BookingStatusBadge({ status }: { status: BookingStatus }) {
  const meta = STATUS_META[status];
  return <Badge variant={meta.badge}>{meta.label}</Badge>;
}

/** Resolve a booking's device_id to its serial number for display. Falls back
 * to the id prefix when the device was soft-deleted between list fetches (the
 * backend's SET-NULL FK keeps the booking row, but a live device list filters
 * soft-deleted rows out — a rare transient). */
export function deviceNameOf(
  deviceId: string | null,
  deviceMap: Map<string, string>,
): string {
  if (!deviceId) return "—";
  return deviceMap.get(deviceId) ?? `设备(${deviceId.slice(0, 8)})`;
}
