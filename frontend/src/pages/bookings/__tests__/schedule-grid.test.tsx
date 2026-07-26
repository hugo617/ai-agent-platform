/**
 * ScheduleGrid tests (booking-schedule-grid 切片 04a).
 *
 * Seam: the grid is a PURE presentational component (no react-query, no auth
 * context) — it receives devices + bookings + config + selectedDate + now as
 * props and calls ``onSlotClick`` on a click. We drive it by passing props +
 * spying on ``onSlotClick``, with NO ``vi.mock("@/hooks/queries")``. This is
 * the agreed seam (plan §切片 04a AC: "纯展示 + 点击回调,不含数据获取").
 *
 * now is prop-injected (D6, not fake timers), so each test pins the clock by
 * passing a literal Date. jsdom can't :hover, so tooltip coverage asserts on
 * the ``data-tooltip`` attribute (P6), not on pseudo-class triggering.
 *
 * CSS class names are kept identical to harness/demo/booking-schedule-grid-demo.html
 * and used as test selectors (P5): selected-full / selected-half / span-2 /
 * span-1-5 / disabled / booking-block.st-pending|st-confirmed|st-inservice|
 * st-done|st-cancel.
 *
 * 10 用例覆盖 plan 切片 04a AC:
 *  1. 空网格渲染(左上角斜线分隔标签 + 设备表头 + 时间行数 = window)
 *  2. 无设备 → 空态文案
 *  3. 占用 cell:状态色块 class + 客户名
 *  4. 跨行 span:60 分钟 → span-2,45 分钟 → span-1-5
 *  5. 已过时间禁用(用 now prop):今天早于 now 的 cell 带 disabled class
 *  6. 未来日期:全可点(无 disabled)
 *  7. 点击空 cell → onSlotClick 以 device + startISO + endISO 调用
 *  8. 点击已占用 cell → 不触发 onSlotClick
 *  9. 45 分钟高亮:点击 → selected-full + 下一行 selected-half
 *  10. 父传新 config(window 变化)→ 行数变化(纯组件 props 驱动)+ hover tooltip data-tooltip
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";

import { renderWithProviders } from "@/test/test-utils";
import { ScheduleGrid } from "../schedule-grid";
import type {
  BookingConfig,
  BookingHqRead,
  DeviceHqRead,
} from "@/api/types";

// ---- fixtures ---------------------------------------------------------------
// selectedDate 固定为 2026-07-25(一个虚构的「今天」);now 注入该日中午 12:00,
// 这样 08:00-11:30 的 slot 已过(禁用),13:00+ 可点。
const SELECTED_DATE = new Date(2026, 6, 25); // 2026-07-25 local
const NOW_NOON = new Date(2026, 6, 25, 12, 0, 0); // 2026-07-25 12:00 local

const DEFAULT_CONFIG: BookingConfig = {
  id: "cfg_1",
  tenant_id: null,
  default_duration_minutes: 45,
  window_start: "08:00",
  window_end: "22:00",
  created_at: "2026-07-20T00:00:00",
  updated_at: "2026-07-20T00:00:00",
};

function makeDevice(overrides: Partial<DeviceHqRead> = {}): DeviceHqRead {
  return {
    id: "d-1",
    tenant_id: "t-1",
    model_id: "m-1",
    serial_number: "DEV-001",
    status: "active",
    customer_id: null,
    created_by: null,
    tenant_name: "测试店",
    model_name: "理疗床 X1",
    customer_name: null,
    created_at: "2026-07-20T00:00:00",
    updated_at: "2026-07-20T00:00:00",
    ...overrides,
  } as DeviceHqRead;
}

/** Build a booking whose scheduled_start_at / scheduled_end_at fall on
 * SELECTED_DATE at the given wall-clock hours (local). 9 = 09:00, 9.5 = 09:30. */
function makeBooking(
  hourStart: number,
  hourEnd: number,
  overrides: Partial<BookingHqRead> = {},
): BookingHqRead {
  const toIso = (h: number) => {
    const hh = Math.floor(h);
    const mm = Math.round((h - hh) * 60);
    const d = new Date(SELECTED_DATE);
    d.setHours(hh, mm, 0, 0);
    return d.toISOString();
  };
  return {
    id: "b-1",
    tenant_id: "t-1",
    tenant_name: "测试店",
    device_id: "d-1",
    device_name: "DEV-001",
    customer_id: "c-1",
    customer_name: "张三",
    scheduled_start_at: toIso(hourStart),
    scheduled_end_at: toIso(hourEnd),
    status: "pending",
    created_by: null,
    started_at: null,
    ended_at: null,
    feedback: null,
    notes: null,
    created_at: "2026-07-24T00:00:00",
    updated_at: "2026-07-24T00:00:00",
    ...overrides,
  } as BookingHqRead;
}

afterEach(() => vi.clearAllMocks());

describe("ScheduleGrid", () => {
  it("渲染:左上角斜线分隔标签 + 设备表头 + 时间行数对齐 config window", () => {
    const devices = [makeDevice()];
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={devices}
        bookings={[]}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );

    // 左上角交叉格:「设备 →」+「← 时间」(AC: 左上角斜线分隔)
    expect(container.querySelector(".corner .lbl-device")).not.toBeNull();
    expect(container.querySelector(".corner .lbl-time")).not.toBeNull();

    // 设备表头:大设备名(model_name,贴近 demo 的「理疗床 1」语义)+ 序列号
    // 小字 + 状态圆点(AC: 卡片式表头)。model_name 缺省时回退 serial_number。
    const deviceCol = container.querySelector("th.device-col");
    expect(deviceCol).not.toBeNull();
    expect(deviceCol!.querySelector(".d-name")?.textContent).toBe("理疗床 X1");
    expect(deviceCol!.querySelector(".d-id")?.textContent).toBe("DEV-001");
    expect(deviceCol!.querySelector(".d-status-dot")).not.toBeNull();

    // 时间行数 = (22-8)/0.5 = 28(AC: 28 行按 config window)
    const timeRows = container.querySelectorAll("tbody tr");
    expect(timeRows.length).toBe(28);

    // 整点大字 + 半点淡色(AC):第一行(08:00)time-col 含 t-hour + t-half
    const firstTimeCol = timeRows[0].querySelector(".time-col");
    expect(firstTimeCol?.querySelector(".t-hour")?.textContent).toBe("08:00");
    expect(firstTimeCol?.querySelector(".t-half")?.textContent).toBe("08:30");
  });

  it("无设备 → 渲染空态文案「该门店暂无可用设备」(AC)", () => {
    const { getByText } = renderWithProviders(
      <ScheduleGrid
        devices={[]}
        bookings={[]}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );
    expect(getByText(/该门店暂无可用设备/)).toBeInTheDocument();
  });

  it("占用 cell:渲染状态色块 class + 客户名(AC: 已占用 = 状态色块)", () => {
    // 09:00-10:00 pending booking on device d-1
    const bookings = [makeBooking(9, 10, { status: "pending" })];
    const { container, getByText } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={bookings}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );

    // booking-block 带 st-pending class(P5 selector)
    const block = container.querySelector(".booking-block.st-pending");
    expect(block).not.toBeNull();
    // 客户名渲染
    expect(getByText("张三")).toBeInTheDocument();
  });

  it("跨行 span:60 分钟 → span-2,45 分钟 → span-1-5(AC: 跨行预约)", () => {
    // 60 分钟(2 cell):09:00-10:00
    const bookings60 = [makeBooking(9, 10, { status: "confirmed" })];
    const { container: c60 } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={bookings60}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );
    // 60min = 2 slots → span-2 class
    expect(c60.querySelector(".booking-block.span-2")).not.toBeNull();
    // 确认是 confirmed 状态
    expect(c60.querySelector(".booking-block.st-confirmed")).not.toBeNull();

    // 45 分钟(1.5 cell):11:00-11:45
    const bookings45 = [
      makeBooking(11, 11.75, { status: "in_service", id: "b-45" }),
    ];
    const { container: c45 } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={bookings45}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );
    // 45min = 1.5 slots → span-1-5 class
    expect(c45.querySelector(".booking-block.span-1-5")).not.toBeNull();
    expect(c45.querySelector(".booking-block.st-inservice")).not.toBeNull();
  });

  it("今天早于 now 的 cell 带 disabled class;晚于 now 的 cell 可点(AC: 已过时间禁用)", () => {
    // now = 12:00 → 11:30 slot 已过(disabled),13:00 slot 可点(bookable)
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={[]}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE} // = 今天(与 now 同日)
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );

    // slot idx 7 = 08:00 + 7*0.5 = 11:30(< 12:00 → disabled)
    const cell1130 = container.querySelector(
      'td.cell[data-device="0"][data-slot="7"]',
    );
    expect(cell1130?.classList.contains("disabled")).toBe(true);
    expect(cell1130?.classList.contains("bookable")).toBe(false);

    // slot idx 10 = 08:00 + 10*0.5 = 13:00(> 12:00 → bookable)
    const cell1300 = container.querySelector(
      'td.cell[data-device="0"][data-slot="10"]',
    );
    expect(cell1300?.classList.contains("bookable")).toBe(true);
    expect(cell1300?.classList.contains("disabled")).toBe(false);
  });

  it("未来日期:所有 cell 可点(无 disabled)(AC: 未来日期全可点)", () => {
    // selectedDate = 明天,now = 今天中午 → 全部 bookable
    const tomorrow = new Date(2026, 6, 26);
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={[]}
        config={DEFAULT_CONFIG}
        selectedDate={tomorrow}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );
    // 任意一个早 slot(08:00, idx 0)应可点,非 disabled
    const cell0800 = container.querySelector(
      'td.cell[data-device="0"][data-slot="0"]',
    );
    expect(cell0800?.classList.contains("bookable")).toBe(true);
    expect(cell0800?.classList.contains("disabled")).toBe(false);
  });

  it("点击空 cell → onSlotClick 以 device + startISO + endISO 调用(AC)", () => {
    const onSlotClick = vi.fn();
    const device = makeDevice();
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={[device]}
        bookings={[]}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={onSlotClick}
      />,
    );

    // 点 13:00 slot(idx 10,bookable)→ duration 45min → end = 13:45
    const cell1300 = container.querySelector(
      'td.cell.bookable[data-device="0"][data-slot="10"]',
    )!;
    fireEvent.click(cell1300);

    expect(onSlotClick).toHaveBeenCalledTimes(1);
    const [argDevice, argStart, argEnd] = onSlotClick.mock.calls[0];
    expect(argDevice).toBe(device);
    // start = 13:00 local on selectedDate — verify via parsed local hour/min
    // (the ISO string is UTC-suffixed; its wall-clock rendering depends on the
    // runner's TZ, so assert on the parsed-local value, not the raw string).
    const startD = new Date(argStart);
    expect(startD.getHours()).toBe(13);
    expect(startD.getMinutes()).toBe(0);
    // end = 13:45(duration 45min)
    const endD = new Date(argEnd);
    expect(endD.getHours()).toBe(13);
    expect(endD.getMinutes()).toBe(45);
  });

  it("点击已占用 cell → 不触发 onSlotClick(AC: 已占用不可点)", () => {
    const onSlotClick = vi.fn();
    // 09:00-10:00 booking on device 0
    const bookings = [makeBooking(9, 10, { status: "pending" })];
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={bookings}
        config={DEFAULT_CONFIG}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={onSlotClick}
      />,
    );

    // booking-block 不带 bookable class,且 cursor not-allowed;点击它不触发
    const block = container.querySelector(".booking-block")!;
    fireEvent.click(block);
    expect(onSlotClick).not.toHaveBeenCalled();
  });

  it("45 分钟高亮:点击空 cell → 当前 slot selected-full + 下一 slot selected-half(AC)", () => {
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={[]}
        config={DEFAULT_CONFIG} // duration=45
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );

    // 点 13:00 slot(idx 10)
    const cell1300 = container.querySelector(
      'td.cell.bookable[data-device="0"][data-slot="10"]',
    )!;
    fireEvent.click(cell1300);

    // 当前 slot(idx 10)→ selected-full
    expect(
      cell1300.classList.contains("selected-full"),
    ).toBe(true);
    // 下一 slot(idx 11)→ selected-half(45min = 1 整 + 1 半)
    const cell1330 = container.querySelector(
      'td.cell[data-device="0"][data-slot="11"]',
    )!;
    expect(cell1330.classList.contains("selected-half")).toBe(true);
  });

  it("60 分钟高亮:duration=60 点击 → 当前 + 下一 slot 均 selected-full(AC)", () => {
    const config60: BookingConfig = { ...DEFAULT_CONFIG, default_duration_minutes: 60 };
    const { container } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={[]}
        config={config60}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );

    // 点 13:00 slot(idx 10)
    const cell1300 = container.querySelector(
      'td.cell.bookable[data-device="0"][data-slot="10"]',
    )!;
    fireEvent.click(cell1300);

    // 当前 slot(idx 10)+ 下一 slot(idx 11)均 selected-full(60min = 2 整行)
    expect(cell1300.classList.contains("selected-full")).toBe(true);
    const cell1330 = container.querySelector(
      'td.cell[data-device="0"][data-slot="11"]',
    )!;
    expect(cell1330.classList.contains("selected-full")).toBe(true);
    // 不应有 selected-half(60min 不产生半行)
    expect(cell1330.classList.contains("selected-half")).toBe(false);
  });

  it("config 变化(window 缩短)→ 行数变化 + tooltip 内容正确(纯组件 props 驱动)", () => {
    // 用 09:00-21:00 window,期望 (21-9)/0.5 = 24 行
    const shortConfig: BookingConfig = {
      ...DEFAULT_CONFIG,
      window_start: "09:00",
      window_end: "21:00",
    };
    // 10:00-11:00 confirmed booking with customer_name + service in notes
    const bookings = [
      makeBooking(10, 11, {
        status: "confirmed",
        customer_name: "李四",
        notes: "肩颈理疗",
        id: "b-cfg",
      }),
    ];
    const { container, rerender } = renderWithProviders(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={bookings}
        config={shortConfig}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );

    // 行数 = 24(09:00-21:00,每 30 分钟)
    expect(container.querySelectorAll("tbody tr").length).toBe(24);

    // 第一行时间列 = 09:00(window_start 对齐)
    const firstTimeCol = container.querySelector("tbody tr .time-col");
    expect(firstTimeCol?.querySelector(".t-hour")?.textContent).toBe("09:00");

    // tooltip data-tooltip 含客户名 + 时段 + 状态(P6: 断言 attribute,不测 :hover)
    const block = container.querySelector(".booking-block")!;
    const tooltip = block.getAttribute("data-tooltip") ?? "";
    expect(tooltip).toContain("李四");
    expect(tooltip).toContain("10:00-11:00");
    expect(tooltip).toContain("已确认"); // bookingStatusText

    // rerender 同 props 确保 stable(纯组件无副作用)
    rerender(
      <ScheduleGrid
        devices={[makeDevice()]}
        bookings={bookings}
        config={shortConfig}
        selectedDate={SELECTED_DATE}
        now={NOW_NOON}
        onSlotClick={() => {}}
      />,
    );
    expect(container.querySelectorAll("tbody tr").length).toBe(24);
  });
});
