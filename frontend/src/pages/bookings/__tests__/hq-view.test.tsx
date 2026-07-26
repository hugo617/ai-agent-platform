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
// (targetDevices filter 用)。切片 04b 新增:网格数据 + 两级配置 read/write
// hooks(useTenantBookingsByDate / useBookingConfigEffective /
// usePlatformBookingConfig / useTenantBookingConfig /
// useUpdatePlatformBookingConfig / useUpdateTenantBookingConfig)。
// queryClient 来自 renderWithProviders,所以 useQueryClient 不需要 mock。
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
  // 切片 04b 网格 + 配置 hooks
  useTenantBookingsByDate: vi.fn() as Mock,
  useBookingConfigEffective: vi.fn() as Mock,
  usePlatformBookingConfig: vi.fn() as Mock,
  useTenantBookingConfig: vi.fn() as Mock,
  useUpdatePlatformBookingConfig: vi.fn() as Mock,
  useUpdateTenantBookingConfig: vi.fn() as Mock,
  // useAuth 返回 { me },me 用来判 isSuperAdmin(决定 ConfigDialog 两栏/单栏)
  useAuthMe: { platform_role: "super_admin", tenant_id: null } as {
    platform_role: string | null;
    tenant_id: string | null;
  },
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
  // 切片 04b
  useTenantBookingsByDate: mocks.useTenantBookingsByDate,
  useBookingConfigEffective: mocks.useBookingConfigEffective,
  usePlatformBookingConfig: mocks.usePlatformBookingConfig,
  useTenantBookingConfig: mocks.useTenantBookingConfig,
  useUpdatePlatformBookingConfig: mocks.useUpdatePlatformBookingConfig,
  useUpdateTenantBookingConfig: mocks.useUpdateTenantBookingConfig,
  // qk 是常量对象,HqView 用它做 invalidateQueries 的 key。直接引真实值即可
  // (vi.mock 工厂返回的对象必须覆盖所有 HqView 引用的 named export)。
  qk: { bookings: ["bookings"] },
}));

// 切片 04b:HqView 调 useAuth() 取 me 判 isSuperAdmin(决定 ConfigDialog 形态)。
// isSuperAdmin 读 me.platform_role === "super_admin";mock 返回 super_admin 让
// 既有用例(不关心 ConfigDialog 形态)走两栏分支也能正常渲染。预填测试 describe
// 里会单独覆写为 hq_staff 验证单栏(若需)。
vi.mock("@/components/auth/auth-context", () => ({
  useAuth: () => ({ me: mocks.useAuthMe }),
}));

// 切片 04b P7:spy-on-children 范式。BookingCreateDialog 被替换为一个捕获 props
// 的占位组件 —— 每次渲染把收到的 props 推到 ``createDialogCalls`` 数组,预填测试
// 断言最后一次调用的 defaultDeviceId/defaultStart/defaultEnd。既有 9 用例 + Tab/
// 网格/设置 用例都不点 cell 打开 create Dialog(它们测的是列表/网格/配置),所以
// 占位从不显示内容,零影响。其他 Dialog(Edit/Cancel/End/NoShow)+ RowMenu 用
// importOriginal 透传真实实现,既有「行内菜单」测试不受影响。
const createDialogCalls: Array<{
  defaultDeviceId?: string;
  defaultStart?: string;
  defaultEnd?: string;
  open: boolean;
}> = [];
vi.mock("../shared-dialog", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../shared-dialog")>();
  return {
    ...actual,
    BookingCreateDialog: (props: {
      defaultDeviceId?: string;
      defaultStart?: string;
      defaultEnd?: string;
      open: boolean;
    }) => {
      createDialogCalls.push({
        defaultDeviceId: props.defaultDeviceId,
        defaultStart: props.defaultStart,
        defaultEnd: props.defaultEnd,
        open: props.open,
      });
      return null;
    },
  };
});

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
// 切片 04b:同时喂网格 + 两级配置 read/write hooks 的默认空值,让既有 9 用例
// (不关心网格/配置)零改动通过 —— 网格 Tab 默认不渲染(viewMode="list"),
// 这些 stub 只在 HqView 顶层 hooks 调用时被读取返回值。
function stubWriteMutations() {
  mocks.useCreateBooking.mockReturnValue(makeMut());
  mocks.useUpdateBooking.mockReturnValue(makeMut());
  mocks.useCancelBooking.mockReturnValue(makeMut());
  mocks.useStartBooking.mockReturnValue(makeMut());
  mocks.useEndBooking.mockReturnValue(makeMut());
  mocks.useNoShowBooking.mockReturnValue(makeMut());
  // 切片 04b 默认:空数据 + 未加载配置(用 undefined 让 HqView 走 fallback)
  mocks.useTenantBookingsByDate.mockReturnValue({ data: [], isLoading: false });
  mocks.useBookingConfigEffective.mockReturnValue({ data: undefined });
  mocks.usePlatformBookingConfig.mockReturnValue({ data: null });
  mocks.useTenantBookingConfig.mockReturnValue({ data: null });
  mocks.useUpdatePlatformBookingConfig.mockReturnValue(makeMut());
  mocks.useUpdateTenantBookingConfig.mockReturnValue(makeMut());
}

afterEach(() => {
  vi.clearAllMocks();
  // 切片 04b: createDialogCalls 是模块级裸数组,vi.clearAllMocks 不碰它。
  // 每个用例后清空,防未来新增测试继承前序用例的 spy 记录(P7 测试虽也手动
  // 清一次,但这里是 belt-and-braces 的统一兜底)。
  createDialogCalls.length = 0;
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

// ============================================================ 切片 04b: Tabs + 网格 + 配置
describe("HqView — booking-schedule-grid 切片 04b Tabs + 网格集成", () => {
  // 网格测试共用 setup:选 target + 喂 device 数据 + effective config + 空 grid。
  // targetDevices 在 HqView 内 .filter(tenant_id===target && status==="active"),
  // 所以 devices 要含一条 target 店的 active 设备,网格才有列可渲染。
  function setupGrid() {
    mocks.useBookings.mockReturnValue({ data: [], isLoading: false });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant({ id: "t-1", name: "上海徐汇店" })],
    });
    mocks.useDevices.mockReturnValue({
      data: [
        {
          id: "d-1",
          tenant_id: "t-1",
          status: "active",
          model_name: "理疗床 1",
          serial_number: "DEV-001",
        },
      ],
    });
    stubWriteMutations();
    // 网格数据:空列表(只测渲染,不测数据)。effectiveConfig 给真实形状让
    // ScheduleGrid 渲染 08:00-22:00 行(28 half-hour rows)。
    mocks.useTenantBookingsByDate.mockReturnValue({ data: [], isLoading: false });
    mocks.useBookingConfigEffective.mockReturnValue({
      data: {
        default_duration_minutes: 45,
        window_start: "08:00",
        window_end: "22:00",
      },
    });
  }

  it("Tab 出现 + 默认列表:选 target 后出现 列表/网格 Tab,列表默认选中", async () => {
    setupGrid();
    const { baseElement, getByRole, getByText } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );

    // 两个 Tab 按钮出现
    const listTab = getByText("列表");
    const gridTab = getByText("网格");
    expect(listTab).toBeTruthy();
    expect(gridTab).toBeTruthy();
    // 默认列表:list Tab aria-pressed=true,grid false
    expect(listTab).toHaveAttribute("aria-pressed", "true");
    expect(gridTab).toHaveAttribute("aria-pressed", "false");
    // list 为空时 ListState 渲染空态(不渲染 Table 表头),这里只验证 Tab
    // 选中态 —— 表头渲染由「渲染跨店表」smoke 用例(带数据)覆盖。
  });

  it("Tab 切到网格 + 网格渲染:点网格 → ScheduleGrid 渲染 + 日期 input min=今天", async () => {
    const user = userEvent.setup();
    setupGrid();
    const { baseElement, getByRole, container } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );

    // 点网格 Tab
    await user.click(getByRole("button", { name: "网格" }));

    // ScheduleGrid 渲染:.grid table 出现 + 设备列表头(理疗床 1)
    expect(container.querySelector("table.grid")).toBeTruthy();
    expect(baseElement.ownerDocument.body.textContent).toContain("理疗床 1");
    // 日期 input min=今天(YYYY-MM-DD 格式)
    const dateInput = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    expect(dateInput).toBeTruthy();
    expect(dateInput.min).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    // 默认值也是今天
    expect(dateInput.value).toBe(dateInput.min);
    // 设置按钮可见
    expect(getByRole("button", { name: /设置/ })).toBeTruthy();
  });

  it("设置按钮 → 弹 ConfigDialog:点设置后「预约配置」标题可见", async () => {
    const user = userEvent.setup();
    setupGrid();
    const { baseElement, getByRole } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );
    await user.click(getByRole("button", { name: "网格" }));

    // 配置 Dialog 未开时标题不可见
    expect(baseElement.ownerDocument.body.textContent).not.toContain("预约配置");

    // 点设置 → Dialog 打开,标题可见
    await user.click(getByRole("button", { name: /设置/ }));
    expect(baseElement.ownerDocument.body.textContent).toContain("预约配置");
  });

  // P7: spy-on-children 范式。点网格空 cell → BookingCreateDialog(已被 spy 替换)
  // 收到预填 props(defaultDeviceId/defaultStart/defaultEnd)。断言最后一次调用
  // 的 props 含点击的 device + cellStart/cellEnd ISO。
  it("P7:点网格空 cell → BookingCreateDialog 收到预填 device + start/end props", async () => {
    const user = userEvent.setup();
    setupGrid();
    // createDialogCalls 已在 afterEach 统一清空,这里无需手动清。
    const { baseElement, getByRole, container } = renderWithProviders(<HqView />);

    await pickTarget(
      baseElement as unknown as HTMLElement,
      getByRole("combobox"),
      "上海徐汇店",
    );
    await user.click(getByRole("button", { name: "网格" }));

    // 把日期改到未来(明天),让所有 cell 都可预订 —— ScheduleGrid 默认 now=今天,
    // 今天的早些时段 cell 会是 disabled(不可点)。换未来日期 isSelectedToday=false
    // → 全部 cell bookable。date input 的 value/min 是 YYYY-MM-DD。
    const dateInput = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    const today = dateInput.min; // 今天 YYYY-MM-DD
    // 明天 = 今天 + 1 天(手算避免引日期库,对齐 plan §8 不引日期库)。
    const [y, m, d] = today.split("-").map(Number);
    const tomorrow = new Date(y, m - 1, d + 1);
    const tomorrowISO = `${tomorrow.getFullYear()}-${String(
      tomorrow.getMonth() + 1,
    ).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;
    fireEvent.change(dateInput, { target: { value: tomorrowISO } });

    // 点一个空 bookable cell。config window 08:00-22:00,slot 2 = 09:00。
    // data-device=0(第一列 d-1),data-slot=2。fireEvent.change 后网格会随
    // gridDate 重渲染,但 selectin 立即可用(同步 setState)。
    const cellEl = container.querySelector(
      'td.cell.bookable[data-device="0"][data-slot="2"]',
    ) as HTMLElement | null;
    expect(cellEl).toBeTruthy();
    await user.click(cellEl as HTMLElement);

    // spy 应被以 open=true + 预填 props 调用。最后一次调用即点击后的那次。
    const lastCall = createDialogCalls[createDialogCalls.length - 1];
    expect(lastCall).toBeTruthy();
    expect(lastCall.open).toBe(true);
    expect(lastCall.defaultDeviceId).toBe("d-1");
    // slot 2 = windowStart(8) + 2*0.5h = 09:00 本地;45 分钟 duration →
    // end 09:45 本地。ScheduleGrid.slotHourToISO 用 setHours(本地)+ toISOString,
    // 所以断言本地小时数(不假设 UTC —— jsdom 跑在宿主时区,toISOString 会偏移)。
    const startLocalHour = new Date(lastCall.defaultStart as string).getHours();
    const endLocalHour = new Date(lastCall.defaultEnd as string).getHours();
    const endLocalMin = new Date(lastCall.defaultEnd as string).getMinutes();
    expect(startLocalHour).toBe(9);
    expect(endLocalHour).toBe(9);
    expect(endLocalMin).toBe(45);
  });
});
