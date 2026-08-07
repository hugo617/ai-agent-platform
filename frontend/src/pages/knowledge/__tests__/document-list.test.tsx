// DocumentList 组件测试(reader-ui slice 01)。
//
// 模式沿用 devices/__tests__/store-view.test.tsx(已落地的 vitest 基建):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(useDocuments 需要)。
//   - ``vi.mock("@/hooks/queries")`` stub useDocuments —— 不走真实 axios/网络,
//     断言的是「组件正确消费了 hook 返回的数据」(后端契约由 msw 集成测试 +
//     pytest 覆盖,组件测试只测渲染层)。
//   - 卡片渲染 + scope 徽章三色 + 状态徽章 + 时间/chunk 数 + 空态。
//
// 覆盖(plan §6 切片 01 AC9):列表渲染(卡片显示标题/scope 徽章/状态徽章/时间/
// chunk 数)+ 空态 + mock useDocuments 范式。CRUD 守卫测试归切片 03(本片 DocumentList
// 是纯只读卡片视图,无写操作)。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { renderWithProviders } from "@/test/test-utils";
import { DocumentList } from "../document-list";
import type { DocumentRead } from "@/api/types";

// ---- mock wiring ----
// ``vi.mock`` 工厂在 hoist 作用域执行,引用的变量必须用 ``vi.hoisted`` 提前。
const mocks = vi.hoisted(() => ({
  useDocuments: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useDocuments: mocks.useDocuments,
}));

// ---- factories ----
// DocumentRead 现在含 scope/group_id/category_id(reader-ui slice 01 G6)。factory
// 默认 store scope + null group/category,每个用例按需 override。
function makeDocument(overrides: Partial<DocumentRead> = {}): DocumentRead {
  return {
    id: "doc_1",
    tenant_id: "tn_1",
    name: "颈椎理疗话术",
    source_type: "text",
    content: "## 开场\n欢迎光临...",
    chunk_count: 3,
    status: "indexed",
    scope: "store",
    group_id: null,
    category_id: null,
    created_at: "2026-08-07T09:00:00Z",
    updated_at: "2026-08-07T09:00:00Z",
    ...overrides,
  };
}

afterEach(() => vi.clearAllMocks());

describe("DocumentList — 卡片渲染 + scope/状态徽章 + 空态(slice 01)", () => {
  it("卡片渲染:标题 + scope 徽章(store→success 实心)+ 状态徽章(indexed→绿点)+ chunk 数 + 时间", () => {
    mocks.useDocuments.mockReturnValue({
      data: [
        makeDocument({
          id: "doc_1",
          name: "颈椎理疗话术",
          scope: "store",
          status: "indexed",
          chunk_count: 3,
          updated_at: "2026-08-07T09:00:00Z",
        }),
      ],
      isLoading: false,
    });

    const { getByText, container } = renderWithProviders(<DocumentList />);

    // 标题。
    expect(getByText("颈椎理疗话术")).toBeTruthy();
    // scope 徽章(store → success 实心)。
    const storeBadge = getByText("本店");
    expect(storeBadge.className).toContain("bg-success");
    // 状态徽章(indexed → dot-success 绿点)。
    expect(getByText("已索引")).toBeTruthy();
    // chunk 数 + 时间(formatDateTime 渲染)。
    expect(getByText(/3 块/)).toBeTruthy();
    // scope 徽章是实心 variant(非 dot),与状态徽章分层。
    expect(storeBadge.className).not.toContain("bg-muted");
    // 卡片总数描述。
    expect(getByText(/共 1 篇文档/)).toBeTruthy();
    // 渲染了一张卡片(button 元素)。
    const cards = container.querySelectorAll("button[type='button']");
    expect(cards.length).toBe(1);
  });

  it("scope 三色映射:platform→destructive / group→warning / store→success 同列表正确渲染", () => {
    mocks.useDocuments.mockReturnValue({
      data: [
        makeDocument({ id: "d_p", name: "平台手册", scope: "platform" }),
        makeDocument({ id: "d_g", name: "集团话术", scope: "group" }),
        makeDocument({ id: "d_s", name: "本店FAQ", scope: "store" }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<DocumentList />);

    // 三色 scope 徽章同时出现(platform=平台/destructive, group=集团/warning,
    // store=本店/success)。
    expect(getByText("平台").className).toContain("bg-destructive");
    expect(getByText("集团").className).toContain("bg-warning");
    expect(getByText("本店").className).toContain("bg-success");
    expect(getByText(/共 3 篇文档/)).toBeTruthy();
  });

  it("状态徽章三态:indexed→已索引(dot-success)/ pending→待处理(dot-warning)/ failed→索引失败(dot-destructive)", () => {
    mocks.useDocuments.mockReturnValue({
      data: [
        makeDocument({ id: "d1", name: "doc1", status: "indexed" }),
        makeDocument({ id: "d2", name: "doc2", status: "pending" }),
        makeDocument({ id: "d3", name: "doc3", status: "failed" }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<DocumentList />);

    // 三态状态徽章(dot variant,与 scope 实心徽章分层)。
    expect(getByText("已索引")).toBeTruthy();
    expect(getByText("待处理")).toBeTruthy();
    expect(getByText("索引失败")).toBeTruthy();
  });

  it("空态:无文档时渲染「暂无文档」+ 总数 0", () => {
    mocks.useDocuments.mockReturnValue({
      data: [],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<DocumentList />);

    expect(getByText(/共 0 篇文档/)).toBeTruthy();
    expect(getByText("暂无文档")).toBeTruthy();
  });

  it("filter 透传:scope/categoryId props 透传给 useDocuments(query 参数管线基础)", () => {
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    renderWithProviders(
      <DocumentList scope="group" categoryId="cat_1" />,
    );

    // 核心断言:useDocuments 被以 {scope, category_id} filter 调用。这是切片 02
    // CategoryTree 点击 → DocumentList 过滤的管线基础(本片只验证透传正确)。
    expect(mocks.useDocuments).toHaveBeenCalledWith({
      scope: "group",
      category_id: "cat_1",
    });
  });

  it("点击卡片触发 onSelectDoc 回调(选中态下传,切片 02 MarkdownReader 联动基础)", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
    const onSelectDoc = vi.fn();
    const doc = makeDocument({ id: "doc_1", name: "颈椎理疗话术" });
    mocks.useDocuments.mockReturnValue({ data: [doc], isLoading: false });

    const { getByText } = renderWithProviders(
      <DocumentList onSelectDoc={onSelectDoc} />,
    );

    await user.click(getByText("颈椎理疗话术"));

    expect(onSelectDoc).toHaveBeenCalledWith(doc);
  });
});
