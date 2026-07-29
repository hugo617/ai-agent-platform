/**
 * bookings/ ScheduleGrid — device×time schedule grid
 * (booking-schedule-grid 切片 04a).
 *
 * The core grid component. Pure presentational + click-callback: it receives
 * devices + bookings + config + selectedDate + now as props and renders the
 * grid, calling ``onSlotClick`` when an empty bookable cell is clicked. NO
 * data fetching, NO auth context, NO react-query — the parent (HqView in slice
 * 04b) owns the hooks and threads the loaded data in. This keeps the grid a
 * pure function of its props (plan §切片 04a: "纯展示 + 点击回调").
 *
 * Visual truth source: harness/demo/booking-schedule-grid-demo.html (D0). The
 * CSS class names are kept IDENTICAL to the demo and double as the test
 * selectors (plan P5): ``.corner`` / ``.device-col`` / ``.cell.bookable`` /
 * ``.cell.disabled`` / ``.cell.selected-full`` / ``.cell.selected-half`` /
 * ``.booking-block.span-2`` / ``.booking-block.span-1-5`` /
 * ``.booking-block.st-pending|st-confirmed|st-inservice|st-done|st-cancel``.
 * The styles live in ``./schedule-grid.css`` (imported here) — ported verbatim
 * from the demo so the visual contract is one source of truth.
 *
 * Time model: the grid is wall-clock. ``BookingHqRead.scheduled_*`` are naive
 * ISO strings; we read their local hours/minutes (mirrors shared.tsx ``hhmm``)
 * so a store's sheet reads in its own timezone. ``now`` is prop-injected (D6)
 * — default ``new Date()``, tests pass a literal — so time-sensitive behaviour
 * is deterministic without ``vi.useFakeTimers`` (no precedent in this project).
 */
import { useMemo, useState } from "react";

import type {
  BookingConfig,
  BookingHqRead,
  BookingStatus,
  DeviceHqRead,
} from "@/api/types";
import { hhmm } from "./date-utils";
import "./schedule-grid.css";

/** 6-state booking lifecycle → demo CSS class suffix (P5) + Chinese tooltip
 * label, as one map so the status→{class,label} derivation has a single site
 * (collapses what were two parallel switches in the demo into one lookup).
 *
 * WHY THIS IS NOT shared.tsx's STATUS_META: STATUS_META carries the *list-view
 * Badge*文案 (pending=「待确认」, in_service=「服务中」), which the rest of the
 * bookings UI renders. The grid tooltip uses the *demo-accepted*文案
 * (pending=「待开始」, in_service=「进行中」) — a different wording the user signed
 * off on in harness/demo/booking-schedule-grid-demo.html. Plan §切片 04a locks
 * the visual to the demo, so the grid keeps the demo's wording here on
 * purpose. Two maps is the cost of that decision; merging would silently
 * re-word the tooltip away from what the user accepted. The colour buckets
 * likewise mirror the demo (cancelled + no_show share st-cancel = "released"). */
const BOOKING_STATUS_GRID: Record<
  BookingStatus,
  { cls: string; label: string }
> = {
  pending: { cls: "st-pending", label: "待开始" },
  confirmed: { cls: "st-confirmed", label: "已确认" },
  in_service: { cls: "st-inservice", label: "进行中" },
  done: { cls: "st-done", label: "已完成" },
  cancelled: { cls: "st-cancel", label: "已取消" },
  no_show: { cls: "st-cancel", label: "爽约" },
};

/** "HH:MM" 24-hour string (config.window_*) → decimal hours (8.5 = 08:30).
 * Returns NaN on malformed input; callers guard with Number.isFinite. */
function hhmmToHours(hhmm: string): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!m) return NaN;
  return Number(m[1]) + Number(m[2]) / 60;
}

/** Decimal hours (9.5 = 09:30) → "HH:MM". Mirrors the demo's ``hourToLabel``.
 * Used for the time-column row labels (windowStart + slotIdx*0.5 → label),
 * which are NOT ISO timestamps, so shared.tsx's ``hhmm(iso)`` doesn't apply.
 * Minutes round to the nearest minute with a 60-carry guard (8.999 → "09:00"
 * not "08:60") — fixes the demo's naive-rounding edge. */
function hoursToLabel(h: number): string {
  let hh = Math.floor(h);
  let mm = Math.round((h - hh) * 60);
  if (mm === 60) {
    mm = 0;
    hh += 1;
  }
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** ISO timestamp → local wall-clock decimal hours (09:30 local = 9.5). The
 * grid compares these to window start/end and ``now`` — all wall-clock, so a
 * store's booking sheet reads in its own timezone. */
function isoToHours(iso: string): number {
  const d = new Date(iso);
  return d.getHours() + d.getMinutes() / 60;
}

/** Slot step in decimal hours. Fixed at 30 minutes — the grid renders two
 * rows per hour (整点行 + 半点行), matching the demo D0. */
const SLOT_STEP = 0.5;

/** Device status → dot CSS modifier class. active = default (no modifier);
 * maintenance / retired add a modifier that recolours the dot. Mirrors the
 * demo's ``d-status-dot`` branches. */
function deviceDotClass(status: DeviceHqRead["status"]): string {
  if (status === "maintenance") return "maintenance";
  if (status === "retired") return "retired";
  return "";
}

/** Build the start/end ISO for a clicked slot, on the selectedDate at the
 * slot's wall-clock hour. Used both for the onSlotClick callback and to mark
 * the spanned cells. */
function slotHourToISO(selectedDate: Date, hourDecimal: number): string {
  const hh = Math.floor(hourDecimal);
  const mm = Math.round((hourDecimal - hh) * 60);
  const d = new Date(selectedDate);
  d.setHours(hh, mm, 0, 0);
  return d.toISOString();
}

/** The active cell selection: which device column + which time slot the user
 * clicked. Bundled as one type (rather than two loose numbers) because the
 * pair always travels together — into useState, through selectionClass, and
 * against each rendered cell. Null = nothing selected. */
interface GridSelection {
  deviceIdx: number;
  slotIdx: number;
}

/** Which selection class (``selected-full`` / ``selected-half`` / none) does
 * the cell at ``(deviceIdx, slotIdx)`` get, given the active selection and the
 * configured duration? Generalised from the demo's 45/60 branches (plan D3 —
 * arbitrary integer duration):
 *
 * Walk the slots the selection covers from its anchor. At slot offset ``o``
 * (0-indexed from the anchor), ``duration - o*30`` minutes remain:
 *   - ≥ 30 remaining  → ``selected-full``(this slot is fully covered)
 *   - 0 < remaining < 30 → ``selected-half``(partial — the demo's →:45 mark)
 *   - ≤ 0             → not part of the selection
 *
 * Worked: 45min → slot0 full (45≥30), slot1 half (15>0); 60min → slot0 full,
 * slot1 full (30≥30); 90min → 3 full; 75min → full, full, half. */
function selectionClass(
  selection: GridSelection | null,
  deviceIdx: number,
  slotIdx: number,
  duration: number,
): "selected-full" | "selected-half" | null {
  if (!selection || selection.deviceIdx !== deviceIdx) return null;
  const offset = slotIdx - selection.slotIdx;
  if (offset < 0) return null;
  const remaining = duration - offset * 30;
  if (remaining >= 30) return "selected-full";
  if (remaining > 0) return "selected-half";
  return null;
}

/**
 * Props for the schedule grid.
 *
 * ``config`` accepts any row shaped like ``{ default_duration_minutes;
 * window_start; window_end }`` — i.e. both ``BookingConfig`` (the persisted
 * row) and ``BookingConfigEffective`` (the merged read view) are structurally
 * compatible. The grid needs only these three fields; plan §切片 04a lists
 * ``BookingConfig`` and slice 04b's ``useBookingConfigEffective`` returns the
 * effective shape — both pass through unchanged (structural subtyping, no
 * adapter needed).
 *
 * ``now`` defaults to ``new Date()`` (D6) but tests pin it to a literal so
 * the disabled-past-cells branch is deterministic.
 *
 * ``onSlotClick(device, startISO, endISO)`` fires only on a bookable empty
 * cell click — occupied cells and disabled (past) cells do not invoke it.
 */
export interface ScheduleGridProps {
  devices: DeviceHqRead[];
  bookings: BookingHqRead[];
  config: Pick<
    BookingConfig,
    "default_duration_minutes" | "window_start" | "window_end"
  >;
  selectedDate: Date;
  /** Clock for the disabled-past-cell branch. Default ``new Date()``; tests
   * pass a literal (D6 — no fake timers). */
  now?: Date;
  onSlotClick: (
    device: DeviceHqRead,
    startISO: string,
    endISO: string,
  ) => void;
}

/**
 * Device × time schedule grid. Renders the devices as columns (card-style
 * header) and time as rows (28 half-hour rows by default, driven by config
 * window). Clicking an empty bookable cell selects it (visual highlight) and
 * fires ``onSlotClick``; occupied + past cells are non-interactive.
 */
export function ScheduleGrid({
  devices,
  bookings,
  config,
  selectedDate,
  now = new Date(),
  onSlotClick,
}: ScheduleGridProps) {
  // selection: which cell is currently clicked. Null when nothing is selected.
  // Local state — the grid is the selection owner until the parent turns the
  // click into a BookingCreateDialog (slice 04b).
  const [selection, setSelection] = useState<GridSelection | null>(null);

  // Window + slot grid derived from config. Recomputes when config changes so
  // a parent passing a new effective config rerenders the right row count
  // (plan AC: "父传新 config prop → 网格 rerender 行数变化"). Defaults to
  // 08:00-22:00 if the config strings are malformed (defensive — backend
  // enforces the HH:MM pattern, but NaN propagates silently otherwise).
  const { totalSlots, windowStart } = useMemo(() => {
    const ws = hhmmToHours(config.window_start);
    const we = hhmmToHours(config.window_end);
    const start = Number.isFinite(ws) ? ws : 8;
    const end = Number.isFinite(we) ? we : 22;
    return {
      totalSlots: Math.max(0, Math.round((end - start) / SLOT_STEP)),
      windowStart: start,
    };
  }, [config.window_start, config.window_end]);

  const duration = config.default_duration_minutes;
  const isSelectedToday = isSameLocalDay(selectedDate, now);
  // now as decimal hours — only meaningful when selectedDate is today. Future
  // dates render every cell bookable (the demo's "未来日期全可点" rule).
  const nowHours = now.getHours() + now.getMinutes() / 60;

  // Pre-index bookings by (deviceIdx, startHour) so each cell lookup is O(1).
  // A booking renders its block ONLY on its start slot; subsequent slots it
  // covers are left as plain cells (the block absolutely positions over them
  // via span-2 / span-1-5). Mirrors the demo's findBooking + renderCell.
  // Computed unconditionally (before the empty-state early return) so the
  // hook order is stable across renders — React's rules-of-hooks requirement.
  const bookingByDeviceSlot = useMemo(() => {
    const map = new Map<string, BookingHqRead>();
    if (devices.length === 0) return map; // empty-state path skips the loop
    for (const b of bookings) {
      const deviceIdx = devices.findIndex((d) => d.id === b.device_id);
      if (deviceIdx === -1) continue; // booking for a device not in the grid
      const startH = isoToHours(b.scheduled_start_at);
      // The block anchors on the slot whose hour === booking start. Find the
      // nearest slot index (handles 09:00 → slot 2 when window is 08:00).
      const slotIdx = Math.round((startH - windowStart) / SLOT_STEP);
      if (slotIdx < 0 || slotIdx >= totalSlots) continue;
      map.set(`${deviceIdx}:${slotIdx}`, b);
    }
    return map;
  }, [bookings, devices, windowStart, totalSlots]);

  // Empty state (AC): no devices → placeholder, no grid. All hooks above run
  // unconditionally; this early return is render-only (no hook calls after).
  if (devices.length === 0) {
    return (
      <div className="sg-empty">
        <p className="sg-empty-text">该门店暂无可用设备</p>
      </div>
    );
  }

  /** Click handler for a bookable empty cell. Selects it (visual highlight)
   * and fires onSlotClick with the device + start/end ISO. Duration drives
   * the end time (start + duration minutes). */
  function handleCellClick(deviceIdx: number, slotIdx: number) {
    setSelection({ deviceIdx, slotIdx });
    const startH = windowStart + slotIdx * SLOT_STEP;
    const endH = startH + duration / 60;
    onSlotClick(devices[deviceIdx], slotHourToISO(selectedDate, startH), slotHourToISO(selectedDate, endH));
  }

  return (
    <div className="grid-scroll">
      <table className="grid">
        <thead>
          <tr>
            {/* Left-top corner cell with diagonal divider (AC: 斜线分隔). */}
            <th className="corner">
              <span className="lbl-device">设备 →</span>
              <span className="lbl-time">← 时间</span>
            </th>
            {/* Device column headers — card style: name + id + status dot.
                Mirrors the demo's d-name (big, human-readable device name) +
                d-id (small, monospace identifier). The demo's data shaped
                ``{id:"DEV-001", name:"理疗床 1"}`` maps to project fields as
                model_name (human label) → d-name, serial_number (identifier)
                → d-id. model_name falls back to serial_number when the model
                row is gone (soft-delete transient) so the big slot is never
                empty. */}
            {devices.map((d) => (
              <th key={d.id} className="device-col">
                <div className="d-card">
                  <span
                    className={`d-status-dot ${deviceDotClass(d.status)}`}
                  />
                  <div className="d-info">
                    <div className="d-name">
                      {d.model_name ?? d.serial_number}
                    </div>
                    <div className="d-id">{d.serial_number}</div>
                  </div>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: totalSlots }, (_, slotIdx) => {
            const hour = windowStart + slotIdx * SLOT_STEP;
            const isHourRow = slotIdx % 2 === 0; // 整点行(显示大字 + 半点小字)
            const isPast = isSelectedToday && hour < nowHours;
            return (
              <tr key={slotIdx}>
                {/* Time column: 整点行 shows t-hour + t-half; 半点行 empty. */}
                <td className="time-col">
                  {isHourRow && (
                    <>
                      <span className="t-hour">{hoursToLabel(hour)}</span>
                      <span className="t-half">
                        {hoursToLabel(hour + SLOT_STEP)}
                      </span>
                    </>
                  )}
                </td>
                {devices.map((_, deviceIdx) => {
                  const booking = bookingByDeviceSlot.get(
                    `${deviceIdx}:${slotIdx}`,
                  );
                  if (booking) {
                    return (
                      <td key={deviceIdx} className="cell">
                        <BookingBlock booking={booking} />
                      </td>
                    );
                  }
                  // Selection highlight: which class (if any) does THIS cell
                  // get given the active selection? Generalised from the demo's
                  // 45/60 branches so any duration works (D3 — arbitrary int):
                  // walk the slots the selection covers; a slot is full when ≥30
                  // remaining minutes fall in it, half when 0<remaining<30.
                  const selClass = selectionClass(
                    selection,
                    deviceIdx,
                    slotIdx,
                    duration,
                  );

                  const classes = ["cell"];
                  if (isPast) classes.push("disabled");
                  else classes.push("bookable");
                  if (selClass) classes.push(selClass);

                  return (
                    <td
                      key={deviceIdx}
                      className={classes.join(" ")}
                      data-device={deviceIdx}
                      data-slot={slotIdx}
                      onClick={
                        isPast
                          ? undefined
                          : () => handleCellClick(deviceIdx, slotIdx)
                      }
                    />
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** One occupied-cell booking block. Renders the status colour bucket + customer
 * name + meta line + tooltip (data-tooltip, P6). The block anchors on its start
 * slot and extends downward via span-2 / span-1-5 (absolute positioning) for
 * multi-slot bookings — exactly the demo's booking-block + span classes. */
function BookingBlock({ booking }: { booking: BookingHqRead }) {
  // Reuse shared.tsx's ``hhmm`` for the time label (project rule: no local
  // date-format helpers — see lib/format.ts + shared.tsx re-exports). The span
  // math still needs decimal hours, so isoToHours stays for that calculation.
  const startH = isoToHours(booking.scheduled_start_at);
  const endH = isoToHours(booking.scheduled_end_at);
  // Span modifier: drive off the duration's whole minutes (not a rounded slot
  // count — Math.round(1.5)===2 would misclassify 45min as span-2). The demo
  // only styles 60min (span-2) and 45min (span-1-5); other durations render
  // without a span modifier (single-cell block). Mirrors demo verbatim.
  const durationMin = Math.round((endH - startH) * 60);
  const spanClass =
    durationMin === 60 ? "span-2" : durationMin === 45 ? "span-1-5" : "";

  const customer = booking.customer_name ?? "散客";
  const timeLabel = `${hhmm(booking.scheduled_start_at)}-${hhmm(booking.scheduled_end_at)}`;
  const statusInfo = BOOKING_STATUS_GRID[booking.status];
  // tooltip = "customer · service | time | 状态:status" — three pipe-separated
  // segments matching the demo verbatim (P6). The demo's ``service`` field has
  // no direct column on BookingHqRead; ``notes`` is the closest persisted
  // free-text field. When notes is null we fall back to "散客"-style "未填" so
  // the middle segment stays present (preserving the demo's 3-segment shape
  // rather than collapsing to 2 segments).
  const service = booking.notes?.trim() || "未填服务";
  const tooltip = `${customer} · ${service} | ${timeLabel} | 状态:${statusInfo.label}`;

  return (
    <div
      className={`booking-block ${statusInfo.cls} ${spanClass}`.trim()}
      data-tooltip={tooltip}
    >
      <div className="b-customer">{customer}</div>
      <div className="b-meta">
        {timeLabel} · {statusInfo.label}
      </div>
    </div>
  );
}

/** Same local calendar day (year + month + date). Used to decide whether the
 * disabled-past-cell branch applies — only today's cells can be past, future
 * dates render everything bookable (demo D0). */
function isSameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
