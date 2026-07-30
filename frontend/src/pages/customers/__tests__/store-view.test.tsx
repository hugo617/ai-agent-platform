// StoreView 组件测(customers-page-split 切片 02)。
//
// 模式沿用 devices/__tests__/store-view.test.tsx(已落地的 vitest 基建):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider。
//   - ``vi.mock("@/hooks/queries")`` stub 写 hooks,断言「组件正确调用 hook」
//     而非「后端返回什么」(后端契约由 pytest 覆盖)。
//   - ``vi.mock("@/components/auth/auth-context")`` 注入 owner/member me 变体,
//     驱动 canCreate/canDelete 守卫(用真实 hasPermission,permissions 是
//     ``string[]`` 如 "customers:create")。
//   - user-event@14 模拟点击;DropdownMenu 项异步 portal 挂载,await findByText。
//
// 覆盖(plan-customers-page-split.md §5 切片02 AC2.1):列表渲染 + member 只读守卫
// + owner 创建 Dialog 填表提交(断言 tags 经 parseTagsJson 解析)+ 删除菜单。
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { StoreView } from "../store-view";
import type { CustomerProfileRead, MeResponse } from "@/api/types";

// ---- mock wiring ----
const mocks = vi.hoisted(() => ({
  useCustomerProfiles: vi.fn() as Mock,
  useCreateCustomerProfile: vi.fn() as Mock,
  useUpdateCustomerProfile: vi.fn() as Mock,
  useDeleteCustomerProfile: vi.fn() as Mock,
  useCustomerUsage: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useCustomerProfiles: mocks.useCustomerProfiles,
  useCreateCustomerProfile: mocks.useCreateCustomerProfile,
  useUpdateCustomerProfile: mocks.useUpdateCustomerProfile,
  useDeleteCustomerProfile: mocks.useDeleteCustomerProfile,
  useCustomerUsage: mocks.useCustomerUsage,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// 真实 hasPermission 读 me.permissions.includes("obj:act");不 mock permission,
// 用真实实现 + 正确的 permissions: string[] 结构驱动守卫。

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

// ExportCsvButton 内部走 useQueryClient(真实 fetch),mock 掉避免网络。
vi.mock("@/components/ui/export-csv-button", () => ({
  ExportCsvButton: () => <button type="button">导出 CSV</button>,
}));

// ---- factories ----
function makeProfile(
  overrides: Partial<CustomerProfileRead> = {},
): CustomerProfileRead {
  return {
    id: "p1",
    customer_id: "c_global_1",
    status: "active",
    remark: "常客",
    last_visit_at: "2026-07-20T00:00:00Z",
    tags: null,
    customer: {
      id: "c_global_1",
      identity_key: "13800000001",
      name: "张三",
      gender: "male",
      birthday: "1990-01-01",
      avatar: null,
    },
    ...overrides,
  } as CustomerProfileRead;
}

// owner:含 customers 的 create/update/delete 权限码。member:只有 read。
function makeOwnerMe(): MeResponse {
  return {
    user_id: "u_owner",
    tenant_id: "t1",
    email: null,
    platform_role: null,
    roles: ["owner"],
    permissions: ["customers:read", "customers:create", "customers:update", "customers:delete"],
    customer_id: null,
  } as MeResponse;
}
function makeMemberMe(): MeResponse {
  return {
    user_id: "u_member",
    tenant_id: "t1",
    email: null,
    platform_role: null,
    roles: ["member"],
    permissions: ["customers:read"],
    customer_id: null,
  } as MeResponse;
}

// stubMutation():返回带 mutateAsync/isPending 的假 hook。
function stubMutation() {
  return { mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: false };
}

beforeEach(() => {
  mocks.useCustomerProfiles.mockReturnValue({ data: [], isLoading: false });
  mocks.useCreateCustomerProfile.mockReturnValue(stubMutation());
  mocks.useUpdateCustomerProfile.mockReturnValue(stubMutation());
  mocks.useDeleteCustomerProfile.mockReturnValue(stubMutation());
  mocks.useCustomerUsage.mockReturnValue({ data: undefined, isLoading: false });
});

afterEach(() => vi.clearAllMocks());

describe("customers/StoreView (slice 02)", () => {
  it("renders profile list with name, identity_key, status badge, gender label", () => {
    mocks.useAuth.mockReturnValue({ me: makeOwnerMe() });
    mocks.useCustomerProfiles.mockReturnValue({
      data: [
        makeProfile(),
        makeProfile({
          id: "p2",
          customer: {
            id: "c2",
            identity_key: "13900000002",
            name: "李四",
            gender: "female",
            birthday: null,
            avatar: null,
          },
          status: "vip",
        }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<StoreView />);

    expect(getByText("张三")).toBeTruthy();
    expect(getByText("13800000001")).toBeTruthy();
    expect(getByText("男")).toBeTruthy();
    expect(getByText("李四")).toBeTruthy();
    expect(getByText("VIP")).toBeTruthy(); // statusBadge vip
    expect(getByText("活跃")).toBeTruthy(); // statusBadge active
  });

  it("renders empty state when no profiles", () => {
    mocks.useAuth.mockReturnValue({ me: makeOwnerMe() });
    mocks.useCustomerProfiles.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<StoreView />);

    expect(getByText("暂无客户")).toBeTruthy();
  });

  it("member (read-only guard): no 新增 button, no 操作 column header, 只读 hint shown", () => {
    mocks.useAuth.mockReturnValue({ me: makeMemberMe() });
    mocks.useCustomerProfiles.mockReturnValue({
      data: [makeProfile()],
      isLoading: false,
    });

    const { queryByText, queryAllByText } = renderWithProviders(<StoreView />);

    expect(queryByText("新增客户")).toBeNull(); // canCreate=false → 无创建按钮
    // CardDescription 文本跨节点,用正则匹配「只读视图」片段
    expect(queryAllByText(/只读视图/).length).toBeGreaterThan(0);
    expect(queryByText("操作")).toBeNull(); // 操作列表头 canCreate 守卫
    expect(queryByText("张三")).not.toBeNull(); // 但列表数据仍渲染
  });

  it("owner create: open dialog, fill form, submit → useCreateCustomerProfile.mutateAsync called with parsed tags", async () => {
    const user = userEvent.setup();
    mocks.useAuth.mockReturnValue({ me: makeOwnerMe() });
    const createMut = stubMutation();
    mocks.useCreateCustomerProfile.mockReturnValue(createMut);

    const { getByRole } = renderWithProviders(<StoreView />);

    await user.click(getByRole("button", { name: "新增客户" }));

    // Dialog 内容 portal 挂在 body,用 within(body) 限定查询范围。
    const body = document.body;
    // 填表:identity_key(placeholder 定位)
    const identityInput = within(body).getByPlaceholderText(
      "如：138xxxx",
    ) as HTMLInputElement;
    await user.type(identityInput, "13700000003");

    // name 输入框:FormField 的 Label「姓名 *」与 input 在同一 div,通过 label
    // 文本定位父容器再取其中的 input(FormField 未给 input 关联 htmlFor/aria-label)。
    const nameLabels = await within(body).findAllByText("姓名 *");
    const nameField = nameLabels[0].closest("div")?.querySelector("input");
    const nameInput = nameField as HTMLInputElement;
    await user.type(nameInput, "王五");

    // tags_json:合法 JSON。userEvent.type 把 { 当特殊修饰符,改用 fireEvent
    // 直接设 value + input 事件触发 react-hook-form register 的 onChange。
    const tagsTextarea = within(body).getByPlaceholderText(
      '{"level": "vip", "source": "walk-in"}',
    ) as HTMLTextAreaElement;
    fireEvent.change(tagsTextarea, { target: { value: '{"level":"vip"}' } });

    await user.click(getByRole("button", { name: "创建" }));

    expect(createMut.mutateAsync).toHaveBeenCalledTimes(1);
    const payload = createMut.mutateAsync.mock.calls[0][0];
    expect(payload.identity_key).toBe("13700000003");
    expect(payload.name).toBe("王五");
    // D4 核心:tags 经 parseTagsJson 正确解析(非原始字符串)
    expect(payload.tags).toEqual({ level: "vip" });
  });

  it("row menu: delete item triggers deleteMut.mutateAsync", async () => {
    const user = userEvent.setup();
    mocks.useAuth.mockReturnValue({ me: makeOwnerMe() });
    const deleteMut = stubMutation();
    mocks.useDeleteCustomerProfile.mockReturnValue(deleteMut);
    mocks.useCustomerProfiles.mockReturnValue({
      data: [makeProfile()],
      isLoading: false,
    });

    const { findByText } = renderWithProviders(<StoreView />);

    // 点行菜单 trigger(DropdownMenu 的 menu button,aria-haspopup="menu")
    const trigger = document.querySelector(
      '[aria-haspopup="menu"]',
    ) as Element;
    await user.click(trigger);

    // 点「删除档案」→ 弹确认 Dialog → 点确认「删除」
    const deleteItem = await findByText("删除档案");
    await user.click(deleteItem);
    const confirmBtn = await findByText("删除");
    await user.click(confirmBtn);

    expect(deleteMut.mutateAsync).toHaveBeenCalledTimes(1);
    expect(deleteMut.mutateAsync.mock.calls[0][0]).toBe("p1"); // profile id
  });
});
