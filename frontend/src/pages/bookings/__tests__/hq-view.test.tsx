// HqView 组件测(bookings-page-split smoke + platform-cross-tenant-write
// 切片 04 平台角色写控件覆盖)。
//
// 第一部分(smoke,bookings-page-split 拆分补测):渲染跨店表 / 列头 / 空态 /
// tenant_name+device_name+customer_name 显示(含 null fallback)。
//
// 第二部分(切片 04 新增,plan §6 AC5/AC9/AC11):平台角色写控件显隐 ——
//   ① 未选 target 时无写按钮(AC9)
//   ② 选 target 后行内出现 DropdownMenu(AC3/AC4)
//   ③ DropdownMenu 按 status 显隐:pending→取消/开机;in_service→结束/爽约;
//      终态→无(AC5)
//
// 模式沿用 store-view.test.tsx 的 vitest 基建:``renderWithProviders`` +
// ``vi.mock("@/hooks/queries")`` stub 全部 HqView 用的 hooks + user-event
// 模拟下拉选择 + 行内菜单点击。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { HqView } from "../hq-view";
import type { BookingHqRead, Tenant } from "@/api/types";

// ---- mock wiring ----
// HqView 切片 04 改造后调的 hooks:列表 + 全租户 + 写 mut + 设备列表
// (targetDevices filter 用)。queryClient 来自 renderWithProviders,所以
// useQueryClient 不需要 mock。
const mocks = vi.hoisted(() => ({
  useBookings: vi.fn() as Mock,
  useAllTenants: vi.fn() as Mock,
  useDevices: vi.fn() as Mock,
  useCreateBooking: vi.fn() as Mock,
  useUpdateBooking: vi.fn() as Mock,
  useCancelBooking: vi.fn() as Mock,
  useStartBooking: vi.fn() as Mock,
  useEndBooking: vi.fn() as Mock,
  useNoShowBooking: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useBookings: mocks.useBookings,
  useAllTenants: mocks.useAllTenants,
  useDevices: mocks.useDevices,
  useCreateBooking: mocks.useCreateBooking,
  useUpdateBooking: mocks.useUpdateBooking,
  useCancelBooking: mocks.useCancelBooking,
  useStartBooking: mocks.useStartBooking,
  useEndBooking: mocks.useEndBooking,
  useNoShowBooking: mocks.useNoShowBooking,
  // qk 是常量对象,HqView 用它做 invalidateQueries 的 key。直接引真实值即可
  // (vi.mock 工厂返回的对象必须覆盖所有 HqView 引用的 named export)。
  qk: { bookings: ["bookings"] },
}));

// ---- factories ----
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
    created_by: null,
    started_at: null,
    ended_at: null,
    feedback: null,
    notes: null,
    created_at: "2026-07-24T09:00:00Z",
    updated_at: "2026-07-24T09:00:00Z",
    ...overrides,
  } as BookingHqRead;
}

function makeTenant(overrides: Partial<Tenant> = {}): Tenant {
  return {
    id: "t-1",
    name: "华东大区·上海徐汇店",
    ...overrides,
  } as Tenant;
}

// 标准的 mutation stub:resolve 立即成功,isPending 默认 false。
function makeMut() {
  return {
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  };
}

// 把所有写 hooks 喂成稳定 stub,避免每个用例重复设置。
function stubWriteMutations() {
  mocks.useCreateBooking.mockReturnValue(makeMut());
  mocks.useUpdateBooking.mockReturnValue(makeMut());
  mocks.useCancelBooking.mockReturnValue(makeMut());
  mocks.useStartBooking.mockReturnValue(makeMut());
  mocks.useEndBooking.mockReturnValue(makeMut());
  mocks.useNoShowBooking.mockReturnValue(makeMut());
}

afterEach(() => {
  vi.clearAllMocks();
});

// 触发行内 DropdownMenu(MoreHorizontal icon-only ghost button)。沿用
// store-view.test.tsx 的 openRowMenu 模式:tbody 内唯一 button。
async function openRowMenu(
  user: ReturnType<typeof userEvent.setup>,
  baseElement: HTMLElement,
  rowIndex = 0,
) {
  const rows = baseElement.querySelectorAll("tbody tr");
  const row = rows[rowIndex] as HTMLElement;
  const trigger = within(row).getByRole("button");
  await user.click(trigger);
  return baseElement.ownerDocument.body;
}

// 选 target:Radix Select 在 jsdom 下 user.click 撞 ``hasPointerCapture is not
// a function``(Radix Select 内部用 pointer capture,jsdom 没实现)。用
// fireEvent 的 pointerDown + pointerUp + click 序列触发 Radix Select 的打开,
// 这是 Radix 官方在 jsdom 测试的推荐姿势(替代 user-event 的 click)。
async function pickTarget(
  baseElement: HTMLElement,
  combobox: HTMLElement,
  optionText: string,
) {
  fireEvent.pointerDown(combobox, { button: 0 });
  fireEvent.pointerUp(combobox, { button: 0 });
  fireEvent.click(combobox);
  const opt = await within(baseElement.ownerDocument.body).findByText(
    optionText,
  );
  fireEvent.pointerDown(opt, { button: 0 });
  fireEvent.pointerUp(opt, { button: 0 });
  fireEvent.click(opt);
  // 等 re-render 完成(option 选择触发 onValueChange → setState)
  await Promise.resolve();
}

// ============================================================ smoke (回归)
describe("HqView — cross-tenant panorama smoke (regression)", () => {
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
    mocks.useAllTenants.mockReturnValue({ data: [] });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

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
    mocks.useAllTenants.mockReturnValue({ data: [] });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { getByText } = renderWithProviders(<HqView />);

    // 切片 04 改造:CardDescription 在未选 target 时追加 " — 请先选择目标门店
    // 才能代为操作",所以这里用部分匹配校验 "共 0 条" 而非整句。
    expect(getByText(/共 0 条预约（跨全部门店）/)).toBeTruthy();
    expect(getByText("暂无预约")).toBeTruthy();
    expect(getByText("跨全部门店暂无设备预约")).toBeTruthy();
  });

  // 回归测试(bugfix:TDZ ReferenceError)。真实运行时 useDevices() 返回非空
  // DeviceHqRead[](平台角色跨店 feed),targetDevices 的 .filter() 回调会真的
  // 执行。若 targetDevices 的计算被放在 const targetTenantId 声明之前(JS 的
  // const 不 hoist 初始值),filter 回调访问 targetTenantId 会抛
  // "Cannot access 'targetTenantId' before initialization" → HqView 崩 → 白屏。
  // 历史背景:本测试加入前,所有 smoke 用例都 mock useDevices→{data:[]},空数组
  // 让 .filter 回调一次都不执行,TDZ 永不触发 → bug 漏网 8 个测试全绿但生产白屏。
  it("useDevices 返回非空数组时不抛 TDZ ReferenceError(回归 bugfix)", () => {
    mocks.useBookings.mockReturnValue({
      data: [makeHqBooking({ id: "b-1", tenant_id: "t-1" })],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    // 关键:非空 devices 数组,触发 .filter 回调执行
    mocks.useDevices.mockReturnValue({
      data: [
        { id: "d-1", tenant_id: "t-1", status: "active", name: "DEV-1" },
        { id: "d-2", tenant_id: "t-2", status: "active", name: "DEV-2" },
        { id: "d-3", tenant_id: "t-1", status: "inactive", name: "DEV-3" },
      ],
    });
    stubWriteMutations();

    // 渲染不应抛 ReferenceError。修复前:const targetDevices 在 targetTenantId
    // 之前 → TDZ 抛错;修复后:顺序调换 → 正常渲染。
    expect(() => renderWithProviders(<HqView />)).not.toThrow();
  });

  it("null fallback:tenant_name/device_name/customer_name 缺失时显示兜底文案", () => {
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
    mocks.useAllTenants.mockReturnValue({ data: [] });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { getByText } = renderWithProviders(<HqView />);

    expect(getByText("（门店已删除）")).toBeTruthy();
    expect(getByText(/设备\(d-1\)/)).toBeTruthy();
    expect(getByText("散客(walk-in)")).toBeTruthy();
  });
});

// ============================================================ platform write (切片 04)
describe("HqView — platform-cross-tenant-write 切片 04 write controls", () => {
  it("AC9:未选 target 时无写按钮 / 无操作列 / 提示选择目标门店", () => {
    mocks.useBookings.mockReturnValue({
      data: [makeHqBooking({ status: "pending", id: "bk_p" })],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { queryByText, queryByRole } = renderWithProviders(<HqView />);

    // 操作列表头不渲染(canWrite false)+ 提示文案
    expect(queryByText("操作")).toBeNull();
    expect(queryByText(/请先选择目标门店/)).toBeTruthy();
    // 没有任何菜单项 / 写按钮渲染
    expect(queryByRole("menuitem")).toBeNull();
    expect(queryByText("创建预约")).toBeNull();
    // 行内 trigger 也不渲染(无操作列) —— 菜单项一个都不出现
    expect(queryByText("确认开机")).toBeNull();
  });

  it("AC3/AC4:选 target 后行内出现 DropdownMenu;pending 行显示开机/爽约/取消", async () => {
    const user = userEvent.setup();
    mocks.useBookings.mockReturnValue({
      data: [makeHqBooking({ status: "pending", id: "bk_p", tenant_id: "t-1" })],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { baseElement, getByRole, getByText } = renderWithProviders(<HqView />);

    // 选 target —— Radix Select trigger 是 role=combobox。jsdom 不支持
    // pointer capture,用 pickTarget 走 fireEvent.pointerDown/Up/click 序列。
    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );

    // 选 target 后,操作列表头出现 + 创建预约按钮出现
    expect(getByText("操作")).toBeTruthy();
    expect(getByText("创建预约")).toBeTruthy();

    // 打开行内菜单,pending 行应有:确认开机 / 标记爽约 / 改约 / 取消预约
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);
    for (const label of ["确认开机", "标记爽约", "改约", "取消预约"]) {
      expect(
        await within(portal as HTMLElement).findByText(label),
      ).toBeInTheDocument();
    }
  });

  it("AC5:in_service 行只显示结束/爽约(不显示开机/改约/取消)", async () => {
    const user = userEvent.setup();
    mocks.useBookings.mockReturnValue({
      data: [
        makeHqBooking({
          status: "in_service",
          id: "bk_is",
          tenant_id: "t-1",
        }),
      ],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { baseElement, getByRole } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );

    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);
    // in_service:可结束 + 可爽约;不可开机(已 in_service)+ 不可改约/取消
    // (MUTABLE_STATUS 守 pending-only)
    expect(
      await within(portal as HTMLElement).findByText("结束服务"),
    ).toBeInTheDocument();
    expect(
      await within(portal as HTMLElement).findByText("标记爽约"),
    ).toBeInTheDocument();
    expect(within(portal as HTMLElement).queryByText("确认开机")).toBeNull();
    expect(within(portal as HTMLElement).queryByText("改约")).toBeNull();
    expect(within(portal as HTMLElement).queryByText("取消预约")).toBeNull();
  });

  it("AC5:终态行(done/cancelled/no_show)无操作菜单(不渲染 trigger)", async () => {
    mocks.useBookings.mockReturnValue({
      data: [
        makeHqBooking({ status: "done", id: "bk_d", tenant_id: "t-1" }),
        makeHqBooking({ status: "cancelled", id: "bk_c", tenant_id: "t-1" }),
        makeHqBooking({ status: "no_show", id: "bk_n", tenant_id: "t-1" }),
      ],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { baseElement, getByRole, getByText } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );

    // 选了 target 但 3 行都是终态 → 无任何菜单项渲染
    expect(
      baseElement.ownerDocument.body.querySelectorAll(
        "[role=menuitem]",
      ).length,
    ).toBe(0);
    // 操作列表头出现(canWrite true),但行内 trigger 因 showMenu false 不渲染
    expect(getByText("操作")).toBeTruthy();
  });

  it("AC2/AC6:选 target 后开机动作以 tenantId 闭包触发 startBooking", async () => {
    const user = userEvent.setup();
    const startMut = makeMut();
    mocks.useBookings.mockReturnValue({
      data: [makeHqBooking({ status: "pending", id: "bk_p", tenant_id: "t-1" })],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    mocks.useDevices.mockReturnValue({ data: [] });
    stubWriteMutations();
    mocks.useStartBooking.mockReturnValue(startMut);

    const { baseElement, getByRole } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );

    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);
    const item = await within(portal as HTMLElement).findByText("确认开机");
    await user.click(item);

    // startMut 是 useStartBooking(targetTenantId) 的返回值 —— closure 已绑
    // 定 target。mutateAsync 直接以 id 调用(tenantId 在 hook 内部加 query)。
    expect(startMut.mutateAsync).toHaveBeenCalledWith("bk_p");
  });
});
