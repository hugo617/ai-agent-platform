/**
 * bookings/ shared bits — status metadata, list filters, date helpers, the
 * schedule grid, and small display primitives. Extracted from the original
 * 1373-line bookings-page.tsx as part of the view-split refactor
 * (plan-bookings-page-split.md). Pure locality move: zero behaviour change.
 *
 * Why this module exists: StoreView, HqView, MyBookingsView and the schedule
 * grid all share the status→{label,badge} mapping and the date math. Keeping
 * them in one place means a status rename touches one file, not four.
 */
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FormField as Field } from "@/components/ui/form-field";
import { ListState } from "@/components/ui/list-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fromDatetimeLocalValue,
  formatDateTime as fmt,
} from "@/lib/format";
import type { Booking, BookingStatus, Device } from "@/api/types";
import { useDeviceSchedule } from "@/hooks/queries";

// Re-export the status domain model + date helpers from their new homes
// (plan-shared-tsx-split 切片 1, expand-contract). shared.tsx still owns the
// other shared display primitives (BookingStatusBadge / deviceNameOf) until
// 切片 2 re-points consumers at deep imports and slims this file. Keeping the
// re-export here means existing consumers (badges / shared-dialog / the views)
// need zero import-path changes in this slice.
import {
  STATUS_META,
  MUTABLE_STATUS,
  ACTIONABLE_STATUS,
  NONE,
} from "./status-meta";
import {
  startOfToday,
  addDays,
  isoDate,
  hhmm,
  dayLabel,
} from "./date-utils";

export { STATUS_META, MUTABLE_STATUS, ACTIONABLE_STATUS, NONE };
export { startOfToday, addDays, isoDate, hhmm, dayLabel };

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

// Re-export the format helpers the views use, so views import everything from
// one place (cuts the number of cross-file imports per view).
export { fromDatetimeLocalValue, fmt };

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

/** Slot-box colour bucket for the schedule grid. Three display tones match the
 * plan's "booked/active/done 三态色" mapping (active = pending/confirmed/
 * in_service; done = done; released = cancelled/no_show). */
export function slotTone(status: BookingStatus): { cls: string } {
  if (status === "done") {
    return { cls: "border-border bg-background text-muted-foreground" };
  }
  if (status === "cancelled" || status === "no_show") {
    return { cls: "border-destructive/30 bg-destructive/5 text-destructive/80 line-through" };
  }
  // active bucket: pending / confirmed / in_service
  return { cls: "border-primary/30 bg-primary/5 text-primary" };
}

// ============================================================ schedule grid
//
// The per-device 7-day grid. No calendar widget (plan: "别过度设计,不做日历
// 控件"). Layout: a device picker + one column per day for the next 7 days
// (today → today+6); each column lists that day's bookings as slot-box cards,
// tinted by the three display buckets (active = pending/confirmed/in_service,
// done = done, released = cancelled/no_show). Empty days render a muted
// placeholder so the column shape is stable.
//
// ``useDeviceSchedule(id, today, today+7d)`` returns only days with ≥1 booking,
// so we look up each of the 7 days in the result map (missing key → empty col).
//
// Used by StoreView only (HqView is read-only panorama, MyBookingsView is the
// customer's own list); kept here because it depends on shared date helpers +
// STATUS_META, and StoreView is its sole consumer.
export function ScheduleGridCard({
  devices,
  selectedId,
  onSelect,
}: {
  devices: Device[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  // The 7-day window: today → today+7d (exclusive end, matching the backend's
  // left-closed/right-open overlap semantics). Computed once per render; the
  // user isn't paginating weeks in this slice.
  const { days, startIso, endIso } = useMemo(() => {
    const today = startOfToday();
    const end = addDays(today, 7);
    const arr: { iso: string; label: string }[] = [];
    for (let i = 0; i < 7; i++) {
      const d = addDays(today, i);
      arr.push({ iso: isoDate(d), label: dayLabel(d, i) });
    }
    return { days: arr, startIso: today.toISOString(), endIso: end.toISOString() };
  }, []);

  const { data: schedule, isLoading } = useDeviceSchedule(
    selectedId || null,
    startIso,
    endIso,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>设备排期</CardTitle>
        <CardDescription>
          选择一台设备,查看未来 7 天的预约排布。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label="设备">
          <Select value={selectedId} onValueChange={onSelect}>
            <SelectTrigger>
              <SelectValue placeholder="选择设备查看排期" />
            </SelectTrigger>
            <SelectContent>
              {devices.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.serial_number}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {!selectedId ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            选择一台设备以查看排期。
          </p>
        ) : (
          // The 7 columns always render (one per day), so there's no list-level
          // empty state — each empty day shows its own "空" placeholder inside
          // the column. ListState is used here purely as a loading gate while
          // the schedule fetch is in flight.
          <ListState isLoading={isLoading} isEmpty={false}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
              {days.map((day) => {
                const dayBookings = schedule?.[day.iso] ?? [];
                return (
                  <div
                    key={day.iso}
                    className="min-h-32 rounded-md border bg-muted/30 p-2"
                  >
                    <div className="mb-2 text-xs font-medium text-muted-foreground">
                      {day.label}
                    </div>
                    {dayBookings.length === 0 ? (
                      <p className="py-4 text-center text-xs text-muted-foreground/60">
                        空
                      </p>
                    ) : (
                      <div className="space-y-1.5">
                        {dayBookings.map((b) => (
                          <ScheduleSlot key={b.id} booking={b} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ListState>
        )}
      </CardContent>
    </Card>
  );
}

/** One booking inside a schedule day column. Colour-coded by the three display
 * buckets (active / done / released) so a glance reads the device's day. */
function ScheduleSlot({ booking }: { booking: Booking }) {
  const tone = slotTone(booking.status);
  const time = `${hhmm(booking.scheduled_start_at)}–${hhmm(booking.scheduled_end_at)}`;
  return (
    <div
      className={`rounded border px-2 py-1 text-xs ${tone.cls}`}
      title={`${time} · ${STATUS_META[booking.status].label}`}
    >
      <div className="font-medium">{time}</div>
      <div className="opacity-80">{STATUS_META[booking.status].label}</div>
    </div>
  );
}
