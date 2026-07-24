// HqView 组件测 smoke(bookings-page-split 重构补测)。
//
// HqView 在原 bookings-page.tsx 里是私有函数(未 export),拆分到独立
// module 后首次可测。这里补 smoke 覆盖:渲染跨店表 / 列头 / 空态 /
// tenant_name+device_name+customer_name 显示(含 null fallback)。
//
// 模式沿用 store-view.test.tsx / my-bookings-view.test.tsx 的 vitest 基建:
// ``renderWithProviders`` + ``vi.mock("@/hooks/queries")`` stub useBookings
// (HqView 唯一 hook)。
//
// 注:HqView 是只读视图,无 write 操作,故无 mutation mock / user-event,
// 纯渲染断言。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { renderWithProviders } from "@/test/test-utils";
import { HqView } from "../hq-view";
import type { BookingHqRead } from "@/api/types";

// ---- mock wiring ----
const mocks = vi.hoisted(() => ({
  useBookings: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useBookings: mocks.useBookings,
}));

// ---- factory ----
function makeHqBooking(overrides: Partial<BookingHqRead> = {}): BookingHqRead {
  return {
    id: "b-1",
    tenant_id: "t-1",
    tenant_name: "华东大区·上海徐汇店",
    device_id: "d-1",
    device_name: "DEVICE-001",
    customer_id: "c-1",
    customer_name: "张三",
    scheduled_start_at: "2026-07-25T10:00:00Z",
    scheduled_end_at: "2026-07-25T11:00:00Z",
    status: "pending",
    notes: null,
    created_at: "2026-07-24T09:00:00Z",
    ...overrides,
  } as BookingHqRead;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("HqView — cross-tenant panorama smoke", () => {
  it("渲染跨店表 + 列头 + 行数据(tenant_name/device_name/customer_name)", () => {
    mocks.useBookings.mockReturnValue({
      data: [
        makeHqBooking(),
        makeHqBooking({
          id: "b-2",
          tenant_name: "华北大区·北京朝阳店",
          device_name: "DEVICE-002",
          customer_name: "李四",
        }),
      ],
      isLoading: false,
    });

    const { getAllByRole, getByText } = renderWithProviders(<HqView />);

    // 列头
    expect(getByText("所属门店")).toBeTruthy();
    expect(getByText("设备")).toBeTruthy();
    expect(getByText("客户")).toBeTruthy();
    expect(getByText("预约时段")).toBeTruthy();

    // 行数据(2 行)
    const rows = getAllByRole("row");
    // 1 header + 2 body
    expect(rows.length).toBe(3);
    expect(getByText("华东大区·上海徐汇店")).toBeTruthy();
    expect(getByText("DEVICE-002")).toBeTruthy();
    expect(getByText("李四")).toBeTruthy();
    // PageHeader 标题
    expect(getByText("预约（总部视图）")).toBeTruthy();
  });

  it("空态:无预约时渲染 EmptyState + 总数 0", () => {
    mocks.useBookings.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<HqView />);

    expect(getByText("共 0 条预约（跨全部门店）")).toBeTruthy();
    expect(getByText("暂无预约")).toBeTruthy();
    expect(
      getByText("跨全部门店暂无设备预约"),
    ).toBeTruthy();
  });

  it("null fallback:tenant_name/device_name/customer_name 缺失时显示兜底文案", () => {
    // tenant_name null(门店硬删,CASCADE 下不可达但守卫显示安全)+ walk-in
    // (customer_id null → customer_name null → "散客")+ device_name null
    // (设备软删的瞬时态)。
    mocks.useBookings.mockReturnValue({
      data: [
        makeHqBooking({
          tenant_name: null,
          device_name: null,
          customer_id: null,
          customer_name: null,
        }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<HqView />);

    expect(getByText("（门店已删除）")).toBeTruthy();
    // device_name null + device_id 存在 → "设备(<id前缀>)"
    expect(getByText(/设备\(d-1\)/)).toBeTruthy();
    expect(getByText("散客(walk-in)")).toBeTruthy();
  });
});
