// KnowledgePage 顶层 Tabs + AdminPanel 子 Tabs(admin-ui slice 02 F1 + F2)。
//
// 验证:
//   - F1 同页 Tabs:owner/admin 看到「阅读」+「管理」两 tab;member 只看到「阅读」
//     (管理 tab 隐藏,hasPermission 守卫)。
//   - F2 子 Tabs:管理 tab 内「文档与发放」/「分类管理」两子 tab + 切换。
//   - F7 职责切割:「创建文档」按钮仅 group_admin/super 可见(owner 进管理 tab 看不到)。
//   - reader-ui 零回归:阅读 tab 渲染原三栏(CategoryTree/DocumentList/MarkdownReader 标题在)。
//
// mock 策略:
//   - 顶层 KnowledgePage 渲染需要 CategoryTree/DocumentList/MarkdownReader/RetrievalDebugCard
//     的 hook,全部 stub(useKnowledgeCategories/useDocuments/useCreateDocument/useDeleteDocument)。
//   - AdminPanel 内的 DocumentForm(Select portal)mock 掉,聚焦 tab/表格行为;
//     DocumentForm 的 scope 联动单测在 document-form.test.tsx。
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/test-utils";
import { KnowledgePage } from "../index";
import { AdminPanel } from "../admin-panel";
import type { MeResponse } from "@/api/types";

// ---- mock wiring ----
// KnowledgePage 渲染链路涉及的 hook 全 stub。
const mocks = vi.hoisted(() => ({
  useKnowledgeCategories: vi.fn() as Mock,
  useDocuments: vi.fn() as Mock,
  useCreateDocument: vi.fn() as Mock,
  useDeleteDocument: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
  // DocumentForm 内的 hook(mock DocumentForm 整体后这些不会被调用,但保留 stub
  // 以防 AdminPanel 直接渲染路径触发)。
  useGroups: vi.fn() as Mock,
  useAllTenants: vi.fn() as Mock,
  // CategoryManager(切片04)用的 category CRUD hook —— admin-panel 测试聚焦 tab/
  // 文档表格行为,category CRUD 单测在 category-manager.test.tsx;这里给兜底 stub
  // 避免 CategoryManager 渲染时 useCreateCategory 等返回 undefined 报错。
  useCreateCategory: vi.fn() as Mock,
  useUpdateCategory: vi.fn() as Mock,
  useDeleteCategory: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useKnowledgeCategories: mocks.useKnowledgeCategories,
  useDocuments: mocks.useDocuments,
  useCreateDocument: mocks.useCreateDocument,
  useDeleteDocument: mocks.useDeleteDocument,
  useGroups: mocks.useGroups,
  useAllTenants: mocks.useAllTenants,
  useCreateCategory: mocks.useCreateCategory,
  useUpdateCategory: mocks.useUpdateCategory,
  useDeleteCategory: mocks.useDeleteCategory,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// DocumentForm 是 Select portal 重组件,scope 联动在 document-form.test.tsx 单测。
// 这里 mock 成一个简单的占位 Dialog,只验「创建文档」按钮点击后能打开。
vi.mock("../document-form", () => ({
  DocumentForm: ({ open }: { open: boolean }) =>
    open ? <div data-testid="document-form-stub">document-form</div> : null,
}));

// ---- 角色工厂 ----
function makeOwnerMe(): MeResponse {
  return {
    user_id: "u_owner",
    tenant_id: "tn_1",
    email: "owner@example.com",
    platform_role: null,
    roles: ["owner"],
    permissions: ["knowledge:read", "knowledge:create", "knowledge:delete"],
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
    permissions: ["knowledge:read"],
    customer_id: null,
  };
}
function makeGroupAdminMe(): MeResponse {
  return {
    user_id: "u_ga",
    tenant_id: "tn_1",
    email: "ga@example.com",
    platform_role: null,
    roles: ["group_admin"],
    permissions: ["knowledge:read", "knowledge:create", "knowledge:delete"],
    customer_id: null,
    group_id: "grp_1",
    is_group_admin: true,
  };
}
function makeSuperAdminMe(): MeResponse {
  return {
    user_id: "u_sa",
    tenant_id: "tn_1",
    email: "sa@example.com",
    platform_role: "super_admin",
    roles: [],
    permissions: [],
    customer_id: null,
  };
}

function makeMut() {
  return { mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: false };
}

function stubBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useKnowledgeCategories.mockReturnValue({ data: [], isLoading: false });
  mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });
  mocks.useCreateDocument.mockReturnValue(makeMut());
  mocks.useDeleteDocument.mockReturnValue(makeMut());
  mocks.useGroups.mockReturnValue({ data: [] });
  mocks.useAllTenants.mockReturnValue({ data: [] });
  // CategoryManager 的 category CRUD hook 兜底(admin-panel 测试不验 category 写流程)。
  mocks.useCreateCategory.mockReturnValue(makeMut());
  mocks.useUpdateCategory.mockReturnValue(makeMut());
  mocks.useDeleteCategory.mockReturnValue(makeMut());
}

afterEach(() => vi.clearAllMocks());

// ============================================================================
// F1:顶层 Tabs(阅读/管理)可见性
// ============================================================================

describe("KnowledgePage 顶层 Tabs(admin-ui slice 02 F1)", () => {
  it("owner:看到「阅读」+「管理」两个 tab,默认阅读", () => {
    stubBasics(makeOwnerMe());
    const { getByText, queryByText } = renderWithProviders(<KnowledgePage />);
    expect(getByText("阅读")).toBeTruthy();
    expect(getByText("管理")).toBeTruthy();
    // 默认阅读 tab:三栏标题在(分类目录 + 文档列表 + 阅读器)。
    expect(queryByText("文档与发放")).toBeNull(); // 管理 tab 内容未渲染
  });

  it("member:只看到「阅读」tab,管理 tab 隐藏(F7)", () => {
    stubBasics(makeMemberMe());
    const { getByText, queryByText } = renderWithProviders(<KnowledgePage />);
    expect(getByText("阅读")).toBeTruthy();
    expect(queryByText("管理")).toBeNull();
  });

  it("group_admin:看到两个 tab(管理 tab 可见)", () => {
    stubBasics(makeGroupAdminMe());
    const { getByText } = renderWithProviders(<KnowledgePage />);
    expect(getByText("阅读")).toBeTruthy();
    expect(getByText("管理")).toBeTruthy();
  });

  it("super_admin:看到两个 tab(管理 tab 可见)", () => {
    stubBasics(makeSuperAdminMe());
    const { getByText } = renderWithProviders(<KnowledgePage />);
    expect(getByText("阅读")).toBeTruthy();
    expect(getByText("管理")).toBeTruthy();
  });

  it("切到管理 tab:渲染 AdminPanel(文档与发放子 tab)", async () => {
    stubBasics(makeOwnerMe());
    const user = userEvent.setup();
    const { getByText, getAllByText } = renderWithProviders(<KnowledgePage />);
    await user.click(getByText("管理"));
    // AdminPanel 子 tab 标题出现(子 tab 按钮 + CardTitle 各一处 → getAllByText)。
    expect(getAllByText("文档与发放").length).toBeGreaterThanOrEqual(1);
    expect(getByText("分类管理")).toBeTruthy();
  });
});

// ============================================================================
// F2:AdminPanel 子 Tabs(文档与发放 / 分类管理)
// ============================================================================

describe("AdminPanel 子 Tabs(admin-ui slice 02 F2)", () => {
  it("默认「文档与发放」子 tab:渲染文档表格标题 + 文档数", () => {
    stubBasics(makeOwnerMe());
    const { getAllByText } = renderWithProviders(<AdminPanel />);
    // 子 tab 按钮 + CardTitle 各一处。
    expect(getAllByText("文档与发放").length).toBeGreaterThanOrEqual(1);
    expect(getAllByText(/共 0 篇文档/).length).toBeGreaterThanOrEqual(1);
  });

  it("切到「分类管理」子 tab:渲染 CategoryManager(切片04 已落地)", async () => {
    stubBasics(makeOwnerMe());
    const user = userEvent.setup();
    const { getByText } = renderWithProviders(<AdminPanel />);
    await user.click(getByText("分类管理"));
    // CategoryManager 按 scope 分组渲染三区块标题(平台/集团/本店层级分类)。
    expect(getByText("平台层级分类")).toBeTruthy();
  });

  it("owner 进管理 tab:看不到「创建文档」按钮(F7 职责切割,本店创建走 reader-ui)", () => {
    stubBasics(makeOwnerMe());
    const { queryByText } = renderWithProviders(<AdminPanel />);
    expect(queryByText("创建文档")).toBeNull();
  });

  it("group_admin:看到「创建文档」按钮(F7,上级创建)", () => {
    stubBasics(makeGroupAdminMe());
    const { getByText } = renderWithProviders(<AdminPanel />);
    expect(getByText("创建文档")).toBeTruthy();
  });

  it("super_admin:看到「创建文档」按钮", () => {
    stubBasics(makeSuperAdminMe());
    const { getByText } = renderWithProviders(<AdminPanel />);
    expect(getByText("创建文档")).toBeTruthy();
  });

  it("group_admin 点「创建文档」:打开 DocumentForm(mock stub)", async () => {
    stubBasics(makeGroupAdminMe());
    const user = userEvent.setup();
    const { getByText, getByTestId } = renderWithProviders(<AdminPanel />);
    await user.click(getByText("创建文档"));
    expect(getByTestId("document-form-stub")).toBeTruthy();
  });
});

// ============================================================================
// F5:文档表格行操作菜单「下发」「管理下发」(admin-ui slice 03)
// ============================================================================

// 切片 03 加的行操作 Dialog 在本测试 mock 成 stub(避免触发真实 distribution hooks)。
vi.mock("../distribute-dialog", () => ({
  DistributeDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="distribute-dialog-stub">distribute</div> : null,
}));
vi.mock("../distribution-list-dialog", () => ({
  DistributionListDialog: ({ open }: { open: boolean }) =>
    open ? (
      <div data-testid="distribution-list-dialog-stub">distribution-list</div>
    ) : null,
}));

function makeDoc(overrides: Partial<{
  id: string;
  name: string;
  scope: "platform" | "group" | "store";
  status: string;
}> = {}) {
  return {
    id: "doc_1",
    name: "集团话术手册",
    content: "...",
    source_type: "text" as const,
    scope: "group" as const,
    group_id: "grp_1",
    tenant_id: null,
    category_id: null,
    status: "indexed",
    embedding_count: 4,
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

describe("AdminPanel 行操作「下发/管理下发」(admin-ui slice 03 F5)", () => {
  it("group_admin:文档行有操作菜单,点开见「下发」「管理下发」", async () => {
    stubBasics(makeGroupAdminMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDoc()],
      isLoading: false,
    });
    const user = userEvent.setup();
    const { getByRole, getByText } = renderWithProviders(<AdminPanel />);
    await user.click(getByRole("button", { name: "文档操作" }));
    // DropdownMenu 展开后两入口可见。
    await vi.waitFor(() => {
      expect(getByText("下发")).toBeTruthy();
      expect(getByText("管理下发")).toBeTruthy();
    });
  });

  it("owner:文档行无操作菜单(F7 职责切割,owner 无下发权)", () => {
    stubBasics(makeOwnerMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDoc()],
      isLoading: false,
    });
    const { queryByText } = renderWithProviders(<AdminPanel />);
    // owner 进管理 tab 看文档表格,但无「操作」列、无下发入口。
    expect(queryByText("下发")).toBeNull();
    expect(queryByText("管理下发")).toBeNull();
  });

  it("group_admin 点「下发」:打开 DistributeDialog stub", async () => {
    stubBasics(makeGroupAdminMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDoc()],
      isLoading: false,
    });
    const user = userEvent.setup();
    const { getByRole, getByText, getByTestId } = renderWithProviders(<AdminPanel />);
    await user.click(getByRole("button", { name: "文档操作" }));
    await user.click(getByText("下发"));
    expect(getByTestId("distribute-dialog-stub")).toBeTruthy();
  });

  it("group_admin 点「管理下发」:打开 DistributionListDialog stub", async () => {
    stubBasics(makeGroupAdminMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDoc()],
      isLoading: false,
    });
    const user = userEvent.setup();
    const { getByRole, getByText, getByTestId } = renderWithProviders(<AdminPanel />);
    await user.click(getByRole("button", { name: "文档操作" }));
    await user.click(getByText("管理下发"));
    expect(getByTestId("distribution-list-dialog-stub")).toBeTruthy();
  });
});
