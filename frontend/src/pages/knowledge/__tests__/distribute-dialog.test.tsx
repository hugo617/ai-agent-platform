// DistributeDialog 下发文档 Dialog(admin-ui slice 03 F4)。
//
// 验证:
//   - F4 模式切换(按门店/按集团)+ 切模式清空对方选择(XOR)。
//   - 按门店多选:点 Checkbox → 提交 → mutateAsync 收 {target_tenant_ids:[...]}。
//   - 按集团单选:Select → 提交 → mutateAsync 收 {target_group_id:...}。
//   - 角色派生目标:group_admin 锁本集团分店(tenants[])/ super 全平台(useAllTenants)。
//   - 空选校验:按门店未选 / 按集团未选 → toast.error + 不调 mutateAsync。
//   - 成功:toast.success + onOpenChange(false) 关闭。
//
// mock 策略:stub useDistributeDocument(返回数组 resolve)/ useGroups / useAllTenants
// / useAuth(驱动 isGroupAdmin/isSuperAdmin)。Radix Select 用 screen 点 combobox。
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from "vitest";
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { DistributeDialog } from "../distribute-dialog";
import type { Group, KnowledgeDistributionRead, MeResponse } from "@/api/types";

const mocks = vi.hoisted(() => ({
  useDistributeDocument: vi.fn() as Mock,
  useGroups: vi.fn() as Mock,
  useAllTenants: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
  useToast: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useDistributeDocument: mocks.useDistributeDocument,
  useGroups: mocks.useGroups,
  useAllTenants: mocks.useAllTenants,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// 部分保留真 ToastProvider(test-utils 需要),只替换 useToast。
vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return { ...actual, useToast: mocks.useToast };
});

// ---- 角色工厂 ----
function makeGroupAdminMe(): MeResponse {
  return {
    user_id: "u_ga",
    tenant_id: "tn_hq",
    email: "ga@example.com",
    platform_role: null,
    roles: ["group_admin"],
    permissions: ["knowledge:read", "knowledge:create", "knowledge:distribute"],
    customer_id: null,
    group_id: "grp_1",
    is_group_admin: true,
  };
}
function makeSuperAdminMe(): MeResponse {
  return {
    user_id: "u_sa",
    tenant_id: "tn_hq",
    email: "sa@example.com",
    platform_role: "super_admin",
    roles: [],
    permissions: [],
    customer_id: null,
  };
}

function makeGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: "grp_1",
    name: "测试集团",
    code: null,
    address: null,
    description: null,
    status: "active",
    sort_order: 0,
    tenant_ids: ["tn_a", "tn_b"],
    tenants: [
      { id: "tn_a", name: "门店A" },
      { id: "tn_b", name: "门店B" },
    ],
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

function makeDist(
  overrides: Partial<KnowledgeDistributionRead> = {},
): KnowledgeDistributionRead {
  return {
    id: "dist_1",
    source_doc_id: "doc_1",
    target_tenant_id: "tn_a",
    distributed_by: "u_sa",
    distributed_at: "2026-08-08T00:00:00Z",
    is_active: true,
    ...overrides,
  };
}

function makeToast() {
  return {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    promise: vi.fn(),
  };
}

function stubBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useDistributeDocument.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue([makeDist()]),
    isPending: false,
  });
  mocks.useGroups.mockReturnValue({ data: [makeGroup()] });
  mocks.useAllTenants.mockReturnValue({ data: [] });
  mocks.useToast.mockReturnValue(makeToast());
}

afterEach(() => vi.clearAllMocks());

// ============================================================================
// F4:模式切换 + 目标范围派生
// ============================================================================

describe("DistributeDialog 模式切换与目标派生(admin-ui slice 03 F4)", () => {
  it("默认「按门店」模式:渲染 Checkbox 门店清单(group_admin 锁本集团分店)", () => {
    stubBasics(makeGroupAdminMe());
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("门店A")).toBeTruthy();
    expect(screen.getByText("门店B")).toBeTruthy();
    expect(screen.getByText("按门店")).toBeTruthy();
  });

  it("group_admin:门店选项只含本集团分店(不含其他集团门店)", () => {
    stubBasics(makeGroupAdminMe());
    mocks.useGroups.mockReturnValue({
      data: [
        makeGroup(),
        makeGroup({
          id: "grp_2",
          name: "其他集团",
          tenants: [{ id: "tn_x", name: "外部门店X" }],
          tenant_ids: ["tn_x"],
        }),
      ],
    });
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("门店A")).toBeTruthy();
    expect(screen.queryByText("外部门店X")).toBeNull();
  });

  it("super_admin:门店选项含全平台门店(useAllTenants)", () => {
    stubBasics(makeSuperAdminMe());
    mocks.useAllTenants.mockReturnValue({
      data: [
        { id: "tn_a", name: "门店A" },
        { id: "tn_z", name: "远端门店Z" },
      ],
    });
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("门店A")).toBeTruthy();
    expect(screen.getByText("远端门店Z")).toBeTruthy();
  });

  it("切到「按集团」:group_admin Select 锁定本集团(disabled + 显示本集团名)", async () => {
    stubBasics(makeGroupAdminMe());
    const user = userEvent.setup();
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByText("按集团"));
    // group_admin 按集团锁定:Select disabled + 显示本集团名。
    expect(screen.getByText("测试集团")).toBeTruthy();
    const lockedSelect = document.querySelector(
      '[role="combobox"][disabled]',
    );
    expect(lockedSelect).toBeTruthy();
  });
});

// ============================================================================
// F4:提交构造 XOR 载荷
// ============================================================================

describe("DistributeDialog 提交构造 XOR 载荷(admin-ui slice 03 F4)", () => {
  it("按门店多选提交:mutateAsync 收 {target_tenant_ids:[tn_a,tn_b]}", async () => {
    stubBasics(makeGroupAdminMe());
    const mutateAsync = vi.fn().mockResolvedValue([
      makeDist(),
      makeDist({ id: "dist_2", target_tenant_id: "tn_b" }),
    ]);
    mocks.useDistributeDocument.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByText("门店A"));
    await user.click(screen.getByText("门店B"));
    await user.click(screen.getByText("确认下发"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({
      target_tenant_ids: ["tn_a", "tn_b"],
    });
  });

  it("按集团单选提交:super mutateAsync 收 {target_group_id:grp_1}", async () => {
    stubBasics(makeSuperAdminMe());
    const mutateAsync = vi.fn().mockResolvedValue([makeDist()]);
    mocks.useDistributeDocument.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByText("按集团"));
    // Radix Select:点 combobox 展开后选 option。
    await user.click(document.querySelector('[role="combobox"]') as HTMLElement);
    await user.click(screen.getByRole("option", { name: "测试集团" }));
    await user.click(screen.getByText("确认下发"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({ target_group_id: "grp_1" });
  });

  it("XOR:按门店选后切按集团,门店选择被清空(提交只带 target_group_id)", async () => {
    stubBasics(makeGroupAdminMe());
    const mutateAsync = vi.fn().mockResolvedValue([makeDist()]);
    mocks.useDistributeDocument.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByText("门店A"));
    await user.click(screen.getByText("按集团"));
    await user.click(screen.getByText("确认下发"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({ target_group_id: "grp_1" });
  });
});

// ============================================================================
// F4:空选校验 + 成功提示
// ============================================================================

describe("DistributeDialog 空选校验与成功提示(admin-ui slice 03 F4)", () => {
  it("按门店未选任何门店:toast.error + 不调 mutateAsync", async () => {
    stubBasics(makeGroupAdminMe());
    const toast = makeToast();
    mocks.useToast.mockReturnValue(toast);
    const mutateAsync = vi.fn().mockResolvedValue([makeDist()]);
    mocks.useDistributeDocument.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(
      <DistributeDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByText("确认下发"));
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("成功:toast.success 显示下发条数 + 关闭 Dialog", async () => {
    stubBasics(makeGroupAdminMe());
    const toast = makeToast();
    mocks.useToast.mockReturnValue(toast);
    const mutateAsync = vi.fn().mockResolvedValue([makeDist(), makeDist({ id: "dist_2" })]);
    mocks.useDistributeDocument.mockReturnValue({ mutateAsync, isPending: false });
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <DistributeDialog
        docId="doc_1"
        docName="手册"
        open
        onOpenChange={onOpenChange}
      />,
    );
    await user.click(screen.getByText("门店A"));
    await user.click(screen.getByText("确认下发"));
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.success.mock.calls[0][0]).toContain("2");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
