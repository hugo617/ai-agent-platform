// customers/ HqView smoke(切片 1 前移,plan-customers-page-split.md §5 切片01 AC1.8)。
//
// 切片 1 只覆盖最关键的渲染 smoke —— 消除「切片 1 完成 = 零测试空窗」,锁住
// customers/ 文件夹结构成立 + HqView 跨店表能渲染 + 行展开生效。完整 store-view
// + hq-view 覆盖(列表/CRUD/usage dialog)在切片 02 补齐。
//
// 范式沿用 devices/__tests__/hq-view.test.tsx 切片 1 smoke 前移范式。
import { describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/test-utils";
import { HqView } from "../hq-view";
import type { CustomerRead } from "@/api/types";

// ---- mock wiring ----
// HqView 调的 hooks:跨店聚合列表 + AI 用量(用量对话框默认关闭,不触发)。
const mocks = vi.hoisted(() => ({
  useCustomers: vi.fn() as Mock,
  useCustomerUsage: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useCustomers: mocks.useCustomers,
  useCustomerUsage: mocks.useCustomerUsage,
}));

// React Router:HqView 用 useSearchParams(client-side filter),CustomerUsageDialog
// 用 useNavigate(「为客户咨询」深链)。renderWithProviders 不包 Router context,
// 所以这里 mock 这两个 hook;useSearchParams 默认返回空 filter。
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
    useNavigate: () => vi.fn(),
  };
});

function makeCustomer(overrides: Partial<CustomerRead> = {}): CustomerRead {
  return {
    id: "c1",
    name: "张三",
    identity_key: "13800000001",
    gender: "male",
    profile_count: 2,
    created_at: "2026-07-01T00:00:00Z",
    profiles: [
      {
        id: "p1",
        status: "active",
        last_visit_at: "2026-07-20T00:00:00Z",
        remark: "常客",
        tags: {},
        tenant: { id: "t1", name: "朝阳店" },
      },
    ],
    ...overrides,
  } as CustomerRead;
}

describe("customers/HqView smoke (slice 01)", () => {
  it("renders cross-store customer list with name, identity_key, profile_count", () => {
    mocks.useCustomers.mockReturnValue({
      data: [makeCustomer(), makeCustomer({ id: "c2", name: "李四", profile_count: 3 })],
      isLoading: false,
    });
    mocks.useCustomerUsage.mockReturnValue({ data: undefined, isLoading: false });

    const { getByText } = renderWithProviders(<HqView />);

    // 列头
    expect(getByText("姓名")).toBeTruthy();
    expect(getByText("手机号/证件号")).toBeTruthy();
    expect(getByText("到店数")).toBeTruthy();
    // 行数据
    expect(getByText("张三")).toBeTruthy();
    expect(getByText("李四")).toBeTruthy();
    expect(getByText("2 家店")).toBeTruthy();
    expect(getByText("3 家店")).toBeTruthy();
  });

  it("renders empty state when no cross-store customers", () => {
    mocks.useCustomers.mockReturnValue({ data: [], isLoading: false });
    mocks.useCustomerUsage.mockReturnValue({ data: undefined, isLoading: false });

    const { getByText } = renderWithProviders(<HqView />);

    expect(getByText("暂无客户")).toBeTruthy();
  });

  it("row expand: click row toggles profile details sub-row", async () => {
    const user = userEvent.setup();
    mocks.useCustomers.mockReturnValue({
      data: [
        makeCustomer({
          profiles: [
            {
              id: "p1",
              status: "vip",
              last_visit_at: "2026-07-20T00:00:00Z",
              remark: "常客",
              tags: {},
              tenant: { id: "t1", name: "朝阳店" },
            },
          ],
        }),
      ],
      isLoading: false,
    });
    mocks.useCustomerUsage.mockReturnValue({ data: undefined, isLoading: false });

    const { queryByText, getByText } = renderWithProviders(<HqView />);

    // 初始:明细未展开(「跨店档案明细」标题不渲染)
    expect(queryByText(/跨店档案明细/)).toBeNull();

    // 点行(chevron 区域)展开
    await user.click(getByText("张三"));
    expect(getByText(/跨店档案明细/)).toBeTruthy();
    expect(getByText("朝阳店")).toBeTruthy();
    expect(getByText("VIP")).toBeTruthy(); // profile status badge
  });

  it("AI usage button: click sets usageTarget (storeScoped=false), opens dialog", async () => {
    const user = userEvent.setup();
    mocks.useCustomers.mockReturnValue({
      data: [makeCustomer()],
      isLoading: false,
    });
    mocks.useCustomerUsage.mockReturnValue({ data: undefined, isLoading: false });

    const { getByText } = renderWithProviders(<HqView />);

    await user.click(getByText("AI 用量"));

    // CustomerUsageDialog 打开,标题含「AI 服务 · 张三」
    expect(getByText(/AI 服务 · 张三/)).toBeTruthy();
    // storeScoped=false → DialogDescription 为「跨全部门店为该客户提供 AI 服务的用量统计」
    expect(
      getByText(/跨全部门店为该客户提供 AI 服务的用量统计/),
    ).toBeTruthy();
  });
});
