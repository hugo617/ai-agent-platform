// MyBookingsView 组件测(device-poweron 切片 02)。
//
// 本项目首个前端组件测。模式(v2 plan AC10):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(否则
//     useMyBookings / useToast 抛 "must be used within Provider")。
//   - ``vi.mock("@/hooks/queries")`` stub useMyBookings / useStartBooking —— 不
//     走真实 axios/网络,断言的是「组件正确调用了 hook」而非「后端返回什么」
//     (后端契约由 pytest 覆盖,组件测只验 UI 接线)。
//   - user-event@14 模拟点击(比 fireEvent 更贴近真实交互)。
//
// 覆盖:vitest 基建跑通 + customer「确认开机」按钮渲染/调用/toast/禁用/非 pending 隐藏。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { MyBookingsView } from "../my-bookings-view";
import type { Booking } from "@/api/types";

// ---- helpers ----
// ``vi.mock`` hoists to top of file (vitest 的 transform 行为),故用
// ``vi.hoisted`` 把 mock 工厂里要引用的变量提到 hoist 作用域,避免 TDZ。
const mocks = vi.hoisted(() => ({
  useMyBookings: vi.fn() as Mock,
  useStartBooking: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useMyBookings: mocks.useMyBookings,
  useStartBooking: mocks.useStartBooking,
}));

function makeBooking(overrides: Partial<Booking> = {}): Booking {
  const now = "2026-07-24T10:00:00Z";
  return {
    id: "bk_1",
    tenant_id: "tn_1",
    device_id: "dev_abcdef12",
    customer_id: "cu_1",
    created_by: "cu_1",
    status: "pending",
    scheduled_start_at: "2026-07-24T10:00:00Z",
    scheduled_end_at: "2026-07-24T11:00:00Z",
    started_at: null,
    ended_at: null,
    feedback: null,
    notes: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

// 一个标准的「可开机」mutation stub:resolve 立即成功,isPending 默认 false。
function makeStartMut(overrides: Partial<{ isPending: boolean }> = {}) {
  return {
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    ...overrides,
  };
}

afterEach(() => vi.clearAllMocks());

describe("MyBookingsView — customer 确认开机", () => {
  it("pending 行渲染「确认开机」按钮", () => {
    mocks.useMyBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_pending" })],
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(makeStartMut());

    const { getByRole } = renderWithProviders(<MyBookingsView />);
    expect(
      getByRole("button", { name: "确认开机" }),
    ).toBeInTheDocument();
  });

  it("点击「确认开机」触发 startBooking(id)", async () => {
    const user = userEvent.setup();
    const startMut = makeStartMut();
    mocks.useMyBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_click" })],
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(startMut);

    const { getByRole } = renderWithProviders(<MyBookingsView />);
    await user.click(getByRole("button", { name: "确认开机" }));

    expect(startMut.mutateAsync).toHaveBeenCalledWith("bk_click");
  });

  it("开机成功后显示「已开机」toast", async () => {
    const user = userEvent.setup();
    mocks.useMyBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_ok" })],
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(makeStartMut());

    const { getByRole, getByText } = renderWithProviders(<MyBookingsView />);
    await user.click(getByRole("button", { name: "确认开机" }));

    // toast.success("已开机") push 进 DOM(标题文本即「已开机」)。
    expect(getByText("已开机")).toBeInTheDocument();
  });

  it("非 pending 行(已开机/已完成/已取消/爽约/已确认)不渲染按钮", () => {
    // 按 spec L259:in_service/done/cancelled/no_show/confirmed 均无按钮。
    // 含 confirmed —— 它是前向兼容占位态(运行期不可达),但 spec 明文
    // 要求不渲染,故纳入断言集防回归。
    const others: Booking["status"][] = [
      "in_service",
      "done",
      "cancelled",
      "no_show",
      "confirmed",
    ];
    mocks.useMyBookings.mockReturnValue({
      data: others.map((status, i) =>
        makeBooking({ status, id: `bk_${status}_${i}` }),
      ),
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(makeStartMut());

    const { queryByRole } = renderWithProviders(<MyBookingsView />);
    expect(queryByRole("button", { name: "确认开机" })).toBeNull();
  });

  it("mutation isPending 时按钮 disabled", () => {
    mocks.useMyBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_disabled" })],
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(makeStartMut({ isPending: true }));

    const { getByRole, queryByRole } = renderWithProviders(<MyBookingsView />);
    // 渲染了按钮(还在 pending 行),但被禁用。
    const btn = getByRole("button", { name: "确认开机" });
    expect(btn).toBeDisabled();
    // 同时无「操作」列以外多余按钮(防御:整页只此一个按钮)。
    expect(queryByRole("button")).toBe(btn);
  });

  it("多行时仅 pending 行有按钮,终态行无", () => {
    mocks.useMyBookings.mockReturnValue({
      data: [
        makeBooking({ status: "pending", id: "bk_p" }),
        makeBooking({ status: "in_service", id: "bk_is" }),
        makeBooking({ status: "done", id: "bk_done" }),
      ],
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(makeStartMut());

    const { getAllByRole } = renderWithProviders(<MyBookingsView />);
    const buttons = getAllByRole("button", { name: "确认开机" });
    expect(buttons).toHaveLength(1);
    // 该按钮位于 pending 行(tr)内 —— 间接证明只有那一行有。
    const row = buttons[0].closest("tr");
    expect(row && within(row).getByText("待确认")).toBeInTheDocument();
  });
});
