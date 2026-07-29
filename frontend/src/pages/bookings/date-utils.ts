/**
 * bookings/ 日期/时间纯函数 —— 本地历日运算。
 *
 * 从原 1373 行 bookings-page.tsx 抽出(plan-shared-tsx-split 切片 1)。
 * 无 React、无副作用依赖的叶子节点,供 hq-view / schedule-grid / filter /
 * schedule-grid-card 按需 deep import。
 *
 * 所有比较都在日历日(``YYYY-MM-DD``)上,而非时间戳 —— "today" 过滤匹配
 * 整个本地日,忽略小时。保持本地时(不做 UTC 偏移),因为门店的排期表按
 * 墙钟时间读。
 */

export function startOfToday(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

export function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

/** ``YYYY-MM-DD`` for a Date (local). Used as the DeviceSchedule map key. */
export function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** ``HH:mm`` from an ISO timestamp (local). Slot card time label. */
export function hhmm(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** ``周一 7/24`` style label for a schedule column header. ``offset`` is 0 for
 * today (rendered as "今天"). */
export function dayLabel(d: Date, offset: number): string {
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const prefix = offset === 0 ? "今天" : offset === 1 ? "明天" : weekdays[d.getDay()];
  return `${prefix} ${d.getMonth() + 1}/${d.getDate()}`;
}
