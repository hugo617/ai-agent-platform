/**
 * booking 状态领域模型 —— 6-state status → {label,badge} 映射 + 派生状态集。
 *
 * 从原 1373 行 bookings-page.tsx 抽出的「状态原语」(plan-shared-tsx-split
 * 切片 1)。无 React 依赖的叶子节点,供 badges / schedule-grid-card /
 * shared-dialog 等按需 deep import。
 *
 * Why a dedicated module: 状态机常量是 bookings 子域的词汇表,集中在一处
 * 意味着加新状态(如 ``confirmed`` 真正启用)只改一个文件,不必遍历所有 view。
 */
import type { BookingStatus } from "@/api/types";

// 6-state status → {label, badge}. Each badge value is the literal Badge
// variant name (``dot-warning`` / ``dot-success`` / ``dot-muted`` /
// ``dot-destructive``), so STATUS_META reads as the plan's colour mapping
// verbatim with no intermediate token to collapse. pending/in_service/no_show
// pick a tinted dot; the neutral "settled" states (confirmed / done /
// cancelled) share the muted grey dot — informational, not warning/danger.
//
// ``confirmed`` is a forward-compat placeholder (no /confirm endpoint yet, see
// plan §0 D2) — the mapping is defined for completeness but unreachable in
// this feature; a booking never enters that state here.
export const STATUS_META: Record<
  BookingStatus,
  {
    label: string;
    badge: "dot-warning" | "dot-success" | "dot-muted" | "dot-destructive";
  }
> = {
  pending: { label: "待确认", badge: "dot-warning" },
  confirmed: { label: "已确认", badge: "dot-muted" },
  in_service: { label: "服务中", badge: "dot-success" },
  done: { label: "已完成", badge: "dot-muted" },
  cancelled: { label: "已取消", badge: "dot-muted" },
  no_show: { label: "爽约", badge: "dot-destructive" },
};

// SelectValue can't render an empty string; "_none" is the sentinel for the
// "walk-in (no customer)" option in the create/edit dialog. Mirrors the
// devices-page bind dialog convention (chat-page.tsx:685-707 lineage).
export const NONE = "_none";

// Only ``pending`` bookings are mutable (D10) — reschedule / cancel are hidden
// for every other state. ``confirmed`` is a forward-compat placeholder state
// that this feature never enters, so it's intentionally NOT in the mutable set
// (it would be cancelled via a future /confirm + /cancel flow, not here).
export const MUTABLE_STATUS: ReadonlySet<BookingStatus> = new Set(["pending"]);

// device-poweron (切片 03):the status set that still has a state-machine action
// available. Reschedule / cancel stay gated on ``MUTABLE_STATUS`` (pending only)
// — those are bookings edits, not lifecycle actions. ``ACTIONABLE_STATUS`` gates
// the lifecycle menu (start / end / no-show): pending / confirmed / in_service
// each have ≥1 action; the terminal states (done / cancelled / no_show) have
// none and hide the menu entirely. ``confirmed`` is included defensively — the
// state machine allows start/no-show from it, but device-booking never writes
// ``confirmed`` so the branch is unreachable at runtime (code comment only).
export const ACTIONABLE_STATUS: ReadonlySet<BookingStatus> = new Set([
  "pending",
  "confirmed",
  "in_service",
]);
