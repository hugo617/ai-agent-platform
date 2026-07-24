// StoreView 组件测(device-poweron 切片 03)。
//
// 模式沿用 my-bookings-view.test.tsx(切片 02 落地的 vitest 基建):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(否则
//     useBookings / useEndBooking / useToast 抛 "must be used within Provider")。
//   - ``vi.mock("@/hooks/queries")`` stub 写 hooks —— 不走真实 axios/网络,
//     断言的是「组件正确调用了 hook」而非「后端返回什么」(后端契约由 pytest 覆盖)。
//   - ``vi.mock("@/components/auth/auth-context")`` 注入不同 me 变体(owner /
//     member),驱动按钮的 ``canUpdate``/``canCancel`` 守卫。
//   - user-event@14 模拟点击(比 fireEvent 更贴近真实交互)。DropdownMenu 项
//     在 Radix 中是异步 portal 挂载,点开后再 await findByText 拿菜单项。
//
// 覆盖(spec L279):确认开机 walk-in / 结束 + feedback / 爽约 + 确认 / 终态无按钮 /
// member 无写按钮(canUpdate+canDelete 均假)。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { StoreView } from "../store-view";
import type { Booking, MeResponse } from "@/api/types";

// ---- mock wiring ----
// ``vi.mock`` 工厂在 hoist 作用域执行,引用的变量必须用 ``vi.hoisted`` 提前。
const mocks = vi.hoisted(() => ({
  useBookings: vi.fn() as Mock,
  useDevices: vi.fn() as Mock,
  useCustomerProfiles: vi.fn() as Mock,
  useCreateBooking: vi.fn() as Mock,
  useUpdateBooking: vi.fn() as Mock,
  useCancelBooking: vi.fn() as Mock,
  useStartBooking: vi.fn() as Mock,
  useEndBooking: vi.fn() as Mock,
  useNoShowBooking: vi.fn() as Mock,
  // ScheduleGridCard(StoreView 内嵌)用的 read hook,测不关心 grid 数据,
  // 喂一个空数据的 stub 即可。
  useDeviceSchedule: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useBookings: mocks.useBookings,
  useDevices: mocks.useDevices,
  useCustomerProfiles: mocks.useCustomerProfiles,
  useCreateBooking: mocks.useCreateBooking,
  useUpdateBooking: mocks.useUpdateBooking,
  useCancelBooking: mocks.useCancelBooking,
  useStartBooking: mocks.useStartBooking,
  useEndBooking: mocks.useEndBooking,
  useNoShowBooking: mocks.useNoShowBooking,
  useDeviceSchedule: mocks.useDeviceSchedule,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// ---- factories ----
function makeBooking(overrides: Partial<Booking> = {}): Booking {
  const now = "2026-07-24T10:00:00Z";
  return {
    id: "bk_1",
    tenant_id: "tn_1",
    device_id: "dev_abcdef12",
    customer_id: null, // 默认 walk-in(B4 用户故事#4)
    created_by: null,
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

// owner me:含 update + delete 权限。member me:只有 read(无 update/delete)。
function makeOwnerMe(): MeResponse {
  return {
    user_id: "u_owner",
    tenant_id: "tn_1",
    email: "owner@example.com",
    platform_role: null,
    roles: ["owner"],
    permissions: ["bookings:read", "bookings:create", "bookings:update", "bookings:delete"],
    customer_id: null,
  };
}
function makeMemberMe(): MeResponse {
  return {
    user_id: "u_member",
    tenant_id: "tn_1",
    email: "member@example.com",
    platform_role: null,
    roles: ["member"],
    permissions: ["bookings:read"],
    customer_id: null,
  };
}

// 一个标准的 mutation stub:resolve 立即成功,isPending 默认 false。
function makeMut(overrides: Partial<{ isPending: boolean }> = {}) {
  return {
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    ...overrides,
  };
}

// 把所有 use* hooks 喂成稳定 stub,避免每个用例重复设置。``me`` 决定按钮可见性。
function stubStoreBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useBookings.mockReturnValue({ data: [], isLoading: false });
  mocks.useDevices.mockReturnValue({ data: [] });
  mocks.useCustomerProfiles.mockReturnValue({ data: [] });
  mocks.useCreateBooking.mockReturnValue(makeMut());
  mocks.useUpdateBooking.mockReturnValue(makeMut());
  mocks.useCancelBooking.mockReturnValue(makeMut());
  mocks.useStartBooking.mockReturnValue(makeMut());
  mocks.useEndBooking.mockReturnValue(makeMut());
  mocks.useNoShowBooking.mockReturnValue(makeMut());
  mocks.useDeviceSchedule.mockReturnValue({ data: {}, isLoading: false });
}

afterEach(() => vi.clearAllMocks());

// 触发器按钮是 MoreHorizontal(无 accessible name 的 icon-only ghost Button)。
// 页面同时有 FilterChips + 「创建预约」等按钮,直接 get 全页 button 会撞多个。
// 思路:按行内 status label 文本定位 <tr>,再在行 scope 找唯一的 button(trigger)。
// Radix DropdownMenu 把菜单项 portal 挂到 body 末端,菜单项异步出现 —— 用
// ``findByText`` 等它出现后再点。
async function openRowMenu(
  user: ReturnType<typeof userEvent.setup>,
  body: HTMLElement,
  rowIndex: number = 0,
) {
  // 行 trigger(MoreHorizontal icon button)是 tbody 内唯一的 button ——
  // PageHeader「创建预约」+ FilterChips 都在 table 之外,tbody 是 row trigger
  // 的唯一容器。用 ``tbody tr`` 选中目标行后取其内 button。
  const rows = body.querySelectorAll("tbody tr");
  const row = rows[rowIndex] as HTMLElement;
  const trigger = within(row).getByRole("button");
  await user.click(trigger);
  return body.ownerDocument.body;
}

describe("StoreView — device-poweron lifecycle buttons", () => {
  it("pending walk-in 行渲染「确认开机」菜单项并触发 startBooking(id)", async () => {
    const user = userEvent.setup();
    const startMut = makeMut();
    stubStoreBasics(makeOwnerMe());
    mocks.useBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_walkin", customer_id: null })],
      isLoading: false,
    });
    mocks.useStartBooking.mockReturnValue(startMut);

    const { baseElement } = renderWithProviders(<StoreView />);
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);

    const item = await within(portal as HTMLElement).findByText("确认开机");
    await user.click(item);

    expect(startMut.mutateAsync).toHaveBeenCalledWith("bk_walkin");
  });

  it("in_service 行渲染「结束服务」+ 点击开 Dialog + 提交触发 endBooking(带 feedback)", async () => {
    const user = userEvent.setup();
    const endMut = makeMut();
    stubStoreBasics(makeOwnerMe());
    mocks.useBookings.mockReturnValue({
      data: [makeBooking({ status: "in_service", id: "bk_insvc" })],
      isLoading: false,
    });
    mocks.useEndBooking.mockReturnValue(endMut);

    const { baseElement } = renderWithProviders(<StoreView />);
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);

    const menuItem = await within(portal as HTMLElement).findByText("结束服务");
    await user.click(menuItem);

    // Dialog 打开 —— title 出现后,textarea 是 dialog 内唯一的可编辑控件。
    // 填一个合法 JSON,期望 endBooking 以 {id, payload:{feedback:...}} 调用。
    const dialog = within(portal as HTMLElement).getByText("结束服务", {
      selector: "[role=heading], h2, *[data-slot=dialog-title]",
    }).closest("[role=dialog]") ?? portal;
    const ta = (dialog as HTMLElement).querySelector("textarea")!;
    // ``user.type`` 把 ``{`` / ``}`` 解析为 modifier 描述符(v14 语义),JSON
    // 文本里它们是字面量。用 fireEvent.change 直接置 value + 触发 React onChange,
    // 等价于真实输入且避免转义地狱。
    fireEvent.change(ta, { target: { value: '{"rating":5}' } });

    // dialog 内「结束服务」按钮(textContent 包含「结束服务」)。
    const submitBtn = within(dialog as HTMLElement).getByRole("button", { name: /结束服务/ });
    await user.click(submitBtn);

    expect(endMut.mutateAsync).toHaveBeenCalledWith({
      id: "bk_insvc",
      payload: { feedback: { rating: 5 } },
    });
  });

  it("pending 行渲染「标记爽约」+ 确认 Dialog → noShowBooking(id)", async () => {
    const user = userEvent.setup();
    const noShowMut = makeMut();
    stubStoreBasics(makeOwnerMe());
    mocks.useBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_p" })],
      isLoading: false,
    });
    mocks.useNoShowBooking.mockReturnValue(noShowMut);

    const { baseElement } = renderWithProviders(<StoreView />);
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);

    const menuItem = await within(portal as HTMLElement).findByText("标记爽约");
    await user.click(menuItem);

    // 确认 dialog 出现,点 dialog 内的「标记爽约」按钮触发 mutation。
    const confirmBtn = await within(portal as HTMLElement).findByRole("button", {
      name: /标记爽约/,
    });
    await user.click(confirmBtn);

    expect(noShowMut.mutateAsync).toHaveBeenCalledWith("bk_p");
  });

  it("终态行(done/cancelled/no_show)无操作菜单(不渲染 trigger)", () => {
    stubStoreBasics(makeOwnerMe());
    mocks.useBookings.mockReturnValue({
      data: [
        makeBooking({ status: "done", id: "bk_done" }),
        makeBooking({ status: "cancelled", id: "bk_cancelled" }),
        makeBooking({ status: "no_show", id: "bk_noshow" }),
      ],
      isLoading: false,
    });

    const { queryByRole } = renderWithProviders(<StoreView />);
    // 终态行无任何动作 → DropdownMenu 不挂载,菜单项一个都不出现。
    expect(
      queryByRole("menuitem", { name: /确认开机|结束服务|标记爽约|取消预约/ }),
    ).toBeNull();
  });

  it("member 视图无任何写按钮(canUpdate/canDelete 均假)", () => {
    stubStoreBasics(makeMemberMe());
    mocks.useBookings.mockReturnValue({
      data: [
        makeBooking({ status: "pending", id: "bk_p" }),
        makeBooking({ status: "in_service", id: "bk_is" }),
      ],
      isLoading: false,
    });

    const { queryByText, queryByRole } = renderWithProviders(<StoreView />);
    // member 既无 :update 也无 :delete → 整行无操作列 + 无菜单。
    // 关键词一个都不出现。
    for (const label of ["确认开机", "结束服务", "标记爽约", "取消预约", "改约"]) {
      expect(queryByText(label)).toBeNull();
    }
    expect(queryByRole("menuitem")).toBeNull();
  });

  it("owner 在 pending 行也可改约/取消(MUTABLE_STATUS 守 pending-only 不被动作按钮破坏)", async () => {
    const user = userEvent.setup();
    stubStoreBasics(makeOwnerMe());
    mocks.useBookings.mockReturnValue({
      data: [makeBooking({ status: "pending", id: "bk_p" })],
      isLoading: false,
    });

    const { baseElement } = renderWithProviders(<StoreView />);
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);

    // pending 行:确认开机 / 标记爽约 / 改约 / 取消预约 全可见。
    for (const label of ["确认开机", "标记爽约", "改约", "取消预约"]) {
      expect(await within(portal as HTMLElement).findByText(label)).toBeInTheDocument();
    }
  });
});
