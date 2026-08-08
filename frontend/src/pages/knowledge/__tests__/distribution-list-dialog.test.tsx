// DistributionListDialog 管理下发(已下发列表 + 撤回,admin-ui slice 03 F5)。
//
// 验证:
//   - F5 列表渲染:useDistributions 返回 N 条 → 渲染 N 个门店名。
//   - is_active 状态:生效 Badge / 已撤回灰显。
//   - 撤回按钮仅在 is_active=true 行出现(已撤回行无按钮)。
//   - 撤回二次确认:点撤回 → 出现「确认撤回」Dialog → 确认 → mutateAsync(distId)。
//   - 空态:返回 [] → 「该文档暂无下发关系」。
//
// mock 策略:stub useDistributions / useRevokeDistribution / useAllTenants /
// useGroups(门店名解析)。toast 部分保留 ToastProvider。
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
import { DistributionListDialog } from "../distribution-list-dialog";
import type { Group, KnowledgeDistributionRead } from "@/api/types";

const mocks = vi.hoisted(() => ({
  useDistributions: vi.fn() as Mock,
  useRevokeDistribution: vi.fn() as Mock,
  useAllTenants: vi.fn() as Mock,
  useGroups: vi.fn() as Mock,
  useToast: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useDistributions: mocks.useDistributions,
  useRevokeDistribution: mocks.useRevokeDistribution,
  useAllTenants: mocks.useAllTenants,
  useGroups: mocks.useGroups,
}));

// 部分保留真 ToastProvider(test-utils 需要),只替换 useToast。
vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return { ...actual, useToast: mocks.useToast };
});

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

function makeToast() {
  return {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    promise: vi.fn(),
  };
}

function stubList(dists: KnowledgeDistributionRead[]) {
  mocks.useDistributions.mockReturnValue({
    data: dists,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
  mocks.useRevokeDistribution.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  });
  mocks.useAllTenants.mockReturnValue({ data: [] });
  mocks.useGroups.mockReturnValue({ data: [makeGroup()] });
  mocks.useToast.mockReturnValue(makeToast());
}

afterEach(() => vi.clearAllMocks());

// ============================================================================
// F5:列表渲染 + 状态显示
// ============================================================================

describe("DistributionListDialog 列表渲染与状态(admin-ui slice 03 F5)", () => {
  it("useDistributions 返回 2 条:渲染 2 个门店名(从 useGroups.tenants 解析名)", () => {
    stubList([
      makeDist({ id: "dist_1", target_tenant_id: "tn_a" }),
      makeDist({ id: "dist_2", target_tenant_id: "tn_b" }),
    ]);
    renderWithProviders(
      <DistributionListDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("门店A")).toBeTruthy();
    expect(screen.getByText("门店B")).toBeTruthy();
  });

  it("生效行(is_active=true):显示「生效」Badge + 「撤回」按钮", () => {
    stubList([makeDist({ is_active: true })]);
    renderWithProviders(
      <DistributionListDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("生效")).toBeTruthy();
    expect(screen.getByText("撤回")).toBeTruthy();
  });

  it("已撤回行(is_active=false):显示「已撤回」灰字 + 无「撤回」按钮", () => {
    stubList([makeDist({ is_active: false })]);
    renderWithProviders(
      <DistributionListDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("已撤回")).toBeTruthy();
    expect(screen.queryByText("撤回")).toBeNull();
  });
});

// ============================================================================
// F5:撤回二次确认 + 调用
// ============================================================================

describe("DistributionListDialog 撤回流程(admin-ui slice 03 F5)", () => {
  it("点「撤回」:出现二次确认 Dialog(「确认撤回」标题)", async () => {
    stubList([makeDist({ id: "dist_1", target_tenant_id: "tn_a", is_active: true })]);
    const user = userEvent.setup();
    renderWithProviders(
      <DistributionListDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByRole("button", { name: "撤回" }));
    // 二次确认 Dialog 标题出现(用 heading role 精确定位,避免与按钮文案混淆)。
    expect(screen.getByRole("heading", { name: "确认撤回" })).toBeTruthy();
  });

  it("确认撤回:调 useRevokeDistribution.mutateAsync(distId)", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useDistributions.mockReturnValue({
      data: [makeDist({ id: "dist_1", is_active: true })],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    mocks.useRevokeDistribution.mockReturnValue({ mutateAsync, isPending: false });
    mocks.useAllTenants.mockReturnValue({ data: [] });
    mocks.useGroups.mockReturnValue({ data: [makeGroup()] });
    mocks.useToast.mockReturnValue(makeToast());
    const user = userEvent.setup();
    renderWithProviders(
      <DistributionListDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    await user.click(screen.getByRole("button", { name: "撤回" }));
    await user.click(screen.getByRole("button", { name: "确认撤回" }));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("dist_1"));
  });
});

// ============================================================================
// F5:空态
// ============================================================================

describe("DistributionListDialog 空态(admin-ui slice 03 F5)", () => {
  it("无下发关系:显示空态文案「该文档暂无下发关系」", () => {
    stubList([]);
    renderWithProviders(
      <DistributionListDialog docId="doc_1" open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("该文档暂无下发关系")).toBeTruthy();
  });
});
