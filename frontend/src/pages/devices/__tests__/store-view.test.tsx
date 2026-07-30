// StoreView 组件测(devices-page-split 切片 02)。
//
// 模式沿用 bookings/__tests__/store-view.test.tsx(已落地的 vitest 基建):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(否则
//     useDevices / useToast 抛 "must be used within Provider")。
//   - ``vi.mock("@/hooks/queries")`` stub 写 hooks —— 不走真实 axios/网络,
//     断言的是「组件正确调用了 hook」而非「后端返回什么」(后端契约由 pytest 覆盖)。
//   - ``vi.mock("@/components/auth/auth-context")`` 注入不同 me 变体(owner /
//     member),驱动按钮的 ``canCreate``/``canUpdate``/``canDelete`` 守卫。
//   - user-event@14 模拟点击(比 fireEvent 更贴近真实交互)。DropdownMenu 项
//     在 Radix 中是异步 portal 挂载,点开后再 await findByText 拿菜单项。
//
// 覆盖(plan-devices-page-split.md 切片 02 AC1):列表渲染 + CRUD 守卫
// (member 只读 / owner 有写按钮)+ 创建 Dialog 弹出。StoreView 用
// ``useDevices``(store-scoped,返 Device[],非 HqView 的 useDevicesAll)+
// ``hasPermission(me, "devices", act)`` 守卫。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { StoreView } from "../store-view";
import type { Device, MeResponse } from "@/api/types";

// ---- mock wiring ----
// ``vi.mock`` 工厂在 hoist 作用域执行,引用的变量必须用 ``vi.hoisted`` 提前。
const mocks = vi.hoisted(() => ({
  useDevices: vi.fn() as Mock,
  useDeviceModels: vi.fn() as Mock,
  useCustomerProfiles: vi.fn() as Mock,
  useCreateDevice: vi.fn() as Mock,
  useUpdateDevice: vi.fn() as Mock,
  useDeleteDevice: vi.fn() as Mock,
  useBindDeviceCustomer: vi.fn() as Mock,
  useUnbindDeviceCustomer: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useDevices: mocks.useDevices,
  useDeviceModels: mocks.useDeviceModels,
  useCustomerProfiles: mocks.useCustomerProfiles,
  useCreateDevice: mocks.useCreateDevice,
  useUpdateDevice: mocks.useUpdateDevice,
  useDeleteDevice: mocks.useDeleteDevice,
  useBindDeviceCustomer: mocks.useBindDeviceCustomer,
  useUnbindDeviceCustomer: mocks.useUnbindDeviceCustomer,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// ---- factories ----
// DeviceRead (store view) carries only ``model_id`` (no ``model_name``) — the
// view resolves the name locally from useDeviceModels(). Bound customer shown
// via customerNameOf(d.customer_id, profiles).
function makeDevice(overrides: Partial<Device> = {}): Device {
  return {
    id: "dev_1",
    tenant_id: "tn_1",
    model_id: "m_1",
    serial_number: "SN-2026-0001",
    status: "active",
    customer_id: "c_1",
    created_by: null,
    created_at: "2026-07-24T09:00:00Z",
    updated_at: "2026-07-24T09:00:00Z",
    ...overrides,
  };
}

// owner me:含 create + update + delete 权限。member me:只有 read(无写)。
function makeOwnerMe(): MeResponse {
  return {
    user_id: "u_owner",
    tenant_id: "tn_1",
    email: "owner@example.com",
    platform_role: null,
    roles: ["owner"],
    permissions: [
      "devices:read",
      "devices:create",
      "devices:update",
      "devices:delete",
    ],
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
    permissions: ["devices:read"],
    customer_id: null,
  };
}

// 一个标准的 mutation stub:resolve 立即成功,isPending 默认 false。
function makeMut() {
  return {
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  };
}

// 把所有 use* hooks 喂成稳定 stub,避免每个用例重复设置。``me`` 决定按钮可见性。
function stubStoreBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useDevices.mockReturnValue({ data: [], isLoading: false });
  mocks.useDeviceModels.mockReturnValue({ data: [] });
  mocks.useCustomerProfiles.mockReturnValue({ data: [] });
  mocks.useCreateDevice.mockReturnValue(makeMut());
  mocks.useUpdateDevice.mockReturnValue(makeMut());
  mocks.useDeleteDevice.mockReturnValue(makeMut());
  mocks.useBindDeviceCustomer.mockReturnValue(makeMut());
  mocks.useUnbindDeviceCustomer.mockReturnValue(makeMut());
}

afterEach(() => vi.clearAllMocks());

// 触发 Radix Select 选项(jsdom 不支持 pointer capture,user.click 撞
// hasPointerCapture)。沿用 hq-view.test.tsx pickTarget 的 fireEvent pointer 序列
// (Radix 官方 jsdom 测试推荐姿势)。``trigger`` 是 SelectValue 的可见文本节点。
async function pickSelectOption(
  baseElement: HTMLElement,
  trigger: HTMLElement,
  optionText: string,
) {
  const selectTrigger = trigger.closest("button") ?? trigger;
  fireEvent.pointerDown(selectTrigger, { button: 0 });
  fireEvent.pointerUp(selectTrigger, { button: 0 });
  fireEvent.click(selectTrigger);
  const opt = await within(baseElement.ownerDocument.body).findByText(
    optionText,
  );
  fireEvent.pointerDown(opt, { button: 0 });
  fireEvent.pointerUp(opt, { button: 0 });
  fireEvent.click(opt);
  await Promise.resolve();
}

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

describe("StoreView — device 列表渲染 + CRUD 守卫(devices-page-split 切片 02)", () => {
  it("列表渲染:行展示 serial_number / model 名(从 modelMap 解析)/ status 徽章 / 客户名", () => {
    stubStoreBasics(makeOwnerMe());
    mocks.useDevices.mockReturnValue({
      data: [
        makeDevice({
          id: "dev_1",
          model_id: "m_1",
          serial_number: "SN-2026-0001",
          status: "active",
          customer_id: "c_1",
        }),
      ],
      isLoading: false,
    });
    // modelMap:useDeviceModels 的 feed,store view 靠它把 model_id 解析成名。
    mocks.useDeviceModels.mockReturnValue({
      data: [{ id: "m_1", name: "MODEL-X1" }],
    });
    mocks.useCustomerProfiles.mockReturnValue({
      data: [
        { customer_id: "c_1", customer: { name: "张三" } },
      ],
    });

    const { getByText, getAllByRole } = renderWithProviders(<StoreView />);

    // 序列号 + 模型名(从 modelMap 解析)+ 状态徽章 + 客户名(customerNameOf)。
    expect(getByText("SN-2026-0001")).toBeTruthy();
    expect(getByText("MODEL-X1")).toBeTruthy();
    expect(getByText("运行中")).toBeTruthy(); // STATUS_META.active.label
    expect(getByText("张三")).toBeTruthy();
    // 1 header + 1 body row。
    expect(getAllByRole("row").length).toBe(2);
    // PageHeader 标题。
    expect(getByText("设备")).toBeTruthy();
  });

  it("空态:无设备时渲染 EmptyState + 总数 0", () => {
    stubStoreBasics(makeOwnerMe());
    mocks.useDevices.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<StoreView />);

    expect(getByText(/共 0 台设备/)).toBeTruthy();
    expect(getByText("暂无设备")).toBeTruthy();
    // owner canCreate → EmptyState 提示「点击右上角设备入库」。
    expect(getByText(/点击右上角/)).toBeTruthy();
  });

  it("member 只读:canCreate/canUpdate/canDelete 均假 → 无「设备入库」按钮 + 无操作列 + 无菜单项", () => {
    stubStoreBasics(makeMemberMe());
    mocks.useDevices.mockReturnValue({
      data: [makeDevice({ id: "dev_1", status: "active" })],
      isLoading: false,
    });

    const { queryByText, queryByRole } = renderWithProviders(<StoreView />);

    // member 无 :create → 入库按钮隐藏;无 :update → 无操作列头;无菜单。
    expect(queryByText("设备入库")).toBeNull();
    expect(queryByText("操作")).toBeNull();
    expect(queryByRole("menuitem")).toBeNull();
    // 卡片描述显示「(只读视图)」。
    expect(queryByText(/只读视图/)).toBeTruthy();
  });

  it("owner:点「设备入库」→ DeviceCreateDialog 弹出 → 填表提交触发 useCreateDevice(store path:无 tenant_id)", async () => {
    const user = userEvent.setup();
    const createMut = makeMut();
    stubStoreBasics(makeOwnerMe());
    mocks.useCreateDevice.mockReturnValue(createMut);
    mocks.useDevices.mockReturnValue({ data: [], isLoading: false });
    // model dropdown 选项 —— Create Dialog 的型号 Select 从 models 渲染。
    mocks.useDeviceModels.mockReturnValue({
      data: [{ id: "m_1", name: "MODEL-X1" }],
    });

    const { getByText, baseElement } = renderWithProviders(<StoreView />);

    // owner 有 :create → 入库按钮可见,点击打开 Create Dialog。
    await user.click(getByText("设备入库"));

    const body = baseElement.ownerDocument.body;
    // Dialog 打开(portal 挂在 body),标题「设备入库」再次可见(Dialog 内)。
    expect(
      await within(body).findByRole("heading", { name: "设备入库" }),
    ).toBeTruthy();

    // 选型号 m_1(Radix Select 在 jsdom 撞 hasPointerCapture,沿用 hq-view
    // pickTarget 的 fireEvent pointer 序列触发)。
    const modelTrigger = within(body).getByText("选择设备型号");
    await pickSelectOption(body, modelTrigger, "MODEL-X1");

    // 填序列号。input 是 Dialog 内唯一的文本输入(型号/序列号里只有序列号是 Input)。
    fireEvent.change(within(body).getByPlaceholderText(/SN-2026/), {
      target: { value: "SN-TEST-001" },
    });

    // 提交。Dialog 内「入库」按钮(textContent 包含「入库」)。
    await user.click(within(body).getByRole("button", { name: "入库" }));

    // 核心断言:useCreateDevice.mutateAsync 被以正确 payload 调用。store path:
    // StoreView 传 tenantId=undefined → payload 省略 tenant_id 字段(后端用
    // user.tenant_id)。若 tenantId 被误传,payload 会带上 tenant_id → store
    // 角色越权指定别的租户。
    expect(createMut.mutateAsync).toHaveBeenCalledWith({
      model_id: "m_1",
      serial_number: "SN-TEST-001",
      status: "active",
    });
  });

  it("owner 行内菜单:DropdownMenu 含 编辑 / 绑定客户 / 删除设备 三项", async () => {
    const user = userEvent.setup();
    stubStoreBasics(makeOwnerMe());
    mocks.useDevices.mockReturnValue({
      data: [
        makeDevice({
          id: "dev_1",
          status: "active",
          model_id: "m_1",
          customer_id: null, // 未绑定 → 菜单显示「绑定客户」
        }),
      ],
      isLoading: false,
    });
    mocks.useDeviceModels.mockReturnValue({
      data: [{ id: "m_1", name: "MODEL-X1" }],
    });

    const { baseElement } = renderWithProviders(<StoreView />);
    await openRowMenu(user, baseElement as unknown as HTMLElement);

    // 三项菜单(未绑定 → 「绑定客户」而非「更换/解绑客户」)。用 ``menuitem``
    // role + name 精确定位,避免与 PageHeader subtitle / TableHead 列头里的同名
    // 文案撞(「绑定客户」同时出现在副标题与列表头里)。
    const portal = baseElement.ownerDocument.body;
    for (const label of ["编辑", "绑定客户", "删除设备"]) {
      expect(
        await within(portal).findByRole("menuitem", { name: label }),
      ).toBeInTheDocument();
    }
  });
});
