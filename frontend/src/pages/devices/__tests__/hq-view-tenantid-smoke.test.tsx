// HqView tenantId 安全回归 smoke(plan-devices-page-split.md 切片 1 前移)。
//
// 本测试的存在理由(plan §0 / §9 高风险项 v2 修正):
//   切片 1 是纯 locality move(拆 devices-page.tsx → devices/ 文件夹)。现有
//   81 测试**不含任何 devices 测试**,所以「65+1 测试零回归」对 HqView 的
//   tenantId 跨租户写传递**零捕获** —— 拆分若把 tenantId 搞乱(StoreView 误传
//   id / HqView 误传 undefined)会造成跨租户越权写,而这不会触发任何现有测试。
//   v2 前移这个最小 smoke 消除「切片 1 完成 = tenantId 安全空窗」。
//
// 测什么(只覆盖最危险的 tenantId prop 路径,完整双路径覆盖在切片 2 的
// hq-view.test.tsx):
//   ① HqView 选 target 后,DeviceCreateDialog 收到 ``tenantId = 目标 id``
//      (非 undefined)—— Create/Edit 的 tenantId prop 路径(platform-cross-
//      tenant-write 的核心 adapter)。
//   ② HqView 未选 target 时,DeviceCreateDialog 收到 ``tenantId = undefined``
//      (canWrite=false, 入库按钮不渲染,Dialog 不打开)—— 验证默认态安全。
//
// 模式沿用 bookings/__tests__/hq-view.test.tsx 的 spy-on-children 范式(P7):
//   vi.mock("../device-dialogs") 把 DeviceCreateDialog 换成捕获 props 的占位
//   组件,每次渲染把收到的 props 推到 ``createDialogCalls`` 数组,断言最后一次
//   调用的 tenantId。Radix Select 在 jsdom 用 fireEvent pointer 序列触发
//   (user.click 撞 hasPointerCapture,沿用 bookings hq-view.test 的 pickTarget)。
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

// spy-on-children:DeviceCreateDialog 被替换为捕获 props 的占位组件。
// 每次渲染把收到的 props(含 tenantId)推到 createDialogCalls,断言最后一次
// 调用。其他 Dialog(Edit/Bind/Delete)+ RowMenu 用 importOriginal 透传真实
// 实现,避免影响未来扩展(本 smoke 只断言 Create 的 tenantId)。
const createDialogCalls: Array<{
  open: boolean;
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
  // createDialogCalls 是模块级裸数组,vi.clearAllMocks 不碰它,手动清。
  createDialogCalls.length = 0;
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

describe("HqView tenantId 安全回归 smoke (切片 1 前移)", () => {
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
});
