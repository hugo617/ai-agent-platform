/**
 * bookings/ 列表过滤逻辑 —— chip 预设 + 过滤应用函数 + FilterChips 组件树。
 *
 * 从原 1373 行 bookings-page.tsx 抽出(plan-shared-tsx-split 切片 2)。
 * 消费者:仅 ``store-view.tsx``。时间过滤依赖 ``date-utils.ts`` 的本地历日
 * 运算(startOfToday / addDays / isoDate),状态过滤是精确匹配。
 *
 * Why a dedicated module: 过滤是 StoreView 列表的单一职责(其它 view 不用),
 * 集中在此意味着改过滤预设只动一个文件,不必碰「共享显示原语」。
 *
 * 注:plan §4.1/§6 记为 ``filter.ts``,但 FilterChips 含 JSX,TypeScript 硬约束
 * 要求 JSX 文件用 ``.tsx`` 扩展名,故落地为 ``filter.tsx``(内容与 plan 一致)。
 */
import { Button } from "@/components/ui/button";
import type { Booking } from "@/api/types";
import { startOfToday, addDays, isoDate } from "./date-utils";

/** List filter presets for the chip row. "all" = no filter. */
export type BookingFilter =
  | "all"
  | "today"
  | "tomorrow"
  | "this_week"
  | "pending"
  | "no_show";

export const FILTER_OPTIONS: { value: BookingFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "today", label: "今日" },
  { value: "tomorrow", label: "明日" },
  { value: "this_week", label: "本周" },
  { value: "pending", label: "待确认" },
  { value: "no_show", label: "爽约" },
];

/** Hand-rolled mutually-exclusive button row. Mirrors the dashboard trend-days
 * toggle (dashboard-page.tsx:244) — no shadcn Tabs primitive exists in this
 * project, and settings-page deliberately avoids adding one. */
export function FilterChips({
  value,
  onChange,
}: {
  value: BookingFilter;
  onChange: (v: BookingFilter) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {FILTER_OPTIONS.map((opt) => (
        <Button
          key={opt.value}
          variant={value === opt.value ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}

/** Apply a chip filter to the booking list. Time filters compare on the local
 * calendar day of ``scheduled_start_at``; status filters are an exact match. */
export function applyBookingFilter(
  list: Booking[],
  filter: BookingFilter,
): Booking[] {
  if (filter === "all") return list;
  if (filter === "pending" || filter === "no_show") {
    return list.filter((b) => b.status === filter);
  }
  const today = startOfToday();
  const todayKey = isoDate(today);
  const tomorrowKey = isoDate(addDays(today, 1));
  // "本周" = the Monday-containing week of today (Mon→Sun), so a sheet printed
  // mid-week still shows the whole current week.
  const weekStart = addDays(today, -((today.getDay() + 6) % 7)); // Mon of this week
  const weekEnd = addDays(weekStart, 7); // exclusive
  return list.filter((b) => {
    const start = new Date(b.scheduled_start_at);
    const key = isoDate(start);
    if (filter === "today") return key === todayKey;
    if (filter === "tomorrow") return key === tomorrowKey;
    // this_week: start date within [weekStart, weekEnd)
    return start >= weekStart && start < weekEnd;
  });
}
