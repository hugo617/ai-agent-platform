/**
 * bookings/ StoreView 专属的排期网格卡组件树。
 *
 * 从原 shared.tsx 抽出(plan-shared-tsx-split 切片 2)。消费者:仅
 * ``store-view.tsx``。依赖 ``status-meta.ts``(STATUS_META)+ ``date-utils.ts``
 * (startOfToday / addDays / isoDate / dayLabel / hhmm)。
 *
 * Why a dedicated module: ScheduleGridCard 是 StoreView 专属的私有组件树
 * (HqView 是只读全景,MyBookingsView 是客户列表,都不消费它)。它原本混在
 * 「所有 view 共享的 shared.tsx」里 —— 改 StoreView 的网格逻辑会触发那个名义
 * 上「共享」的文件变更(Divergent Change)。抽出后改网格只动这一个文件。
 *
 * ``slotTone`` 归此非 badges.tsx(D6 决策):它是 ScheduleSlot 的私有 helper
 * (单消费者),与 BookingStatusBadge 是不同的视觉系统(三态色 vs 状态徽章)。
 */
import { useMemo } from "react";

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
import type { Booking, BookingStatus, Device } from "@/api/types";
import { useDeviceSchedule } from "@/hooks/queries";
import { STATUS_META } from "./status-meta";
import { startOfToday, addDays, isoDate, dayLabel, hhmm } from "./date-utils";

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
// customer's own list); it depends on shared date helpers + STATUS_META.
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
