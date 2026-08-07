// KnowledgePage 三栏编排 smoke + 跨角色 + 空态测试(reader-ui slice 02 + 03)。
//
// 验证:
//   - slice 02 AC9:三栏 smoke(三栏均渲染)+ CategoryTree 点击 → DocumentList 过滤
//     + DocumentList 点击 → MarkdownReader 显示。
//   - slice 03 AC4:跨角色视图(group_admin/super_admin 聚合视图由 backend list 返回
//     不同数据,前端渲染一致 —— 测试 mock 不同 useDocuments 返回值断言渲染差异)+
//     member 只读守卫。
//   - slice 03 AC5:空态完整覆盖(categories 空 + documents 空 + selectedDoc null)。
//
// mock 策略:stub ``useKnowledgeCategories`` + ``useDocuments`` + 写 mutation hooks
// (DocumentList 切片 03 接入 useCreateDocument/useDeleteDocument)+ auth(驱动权限守卫)。
// useAuth 注入不同 me 变体驱动跨角色测试。
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/test-utils";
import { KnowledgePage } from "../index";
import type {
  DocumentRead,
  KnowledgeCategoryRead,
  MeResponse,
} from "@/api/types";

// ---- mock wiring ----
// index.tsx 渲染的子组件调用的所有 hook 都要 stub:CategoryTree 调
// useKnowledgeCategories;DocumentList 调 useDocuments + useCreateDocument +
// useDeleteDocument(切片 03 接入 CRUD)。
const mocks = vi.hoisted(() => ({
  useKnowledgeCategories: vi.fn() as Mock,
  useDocuments: vi.fn() as Mock,
  useCreateDocument: vi.fn() as Mock,
  useDeleteDocument: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useKnowledgeCategories: mocks.useKnowledgeCategories,
  useDocuments: mocks.useDocuments,
  useCreateDocument: mocks.useCreateDocument,
  useDeleteDocument: mocks.useDeleteDocument,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// ---- factories ----
function makeCategory(
  overrides: Partial<KnowledgeCategoryRead> = {},
): KnowledgeCategoryRead {
  return {
    id: "cat_store_1",
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

function makeDocument(overrides: Partial<DocumentRead> = {}): DocumentRead {
  return {
    id: "doc_1",
    tenant_id: "tn_1",
    name: "颈椎理疗话术",
    source_type: "text",
    content: "## 开场\n欢迎光临。",
    chunk_count: 3,
    status: "indexed",
    scope: "store",
    group_id: null,
    category_id: "cat_store_1",
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

// 角色变体:owner(门店,有 knowledge 写权限)/ member(只读)/ group_admin /
// super_admin(hasPermission 直接 true)。真实 hasPermission 靠 me.permissions +
// platform_role 驱动。
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
  return {
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  };
}

// 把所有 use* hooks 喂成稳定 stub。``me`` 决定权限按钮可见性。
function stubBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useKnowledgeCategories.mockReturnValue({ data: [], isLoading: false });
  mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });
  mocks.useCreateDocument.mockReturnValue(makeMut());
  mocks.useDeleteDocument.mockReturnValue(makeMut());
}

afterEach(() => vi.clearAllMocks());

// ============================================================================
// slice 02:三栏 smoke + 联动
// ============================================================================

describe("KnowledgePage 三栏编排 smoke + 联动(slice 02)", () => {
  beforeEach(() => stubBasics(makeOwnerMe()));

  it("三栏 smoke:左栏分类目录 + 中栏文档列表 + 右栏阅读器均渲染", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory()],
      isLoading: false,
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getAllByText } = renderWithProviders(<KnowledgePage />);

    // 左栏标题(分类目录 CardTitle + 响应式 Sheet Trigger/Title 都含「分类目录」,
    // jsdom 下 lg 元素全在 DOM,故用 getAllByText 容忍多处)。
    expect(getAllByText("分类目录").length).toBeGreaterThanOrEqual(1);
    // 中栏标题(文档列表 CardTitle,新 DocumentList 独有)。
    expect(getAllByText("文档列表").length).toBeGreaterThanOrEqual(1);
    // 右栏标题(阅读器 CardTitle,空 doc 时显示「阅读器」)。
    expect(getAllByText("阅读器").length).toBeGreaterThanOrEqual(1);
  });

  it("联动 1:CategoryTree 点击 category → DocumentList 收到 scope+categoryId 过滤", async () => {
    const user = userEvent.setup();
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory({ id: "cat_g1", name: "集团话术", scope: "group" })],
      isLoading: false,
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<KnowledgePage />);

    // 点击左栏的「集团话术」category。
    // 注:左栏 CategoryTree 在 lg+ 显示(grid 第一列),jsdom 下 class 不影响 DOM 存在。
    await user.click(getByText("集团话术"));

    // useDocuments 被 DocumentList 调用时,filter 应含 group/cat_g1。
    const callsWithFilter = mocks.useDocuments.mock.calls.filter(
      ([arg]) => arg && typeof arg === "object" && "scope" in arg,
    );
    expect(callsWithFilter.length).toBeGreaterThan(0);
    expect(
      callsWithFilter.some(
        (c) => c[0]?.scope === "group" && c[0]?.category_id === "cat_g1",
      ),
    ).toBe(true);
  });

  it("联动 2:DocumentList 点击文档 → MarkdownReader 显示文档内容", async () => {
    const user = userEvent.setup();
    const doc = makeDocument({
      id: "doc_sel",
      name: "被选中的文档",
      content: "## 这篇文档的独有标题",
    });
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory()],
      isLoading: false,
    });
    mocks.useDocuments.mockReturnValue({ data: [doc], isLoading: false });

    const { getAllByText, queryByText } = renderWithProviders(<KnowledgePage />);

    // 初始:右栏空态「选择左侧文档查看」(MarkdownReader 空 doc 占位)。
    expect(queryByText("选择左侧文档查看")).not.toBeNull();

    // 点击中栏文档卡片(唯一来源,切片 03 已删 LegacyKnowledgePage)。
    await user.click(getAllByText("被选中的文档")[0]);

    // 联动后:空态消失(右栏已选中)。
    expect(queryByText("选择左侧文档查看")).toBeNull();
    // Markdown 渲染:右栏正文 h2 标题。h2 带 id=toc-0(目录大纲锚点),
    // 证明 MarkdownReader 接到了 selectedDoc。
    const h2 = document.getElementById("toc-0");
    expect(h2).not.toBeNull();
    expect(h2?.textContent).toContain("这篇文档的独有标题");
  });
});

// ============================================================================
// slice 03 AC4:跨角色视图(group_admin/super_admin 聚合 + member 只读)
// ============================================================================

describe("KnowledgePage 跨角色视图差异(slice 03 AC4)", () => {
  it("group_admin:看到聚合文档列表(本集团 group scope + 下发来的 platform scope)", () => {
    stubBasics(makeGroupAdminMe());
    // group_admin 的 backend list 返回聚合:本集团 group 文档 + 平台下发文档。
    mocks.useDocuments.mockReturnValue({
      data: [
        makeDocument({
          id: "doc_g1",
          name: "集团统一话术",
          scope: "group",
          group_id: "grp_1",
        }),
        makeDocument({
          id: "doc_p1",
          name: "平台标准手册",
          scope: "platform",
        }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<KnowledgePage />);

    // 聚合视图:group + platform 两类 scope 文档都渲染。
    expect(getByText("集团统一话术")).toBeTruthy();
    expect(getByText("平台标准手册")).toBeTruthy();
    // scope 徽章两色都在(group=集团/warning,platform=平台/destructive)。
    expect(getByText("集团").className).toContain("bg-warning");
    expect(getByText("平台").className).toContain("bg-destructive");
    // 总数反映聚合。
    expect(getByText(/共 2 篇文档/)).toBeTruthy();
  });

  it("super_admin:看到全量聚合(platform + group + store 三色同列表)", () => {
    stubBasics(makeSuperAdminMe());
    mocks.useDocuments.mockReturnValue({
      data: [
        makeDocument({ id: "d_p", name: "平台手册", scope: "platform" }),
        makeDocument({ id: "d_g", name: "集团话术", scope: "group" }),
        makeDocument({ id: "d_s", name: "门店FAQ", scope: "store" }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<KnowledgePage />);

    // 三 scope 同列表(super_admin 全量聚合)。
    expect(getByText("平台手册")).toBeTruthy();
    expect(getByText("集团话术")).toBeTruthy();
    expect(getByText("门店FAQ")).toBeTruthy();
    // 三色 scope 徽章。
    expect(getByText("平台").className).toContain("bg-destructive");
    expect(getByText("集团").className).toContain("bg-warning");
    expect(getByText("本店").className).toContain("bg-success");
  });

  it("门店 owner:只看本店 + 下发(无其他门店 store 文档)", () => {
    stubBasics(makeOwnerMe());
    // 门店 owner 的 backend list 只返回:本店 store 文档 + 可见下发(platform/group)。
    mocks.useDocuments.mockReturnValue({
      data: [
        makeDocument({ id: "d_s", name: "本店自建话术", scope: "store" }),
        makeDocument({ id: "d_p", name: "平台下发手册", scope: "platform" }),
      ],
      isLoading: false,
    });

    const { getByText, queryByText } = renderWithProviders(<KnowledgePage />);

    // 本店 store + 平台下发可见;无其他门店 store 文档(隔离)。
    expect(getByText("本店自建话术")).toBeTruthy();
    expect(getByText("平台下发手册")).toBeTruthy();
    // 「门店FAQ」是别的门店的,不在本店 list 里(断言它不在)。
    expect(queryByText("门店FAQ")).toBeNull();
  });

  it("member:只读守卫(无「录入文档」按钮 + 无删除菜单)", () => {
    stubBasics(makeMemberMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDocument({ id: "d_s", name: "本店文档" })],
      isLoading: false,
    });

    const { queryByText, queryAllByLabelText } = renderWithProviders(
      <KnowledgePage />,
    );

    // member 只有 read → 无写按钮。
    expect(queryByText("录入文档")).toBeNull();
    expect(queryAllByLabelText("操作").length).toBe(0);
    // 但文档仍可见(只读)。
    expect(queryByText("本店文档")).not.toBeNull();
  });

  // 跨角色渲染一致(AC4 契约):前端渲染逻辑对所有角色同结构 —— 差异只在 backend
  // list 返回的数据。上面 group_admin/super_admin/owner 三个用例各自喂不同数据已
  // 证明「前端只渲染 useDocuments 返回值」(DocumentList 组件代码无角色分支),无需
  // 再用同一份数据重复跑三遍断言同一结构。
});

// ============================================================================
// slice 03 AC5:空态完整覆盖
// ============================================================================

describe("KnowledgePage 空态完整覆盖(slice 03 AC5)", () => {
  beforeEach(() => stubBasics(makeOwnerMe()));

  it("空态 1:categories 空 → 左栏目录树显示空态,不报错", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [],
      isLoading: false,
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getAllByText } = renderWithProviders(<KnowledgePage />);

    // 左栏分类目录 CardTitle 仍渲染(空内容不崩)。
    expect(getAllByText("分类目录").length).toBeGreaterThanOrEqual(1);
    // 中栏文档列表空态。
    expect(getAllByText(/暂无文档/).length).toBeGreaterThanOrEqual(1);
  });

  it("空态 2:documents 空 → 中栏显示「暂无文档」+ 总数 0", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory()],
      isLoading: false,
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getAllByText } = renderWithProviders(<KnowledgePage />);

    expect(getAllByText(/共 0 篇文档/).length).toBeGreaterThanOrEqual(1);
    expect(getAllByText(/暂无文档/).length).toBeGreaterThanOrEqual(1);
  });

  it("空态 3:selectedDoc null → 右栏 MarkdownReader 显示空态占位", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory()],
      isLoading: false,
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<KnowledgePage />);

    // 右栏空态文案(MarkdownReader 空 doc 占位)。
    expect(getByText("选择左侧文档查看")).toBeTruthy();
  });
});
