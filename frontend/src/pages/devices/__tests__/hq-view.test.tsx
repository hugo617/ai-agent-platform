// HqView 组件测(devices-page-split 切片 02)。
//
// 覆盖三块(plan-devices-page-split.md §5 + 切片 02 AC2):
//   ① tenantId prop 路径(Create/Edit,spy-on-children):HqView 选 target 后,
//      DeviceCreateDialog / DeviceEditDialog 收到 ``tenantId = 目标 id``(非
//      undefined)—— platform-cross-tenant-write 的核心 adapter。未选 target 时
//      收到 ``undefined``(canWrite=false,入库按钮不渲染,默认态安全)。
//   ② panorama 列表渲染(跨店表 + 列头 + 行数据 tenant_name/model_name/
//      customer_name)+ 空态。
//   ③ hook closure 路径(Bind/Delete):DeviceBindDialog / DeviceDeleteDialog 无
//      tenantId prop,跨租户写靠 HqView 调 ``useDeleteDevice(targetTenantId)`` /
//      ``useBindDeviceCustomer(targetTenantId)``,targetTenantId 闭包绑定进 hook
//      (query param 传递)。本文件既断言 hook **被以 targetTenantId 构造**,也
//      断言闭包在**写流程里真生效**(点删除 → mutateAsync 被调)。
//
// 历史背景:本文件脱胎于切片 1 前移的 tenantId smoke(当时只覆盖最危险的 Create
// prop 路径,消除「切片 1 完成 = tenantId 安全零捕获」空窗);切片 02 把它扩展为
// 完整 hq-view.test(prop 双路径 + panorama + closure 双路径)。
//
// 模式沿用 bookings/__tests__/hq-view.test.tsx 的 spy-on-children 范式(P7):
//   vi.mock("../device-dialogs") 把 DeviceCreateDialog / DeviceEditDialog 换成
//   捕获 props 的占位组件,每次渲染把收到的 props 推到 ``createDialogCalls`` /
//   ``editDialogCalls`` 数组,断言最后一次调用的 tenantId。Radix Select 在 jsdom
//   用 fireEvent pointer 序列触发(user.click 撞 hasPointerCapture,沿用 bookings
//   hq-view.test 的 pickTarget)。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { HqView } from "../hq-view";
import type { DeviceHqRead, Tenant } from "@/api/types";

// ---- mock wiring ----
// HqView 调的 hooks:panorama 列表 + 全租户 + model 目录 + 5 个写 hook。
// queryClient 来自 renderWithProviders,所以 useQueryClient 不需要 mock。
const mocks = vi.hoisted(() => ({
  useDevicesAll: vi.fn() as Mock,
  useAllTenants: vi.fn() as Mock,
  useDeviceModels: vi.fn() as Mock,
  useCreateDevice: vi.fn() as Mock,
  useUpdateDevice: vi.fn() as Mock,
  useDeleteDevice: vi.fn() as Mock,
  useBindDeviceCustomer: vi.fn() as Mock,
  useUnbindDeviceCustomer: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useDevicesAll: mocks.useDevicesAll,
  useAllTenants: mocks.useAllTenants,
  useDeviceModels: mocks.useDeviceModels,
  useCreateDevice: mocks.useCreateDevice,
  useUpdateDevice: mocks.useUpdateDevice,
  useDeleteDevice: mocks.useDeleteDevice,
  useBindDeviceCustomer: mocks.useBindDeviceCustomer,
  useUnbindDeviceCustomer: mocks.useUnbindDeviceCustomer,
  // qk 是常量对象,HqView 用它做 invalidateQueries 的 key。
  qk: { devices: ["devices"] },
}));

// spy-on-children:DeviceCreateDialog / DeviceEditDialog 被替换为捕获 props 的
// 占位组件。每次渲染把收到的 props(含 tenantId)推到 createDialogCalls /
// editDialogCalls,断言最后一次调用的 tenantId。这两个 Dialog 是跨租户写的
// **prop 路径**(Create/Edit 通过 tenantId prop 区分 store/HQ);Bind/Delete
// 两 Dialog 无 tenantId prop,跨租户写走 **hook closure 路径**(见下方
// ``useDeleteDevice/useBindDeviceCustomer(targetTenantId)`` 断言),故不用
// spy 占位 —— 用 importOriginal 透传真实实现,既有「行内菜单」测试不受影响。
const createDialogCalls: Array<{
  open: boolean;
  tenantId?: string;
}> = [];
const editDialogCalls: Array<{
  targetId: string | null;
  tenantId?: string;
}> = [];
vi.mock("../device-dialogs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../device-dialogs")>();
  return {
    ...actual,
    DeviceCreateDialog: (props: { open: boolean; tenantId?: string }) => {
      createDialogCalls.push({
        open: props.open,
        tenantId: props.tenantId,
      });
      return null;
    },
    DeviceEditDialog: (props: {
      target: { id: string } | null;
      tenantId?: string;
    }) => {
      editDialogCalls.push({
        targetId: props.target ? props.target.id : null,
        tenantId: props.tenantId,
      });
      return null;
    },
  };
});

// ---- factories ----
function makeHqDevice(overrides: Partial<DeviceHqRead> = {}): DeviceHqRead {
  return {
    id: "d-1",
    tenant_id: "t-1",
    tenant_name: "华东大区·上海徐汇店",
    model_id: "m-1",
    model_name: "MODEL-X1",
    serial_number: "SN-2026-0001",
    status: "active",
    customer_id: "c-1",
    customer_name: "张三",
    created_by: null,
    created_at: "2026-07-24T09:00:00Z",
    updated_at: "2026-07-24T09:00:00Z",
    ...overrides,
  } as DeviceHqRead;
}

function makeTenant(overrides: Partial<Tenant> = {}): Tenant {
  return {
    id: "t-target",
    name: "华北大区·北京朝阳店",
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

function stubWriteMutations() {
  mocks.useCreateDevice.mockReturnValue(makeMut());
  mocks.useUpdateDevice.mockReturnValue(makeMut());
  mocks.useDeleteDevice.mockReturnValue(makeMut());
  mocks.useBindDeviceCustomer.mockReturnValue(makeMut());
  mocks.useUnbindDeviceCustomer.mockReturnValue(makeMut());
}

afterEach(() => {
  vi.clearAllMocks();
  // createDialogCalls / editDialogCalls 是模块级裸数组,vi.clearAllMocks 不碰,
  // 手动清。每个用例后清空,防后续用例继承前序用例的 spy 记录。
  createDialogCalls.length = 0;
  editDialogCalls.length = 0;
});

// Radix Select 在 jsdom 下 user.click 撞 ``hasPointerCapture is not a
// function``(Radix Select 内部用 pointer capture,jsdom 没实现)。用
// fireEvent 的 pointerDown + pointerUp + click 序列触发,沿用 bookings
// hq-view.test 的 pickTarget 范式(Radix 官方 jsdom 测试推荐姿势)。
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
  await Promise.resolve();
}

// ============================================================ tenantId prop 路径(Create/Edit)
// 切片 1 前移的 smoke:覆盖跨租户写的 **prop 路径** —— DeviceCreateDialog 通过
// tenantId prop 收到目标门店(非 undefined)。切片 02 扩展 Edit prop 路径 +
// Bind/Delete hook closure 路径(见后续 describe 块)。
describe("HqView — tenantId prop 路径(Create/Edit spy-on-children)", () => {
  it("未选 target:入库按钮不渲染,DeviceCreateDialog tenantId 为 undefined(默认态安全)", () => {
    mocks.useDevicesAll.mockReturnValue({ data: [], isLoading: false });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant()],
    });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { queryByText } = renderWithProviders(<HqView />);

    // canWrite=false → 入库按钮隐藏
    expect(queryByText("设备入库")).toBeNull();
    // HqView 渲染时 DeviceCreateDialog 已 mount(open=false),tenantId 为
    // undefined(targetTenantId 空串 → targetTenantId || undefined)。
    expect(createDialogCalls.length).toBeGreaterThan(0);
    const lastCall = createDialogCalls[createDialogCalls.length - 1];
    expect(lastCall.open).toBe(false);
    expect(lastCall.tenantId).toBeUndefined();
  });

  it("选 target 后点入库:DeviceCreateDialog 收到目标 tenantId(非 undefined,跨租户写守卫)", async () => {
    const user = userEvent.setup();
    mocks.useDevicesAll.mockReturnValue({
      data: [makeHqDevice()],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({
      data: [makeTenant()],
    });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();
    // 清空初始 mount 的 spy 记录,只关注「选 target + 点入库」之后的调用。
    createDialogCalls.length = 0;

    const { baseElement, getByText } = renderWithProviders(<HqView />);

    // 选 target(AC9:写操作前置条件)
    const combobox = baseElement.querySelector(
      "button[role='combobox']",
    ) as HTMLElement;
    await pickTarget(baseElement, combobox, "华北大区·北京朝阳店");

    // 选 target 后入库按钮出现,点击打开 Create Dialog
    await user.click(getByText("设备入库"));

    // 核心断言:DeviceCreateDialog 收到目标 tenantId(非 undefined)。
    // 这是 platform-cross-tenant-write 跨租户写的 prop 路径 —— 若拆分把
    // tenantId 丢成 undefined,create payload 会省略 tenant_id → 后端用
    // user.tenant_id(平台方自己的租户)而非目标门店,构成越权写漏洞。
    expect(createDialogCalls.length).toBeGreaterThan(0);
    const lastCall = createDialogCalls[createDialogCalls.length - 1];
    expect(lastCall.open).toBe(true);
    expect(lastCall.tenantId).toBe("t-target");
  });

  it("选 target 后行内点编辑:DeviceEditDialog 收到目标 tenantId(Edit prop 路径)", async () => {
    const user = userEvent.setup();
    mocks.useDevicesAll.mockReturnValue({
      data: [
        makeHqDevice({
          id: "d-1",
          model_id: "m-1",
          serial_number: "SN-2026-0001",
          status: "active",
        }),
      ],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({ data: [makeTenant()] });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();
    // 清空初始 mount 的 spy 记录,只关注「选 target + 点编辑」之后的调用。
    editDialogCalls.length = 0;

    const { baseElement } = renderWithProviders(<HqView />);

    // 选 target(AC9:写操作前置条件)。
    const combobox = baseElement.querySelector(
      "button[role='combobox']",
    ) as HTMLElement;
    await pickTarget(baseElement, combobox, "华北大区·北京朝阳店");

    // 打开行内菜单(MoreHorizontal icon-only ghost button),点「编辑」。
    const row = baseElement.querySelector("tbody tr") as HTMLElement;
    await user.click(within(row).getByRole("button"));
    const editItem = await within(baseElement.ownerDocument.body).findByRole(
      "menuitem",
      { name: "编辑" },
    );
    await user.click(editItem);

    // 核心断言:DeviceEditDialog 收到目标 tenantId(Edit prop 路径,与 Create
    // 同机制)。若 tenantId 被丢成 undefined,update payload 会省略 tenant_id
    // → 后端用 user.tenant_id 而非目标门店,构成越权写漏洞。
    expect(editDialogCalls.length).toBeGreaterThan(0);
    const lastCall = editDialogCalls[editDialogCalls.length - 1];
    expect(lastCall.targetId).toBe("d-1");
    expect(lastCall.tenantId).toBe("t-target");
  });
});

// ============================================================ panorama 渲染(列表回归)
describe("HqView — cross-tenant panorama smoke (列表渲染)", () => {
  it("渲染跨店表 + 列头 + 行数据(tenant_name/model_name/customer_name)", () => {
    mocks.useDevicesAll.mockReturnValue({
      data: [
        makeHqDevice(),
        makeHqDevice({
          id: "d-2",
          tenant_name: "华北大区·北京朝阳店",
          model_name: "MODEL-X2",
          serial_number: "SN-2026-0002",
          customer_name: "李四",
        }),
      ],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({ data: [] });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { getAllByRole, getByText } = renderWithProviders(<HqView />);

    // 列头(所属门店 / 序列号 / 型号 / 状态 / 绑定客户 / 创建时间)。
    expect(getByText("所属门店")).toBeTruthy();
    expect(getByText("序列号")).toBeTruthy();
    expect(getByText("型号")).toBeTruthy();
    expect(getByText("状态")).toBeTruthy();
    expect(getByText("绑定客户")).toBeTruthy();

    // 行数据(1 header + 2 body)。DeviceHqRead 服务端已展开 *_name。
    expect(getAllByRole("row").length).toBe(3);
    expect(getByText("华东大区·上海徐汇店")).toBeTruthy();
    expect(getByText("MODEL-X2")).toBeTruthy();
    expect(getByText("李四")).toBeTruthy();
    // PageHeader 标题。
    expect(getByText("设备（总部视图）")).toBeTruthy();
  });

  it("空态:无设备时渲染 EmptyState + 总数 0 + 提示选目标门店", () => {
    mocks.useDevicesAll.mockReturnValue({ data: [], isLoading: false });
    mocks.useAllTenants.mockReturnValue({ data: [] });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { getByText } = renderWithProviders(<HqView />);

    // canWrite=false → CardDescription 追加「请先选择目标门店」。
    expect(getByText(/共 0 台设备（跨全部门店）/)).toBeTruthy();
    expect(getByText("暂无设备")).toBeTruthy();
    expect(getByText(/请先选择目标门店/)).toBeTruthy();
  });
});

// ============================================================ hook closure 路径(Bind/Delete)
// 跨租户写的另一半:DeviceBindDialog / DeviceDeleteDialog 无 tenantId prop,
// 它们的跨租户写靠 hook closure —— HqView 调 ``useDeleteDevice(targetTenantId)``
// / ``useBindDeviceCustomer(targetTenantId)``,targetTenantId 闭包绑定进 hook
// (query param 传递)。StoreView 调这些 hook 不带参数(store path)。
describe("HqView — hook closure 路径(Bind/Delete targetTenantId 闭包)", () => {
  it("选 target 后 useDeleteDevice / useBindDeviceCustomer / useUnbindDeviceCustomer 被以 targetTenantId 调用", async () => {
    mocks.useDevicesAll.mockReturnValue({ data: [] });
    mocks.useAllTenants.mockReturnValue({ data: [makeTenant()] });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();

    const { baseElement } = renderWithProviders(<HqView />);

    // 选 target。
    const combobox = baseElement.querySelector(
      "button[role='combobox']",
    ) as HTMLElement;
    await pickTarget(baseElement, combobox, "华北大区·北京朝阳店");

    // 核心断言:三个写 hook 在 HqView 渲染时以 targetTenantId 构造(hook
    // closure)。这是 platform-cross-tenant-write 的 query-param 传递机制 ——
    // 若 targetTenantId 没进 hook 实参,delete/bind 的 mutateAsync 会打到
    // 平台方自己的租户(越权写)或被后端 400 拒(平台写者必须指定 target)。
    // useCreateDevice / useUpdateDevice 不接 tenantId(走 Dialog prop 路径,
    // 由 Create/Edit 的 spy 用例覆盖),故这里只断言三个 closure 路径的 hook。
    expect(mocks.useDeleteDevice).toHaveBeenCalledWith("t-target");
    expect(mocks.useBindDeviceCustomer).toHaveBeenCalledWith("t-target");
    expect(mocks.useUnbindDeviceCustomer).toHaveBeenCalledWith("t-target");
  });

  it("未选 target 时三个写 hook 以 undefined 调用(store path 形态,默认态安全)", () => {
    mocks.useDevicesAll.mockReturnValue({ data: [] });
    mocks.useAllTenants.mockReturnValue({ data: [makeTenant()] });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();

    renderWithProviders(<HqView />);

    // 未选 target → targetTenantId="" → ``"" || undefined`` = undefined。
    // 三个 hook 以 undefined 构造;canWrite=false → 写控件全隐藏,即便 hook
    // 构造了也不会被触发(buttons/menus 不渲染),双重防御。
    expect(mocks.useDeleteDevice).toHaveBeenCalledWith(undefined);
    expect(mocks.useBindDeviceCustomer).toHaveBeenCalledWith(undefined);
    expect(mocks.useUnbindDeviceCustomer).toHaveBeenCalledWith(undefined);
  });

  it("选 target 后行内点删除 → DeviceDeleteDialog 确认 → deleteMut.mutateAsync 被调(闭包在写流程生效)", async () => {
    const user = userEvent.setup();
    const deleteMut = makeMut();
    mocks.useDevicesAll.mockReturnValue({
      data: [makeHqDevice({ id: "d-1", status: "active" })],
      isLoading: false,
    });
    mocks.useAllTenants.mockReturnValue({ data: [makeTenant()] });
    mocks.useDeviceModels.mockReturnValue({ data: [] });
    stubWriteMutations();
    // useDeleteDevice(targetTenantId) 的返回值 —— 覆盖为可观测的 deleteMut,
    // 证明闭包绑定在写流程里真生效(不只构造时传了参数)。
    mocks.useDeleteDevice.mockReturnValue(deleteMut);

    const { baseElement } = renderWithProviders(<HqView />);

    // 选 target。
    const combobox = baseElement.querySelector(
      "button[role='combobox']",
    ) as HTMLElement;
    await pickTarget(baseElement, combobox, "华北大区·北京朝阳店");

    // 打开行内菜单 → 点「删除设备」→ DeviceDeleteDialog 弹出 → 点「删除」确认。
    const row = baseElement.querySelector("tbody tr") as HTMLElement;
    await user.click(within(row).getByRole("button"));
    const deleteItem = await within(baseElement.ownerDocument.body).findByRole(
      "menuitem",
      { name: "删除设备" },
    );
    await user.click(deleteItem);

    // DeleteDialog 的「删除」按钮(destructive variant,textContent 含「删除」)。
    const confirmBtn = await within(
      baseElement.ownerDocument.body,
    ).findByRole("button", { name: /删除/ });
    await user.click(confirmBtn);

    // 核心断言:deleteMut 是 useDeleteDevice(targetTenantId) 的返回值 —— closure
    // 已绑定 target。mutateAsync 以 device id 调用(tenantId 在 hook 内部加 query
    // param,参照 bookings hq-view.test 断言 startMut.mutateAsync 的范式)。
    // 这证明 closure 路径不只是「构造时传了 targetTenantId」,而是写流程里真生效。
    expect(deleteMut.mutateAsync).toHaveBeenCalledWith("d-1");
  });
});
