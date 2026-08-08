// CategoryManager 分类管理 CRUD(admin-ui slice 04 F6)。
//
// 验证:
//   - F6 scope 分组渲染:platform/group/store 三区块,Category 落到对应区块。
//   - 新建 Dialog:scope Select 按 getAvailableScopes 过滤(角色映射)+ scope 联动
//     (group→绑定本集团提示 / store→绑定本店提示 / platform→无提示)+ 提交构造
//     payload(scope=group 带 group_id / scope=store 带 tenant_id / platform 两者不带)。
//   - 编辑 Dialog:只改 name + sort_order(scope/group_id/tenant_id 不可改 —— 对齐
//     KnowledgeCategoryUpdate),提交只带 {name, sort_order}。
//   - 删除:二次确认 Dialog → 确认后调 useDeleteCategory。
//   - member 守卫:无 knowledge:create → 无「新建分类」按钮 + 无行操作菜单(helper
//     守卫;member 在 index.tsx 层已被挡,这里是双保险)。
//
// mock 策略:stub useKnowledgeCategories/useCreateCategory/useUpdateCategory/
// useDeleteCategory/useAuth(驱动 getAvailableScopes + hasPermission)。Radix Select
// 用 screen 点 combobox(镜像 distribute-dialog.test.tsx)。
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
import { CategoryManager } from "../category-manager";
import type { KnowledgeCategoryRead, MeResponse } from "@/api/types";

const mocks = vi.hoisted(() => ({
  useKnowledgeCategories: vi.fn() as Mock,
  useCreateCategory: vi.fn() as Mock,
  useUpdateCategory: vi.fn() as Mock,
  useDeleteCategory: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
  useToast: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useKnowledgeCategories: mocks.useKnowledgeCategories,
  useCreateCategory: mocks.useCreateCategory,
  useUpdateCategory: mocks.useUpdateCategory,
  useDeleteCategory: mocks.useDeleteCategory,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return { ...actual, useToast: mocks.useToast };
});

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

function makeCategory(
  overrides: Partial<KnowledgeCategoryRead> = {},
): KnowledgeCategoryRead {
  return {
    id: "cat_1",
    name: "话术",
    scope: "store",
    group_id: null,
    tenant_id: "tn_1",
    sort_order: 0,
    is_deleted: false,
    created_at: "2026-08-08T00:00:00Z",
    updated_at: "2026-08-08T00:00:00Z",
    ...overrides,
  };
}

function makeMut() {
  return { mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: false };
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

function stubBasics(me: MeResponse, categories: KnowledgeCategoryRead[] = []) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useKnowledgeCategories.mockReturnValue({
    data: categories,
    isLoading: false,
  });
  mocks.useCreateCategory.mockReturnValue(makeMut());
  mocks.useUpdateCategory.mockReturnValue(makeMut());
  mocks.useDeleteCategory.mockReturnValue(makeMut());
  mocks.useToast.mockReturnValue(makeToast());
}

afterEach(() => vi.clearAllMocks());

// ============================================================================
// F6:scope 分组渲染
// ============================================================================

describe("CategoryManager scope 分组渲染(admin-ui slice 04 F6)", () => {
  it("三个 scope 区块始终渲染(平台/集团/本店层级分类)", () => {
    stubBasics(makeOwnerMe(), []);
    const { getByText } = renderWithProviders(<CategoryManager />);
    expect(getByText("平台层级分类")).toBeTruthy();
    expect(getByText("集团层级分类")).toBeTruthy();
    expect(getByText("本店层级分类")).toBeTruthy();
  });

  it("Category 按 scope 落到对应区块", () => {
    stubBasics(makeSuperAdminMe(), [
      makeCategory({ id: "cat_p", name: "平台手册", scope: "platform" }),
      makeCategory({ id: "cat_g", name: "集团话术", scope: "group" }),
      makeCategory({ id: "cat_s", name: "门店FAQ", scope: "store" }),
    ]);
    const { getByText } = renderWithProviders(<CategoryManager />);
    expect(getByText("平台手册")).toBeTruthy();
    expect(getByText("集团话术")).toBeTruthy();
    expect(getByText("门店FAQ")).toBeTruthy();
  });
});

// ============================================================================
// F6:新建 Dialog scope 过滤(角色映射)
// ============================================================================

describe("CategoryManager 新建 Dialog scope 过滤(admin-ui slice 04 F6)", () => {
  it("owner:新建分类 scope Select 只有「本店」(getAvailableScopes→[store])", async () => {
    stubBasics(makeOwnerMe());
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByText("新建分类"));
    await user.click(document.querySelector('[role="combobox"]') as HTMLElement);
    // owner 只能选 store。
    expect(screen.getByRole("option", { name: "本店" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "平台" })).toBeNull();
    expect(screen.queryByRole("option", { name: "集团" })).toBeNull();
  });

  it("super_admin:新建分类 scope Select 有全部三层(平台/集团/本店)", async () => {
    stubBasics(makeSuperAdminMe());
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByText("新建分类"));
    await user.click(document.querySelector('[role="combobox"]') as HTMLElement);
    expect(screen.getByRole("option", { name: "平台" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "集团" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "本店" })).toBeTruthy();
  });
});

// ============================================================================
// F6:新建 scope 联动 + 提交构造 payload
// ============================================================================

describe("CategoryManager 新建 scope 联动与提交(admin-ui slice 04 F6)", () => {
  it("scope=store:提示绑定本店 + 提交带 tenant_id(默认 me.tenant_id)", async () => {
    stubBasics(makeOwnerMe());
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useCreateCategory.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByText("新建分类"));
    // owner 默认 scope=store(第一个可用),应显示本店绑定提示。
    expect(screen.getByText(/将绑定到当前门店/)).toBeTruthy();
    await user.type(screen.getByPlaceholderText("如 话术 / 产品说明 / FAQ"), "新FAQ");
    await user.click(screen.getByText("确认新建"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({
      name: "新FAQ",
      scope: "store",
      sort_order: 0,
      tenant_id: "tn_1",
    });
  });

  it("scope=group:提示绑定本集团 + 提交带 group_id(默认 me.group_id)", async () => {
    stubBasics(makeGroupAdminMe());
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useCreateCategory.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByText("新建分类"));
    // group_admin 默认 scope=group(第一个可用),应显示本集团绑定提示。
    expect(screen.getByText(/将绑定到当前集团/)).toBeTruthy();
    await user.type(screen.getByPlaceholderText("如 话术 / 产品说明 / FAQ"), "集团分类");
    await user.click(screen.getByText("确认新建"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({
      name: "集团分类",
      scope: "group",
      sort_order: 0,
      group_id: "grp_1",
    });
  });

  it("scope=platform:无绑定提示 + 提交不带 group_id/tenant_id", async () => {
    stubBasics(makeSuperAdminMe());
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useCreateCategory.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByText("新建分类"));
    // super 默认 scope=platform(第一个可用),选 platform。
    await user.click(document.querySelector('[role="combobox"]') as HTMLElement);
    await user.click(screen.getByRole("option", { name: "平台" }));
    await user.type(screen.getByPlaceholderText("如 话术 / 产品说明 / FAQ"), "平台标准");
    await user.click(screen.getByText("确认新建"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const payload = mutateAsync.mock.calls[0][0];
    expect(payload.name).toBe("平台标准");
    expect(payload.scope).toBe("platform");
    expect(payload.group_id).toBeUndefined();
    expect(payload.tenant_id).toBeUndefined();
  });
});

// ============================================================================
// F6:编辑只改 name + sort_order(scope/group_id/tenant_id 不可改)
// ============================================================================

describe("CategoryManager 编辑只改 name/sort_order(admin-ui slice 04 F6)", () => {
  it("编辑 Dialog:scope 只读展示 + 提交只带 {name, sort_order}", async () => {
    stubBasics(makeOwnerMe(), [
      makeCategory({
        id: "cat_edit",
        name: "旧名",
        scope: "store",
        sort_order: 5,
      }),
    ]);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useUpdateCategory.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByRole("button", { name: "分类操作" }));
    await user.click(screen.getByText("编辑"));
    // scope 不可改:层级显示为只读 Badge(无第二个 Select/combobox 出现)。
    expect(screen.getByText("分类层级(不可改)")).toBeTruthy();
    // 改 name 后提交。
    const nameInput = screen.getByPlaceholderText("分类名称") as HTMLInputElement;
    await user.clear(nameInput);
    await user.type(nameInput, "新名");
    await user.click(screen.getByText("保存"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: "cat_edit",
      payload: { name: "新名", sort_order: 5 },
    });
  });
});

// ============================================================================
// F6:删除二次确认
// ============================================================================

describe("CategoryManager 删除二次确认(admin-ui slice 04 F6)", () => {
  it("点删除 → 二次确认 Dialog → 确认后调 useDeleteCategory(id)", async () => {
    stubBasics(makeOwnerMe(), [
      makeCategory({ id: "cat_del", name: "待删", scope: "store" }),
    ]);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useDeleteCategory.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByRole("button", { name: "分类操作" }));
    await user.click(screen.getByText("删除"));
    // 二次确认 Dialog 出现。
    expect(screen.getByText("确认删除分类")).toBeTruthy();
    await user.click(screen.getByText("确认删除"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith("cat_del");
  });

  it("二次确认点取消 → 不调 useDeleteCategory", async () => {
    stubBasics(makeOwnerMe(), [
      makeCategory({ id: "cat_del", name: "待删", scope: "store" }),
    ]);
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useDeleteCategory.mockReturnValue({ mutateAsync, isPending: false });
    const user = userEvent.setup();
    renderWithProviders(<CategoryManager />);
    await user.click(screen.getByRole("button", { name: "分类操作" }));
    await user.click(screen.getByText("删除"));
    await user.click(screen.getByText("取消"));
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});

// ============================================================================
// F6:member 守卫(无写权限 → 无新建按钮 + 无行操作)
// ============================================================================

describe("CategoryManager member 守卫(admin-ui slice 04 F6)", () => {
  it("member:无「新建分类」按钮(getAvailableScopes→[] + 无 knowledge:create)", () => {
    stubBasics(makeMemberMe(), []);
    const { queryByText } = renderWithProviders(<CategoryManager />);
    expect(queryByText("新建分类")).toBeNull();
  });

  it("member:有分类数据时无行操作菜单(无「分类操作」aria-label)", () => {
    stubBasics(makeMemberMe(), [
      makeCategory({ id: "cat_s", name: "只读分类", scope: "store" }),
    ]);
    const { queryByRole, getByText } = renderWithProviders(<CategoryManager />);
    // 分类名仍渲染(member 可读),但无操作菜单。
    expect(getByText("只读分类")).toBeTruthy();
    expect(queryByRole("button", { name: "分类操作" })).toBeNull();
  });
});
