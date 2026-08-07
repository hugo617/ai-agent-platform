// KnowledgePage 三栏编排 smoke 测试(reader-ui slice 02)。
//
// 验证 plan §6 切片 02 AC9:三栏 smoke(三栏均渲染)+ CategoryTree 点击 →
// DocumentList 过滤(选中态 scope/categoryId 下传)+ DocumentList 点击 →
// MarkdownReader 显示(选中 doc 下传)。
//
// mock 策略:stub ``useKnowledgeCategories`` + ``useDocuments``(两个子组件自调的
// hook),让三栏各自拿到数据。注意 index.tsx 还渲染 <LegacyKnowledgePage/>(切片 02
// 过渡保留),它也调 useDocuments + useCreateDocument + useDeleteDocument —— 一并 stub
// 避免报 hook 未定义。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { renderWithProviders } from "@/test/test-utils";
import { KnowledgePage } from "../index";
import type {
  DocumentRead,
  KnowledgeCategoryRead,
} from "@/api/types";

// ---- mock wiring ----
// index.tsx 渲染的子组件调用的所有 hook 都要 stub:CategoryTree 调
// useKnowledgeCategories;DocumentList 调 useDocuments;LegacyKnowledgePage 调
// useDocuments + useCreateDocument + useDeleteDocument。
const mocks = vi.hoisted(() => ({
  useKnowledgeCategories: vi.fn() as Mock,
  useDocuments: vi.fn() as Mock,
  useCreateDocument: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })) as Mock,
  useDeleteDocument: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })) as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useKnowledgeCategories: mocks.useKnowledgeCategories,
  useDocuments: mocks.useDocuments,
  useCreateDocument: mocks.useCreateDocument,
  useDeleteDocument: mocks.useDeleteDocument,
}));

// LegacyKnowledgePage(切片 02 过渡期保留)调 useAuth + hasPermission 控制 CRUD
// 按钮显隐。index.test 渲染整个 KnowledgePage(含 Legacy),故注入 owner 角色 +
// hasPermission=true(本测试关注三栏联动,不测权限差异 —— 权限归切片 03 跨角色测试)。
vi.mock("@/components/auth/auth-context", () => ({
  useAuth: () => ({
    me: {
      id: "u_1",
      tenant_id: "tn_1",
      roles: [{ role: "owner" }],
    },
  }),
}));
vi.mock("@/lib/permission", () => ({
  hasPermission: () => true,
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

afterEach(() => vi.clearAllMocks());

describe("KnowledgePage 三栏编排 smoke + 联动(slice 02)", () => {
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
    const user = (await import("@testing-library/user-event")).default.setup();
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
    // (LegacyKnowledgePage 也调 useDocuments 但无 filter —— 两者调用并存,断言
    //  至少一次带 filter 的调用。)
    const callsWithFilter = mocks.useDocuments.mock.calls.filter(
      ([arg]) => arg && typeof arg === "object" && "scope" in arg,
    );
    expect(callsWithFilter.length).toBeGreaterThan(0);
    expect(callsWithFilter.some(
      (c) => c[0]?.scope === "group" && c[0]?.category_id === "cat_g1",
    )).toBe(true);
  });

  it("联动 2:DocumentList 点击文档 → MarkdownReader 显示文档内容", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
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

    const { getAllByText, queryByText } = renderWithProviders(
      <KnowledgePage />,
    );

    // 初始:右栏空态「选择左侧文档查看」(MarkdownReader 空 doc 占位)。
    expect(queryByText("选择左侧文档查看")).not.toBeNull();

    // 点击中栏文档卡片。中栏 DocumentList 卡片是 <button>,LegacyKnowledgePage
    // 的旧 Table 是 <td> —— 两者都含文档名,故用 getAllByText 取第一个(DOM 顺序:
    // 三栏 grid 在前,Legacy 在后,故 [0] 是中栏卡片)。
    const matches = getAllByText("被选中的文档");
    await user.click(matches[0]);

    // 联动后:空态消失(右栏已选中)。
    expect(queryByText("选择左侧文档查看")).toBeNull();
    // Markdown 渲染:右栏正文 h2 标题(只在 MarkdownReader 渲染,Legacy 不渲染 Markdown)。
    // h2 带 id=toc-0(目录大纲锚点),证明 MarkdownReader 接到了 selectedDoc。
    const h2 = document.getElementById("toc-0");
    expect(h2).not.toBeNull();
    expect(h2?.textContent).toContain("这篇文档的独有标题");
  });
});
