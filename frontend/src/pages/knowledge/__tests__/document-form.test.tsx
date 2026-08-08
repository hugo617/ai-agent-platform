// DocumentForm admin 创建文档表单(admin-ui slice 02 F3 scope 联动)。
//
// 验证:
//   - F3 scope 下拉按角色过滤:getAvailableScopes(member 空 / owner 仅 store /
//     group_admin group+store / super 全)。
//   - scope 联动:platform → 隐藏 group/tenant;group → 显示 group(group_admin 锁定
//     me.group_id / super 可选);store → 显示 tenant(owner/group_admin 锁定本店 /
//     super 可选)。
//   - category 下拉:按所选 scope 过滤(同 scope categories 出现)。
//   - 提交透传:useCreateDocument 收到带 scope/group_id/tenant_id/category_id 的 payload。
//
// mock 策略:stub useCreateDocument + useKnowledgeCategories + useGroups + useAllTenants
// + useAuth(驱动 getAvailableScopes)。Radix Select 在 jsdom 下用 userEvent.click 点开。
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
import { DocumentForm } from "../document-form";
import type {
  KnowledgeCategoryRead,
  MeResponse,
} from "@/api/types";

const mocks = vi.hoisted(() => ({
  useCreateDocument: vi.fn() as Mock,
  useKnowledgeCategories: vi.fn() as Mock,
  useGroups: vi.fn() as Mock,
  useAllTenants: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useCreateDocument: mocks.useCreateDocument,
  useKnowledgeCategories: mocks.useKnowledgeCategories,
  useGroups: mocks.useGroups,
  useAllTenants: mocks.useAllTenants,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// ---- 角色工厂 ----
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

function makeCategory(
  overrides: Partial<KnowledgeCategoryRead> = {},
): KnowledgeCategoryRead {
  return {
    id: "cat_1",
    name: "产品手册",
    scope: "store",
    group_id: null,
    tenant_id: "tn_1",
    sort_order: 0,
    is_deleted: false,
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

function stubBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useCreateDocument.mockReturnValue(makeMut());
  mocks.useKnowledgeCategories.mockReturnValue({ data: [], isLoading: false });
  mocks.useGroups.mockReturnValue({ data: [] });
  mocks.useAllTenants.mockReturnValue({ data: [] });
}

afterEach(() => vi.clearAllMocks());

// 辅助:打开 scope Select 并断言可选项。Radix Select 在 jsdom 下点 trigger 展开
// Content(portal),然后读 SelectItem 文本。
async function openScopeSelectAndGetOptions(user: ReturnType<typeof userEvent.setup>) {
  // trigger 文案含 placeholder "选择层级"。
  const trigger = document.querySelector(
    '[role="combobox"]',
  ) as HTMLElement;
  await user.click(trigger);
  // SelectContent portal 挂在 body;SelectItem 的 role=option。
  const options = Array.from(
    document.querySelectorAll('[role="option"]'),
  ).map((o) => o.textContent ?? "");
  return options;
}

describe("DocumentForm scope 下拉按角色过滤(admin-ui slice 02 F3)", () => {
  it("group_admin:scope 下拉含「集团」+「本店」(无平台)", async () => {
    stubBasics(makeGroupAdminMe());
    const user = userEvent.setup();
    renderWithProviders(<DocumentForm open={true} onOpenChange={vi.fn()} />);
    const options = await openScopeSelectAndGetOptions(user);
    expect(options).toContain("集团");
    expect(options).toContain("本店");
    expect(options).not.toContain("平台");
  });

  it("super_admin:scope 下拉含「平台」+「集团」+「本店」(全选)", async () => {
    stubBasics(makeSuperAdminMe());
    const user = userEvent.setup();
    renderWithProviders(<DocumentForm open={true} onOpenChange={vi.fn()} />);
    const options = await openScopeSelectAndGetOptions(user);
    expect(options).toContain("平台");
    expect(options).toContain("集团");
    expect(options).toContain("本店");
  });
});

describe("DocumentForm scope 联动显隐(admin-ui slice 02 F3)", () => {
  it("默认 scope(group_admin=集团):显示「目标集团」字段且锁定 me.group_id", () => {
    stubBasics(makeGroupAdminMe());
    renderWithProviders(<DocumentForm open={true} onOpenChange={vi.fn()} />);
    // group_admin 默认 scope=group + groupId=me.group_id 锁定(disabled Input)。
    expect(document.querySelector('input[disabled]')?.getAttribute("value")).toBe("grp_1");
    expect(document.body.textContent).toContain("目标集团");
  });

  it("super_admin 默认 scope=platform:不显示 group/tenant 字段", () => {
    stubBasics(makeSuperAdminMe());
    renderWithProviders(<DocumentForm open={true} onOpenChange={vi.fn()} />);
    // super 默认 scope=platform → 无 group/tenant 字段。
    expect(document.body.textContent).not.toContain("目标集团");
    expect(document.body.textContent).not.toContain("目标门店");
  });
});

describe("DocumentForm 提交透传 scope/group_id(admin-ui slice 02)", () => {
  it("group_admin 提交:useCreateDocument 收到 scope=group + group_id=me.group_id", async () => {
    // 用一个稳定的 mutateAsync 引用,跨 mock 调用可观察。
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mocks.useAuth.mockReturnValue({ me: makeGroupAdminMe() });
    mocks.useCreateDocument.mockReturnValue({ mutateAsync, isPending: false });
    mocks.useKnowledgeCategories.mockReturnValue({ data: [], isLoading: false });
    mocks.useGroups.mockReturnValue({ data: [] });
    mocks.useAllTenants.mockReturnValue({ data: [] });

    const user = userEvent.setup();
    const { getByPlaceholderText, getByText } = renderWithProviders(
      <DocumentForm open={true} onOpenChange={vi.fn()} />,
    );

    // 填名称 + 内容(scope 默认 group,group_id 默认锁定 grp_1)。
    await user.type(getByPlaceholderText(/集团统一话术/), "集团统一话术");
    await user.type(getByPlaceholderText(/产品说明/), "开场欢迎光临");
    await user.click(getByText("创建并索引"));

    // mutateAsync 收到带 scope=group + group_id=grp_1 的 payload。
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    const payload = mutateAsync.mock.calls[0][0];
    expect(payload.name).toBe("集团统一话术");
    expect(payload.scope).toBe("group");
    expect(payload.group_id).toBe("grp_1");
    // platform/store 字段不应带。
    expect(payload.tenant_id).toBeUndefined();
  });

  it("group_admin group_id 锁定:不可改(disabled Input 显示 me.group_id)", () => {
    stubBasics(makeGroupAdminMe());
    renderWithProviders(<DocumentForm open={true} onOpenChange={vi.fn()} />);
    const disabledInput = document.querySelector('input[disabled]') as HTMLInputElement;
    expect(disabledInput).toBeTruthy();
    expect(disabledInput.value).toBe("grp_1");
  });
});

describe("DocumentForm category 下拉按 scope 过滤(admin-ui slice 02)", () => {
  it("selected scope 有匹配 categories:category 下拉出现(同 scope)", async () => {
    mocks.useAuth.mockReturnValue({ me: makeGroupAdminMe() });
    mocks.useCreateDocument.mockReturnValue(makeMut());
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "cat_g", scope: "group", name: "集团话术类" }),
        makeCategory({ id: "cat_s", scope: "store", name: "本店FAQ类" }),
      ],
      isLoading: false,
    });
    mocks.useGroups.mockReturnValue({ data: [] });
    mocks.useAllTenants.mockReturnValue({ data: [] });

    const user = userEvent.setup();
    renderWithProviders(<DocumentForm open={true} onOpenChange={vi.fn()} />);

    // group_admin 默认 scope=group → category 下拉出现(scope 匹配的 group 类)。
    // 点开 category Select(第二个 combobox)。
    const combos = document.querySelectorAll('[role="combobox"]');
    // 第一个 = scope Select,第二个 = category Select。
    expect(combos.length).toBeGreaterThanOrEqual(2);
    await user.click(combos[1]);
    const options = Array.from(document.querySelectorAll('[role="option"]')).map(
      (o) => o.textContent ?? "",
    );
    // group scope 的 category 出现;store scope 的不出现。
    expect(options).toContain("集团话术类");
    expect(options).toContain("不归类");
    expect(options).not.toContain("本店FAQ类");
  });
});
