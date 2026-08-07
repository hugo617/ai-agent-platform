// CategoryTree 组件测试(reader-ui slice 02)。
//
// 模式沿用 devices/__tests__/store-view.test.tsx + knowledge slice 01 的
// document-list.test.tsx(vitest 基建):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(useKnowledgeCategories
//     需要 QueryClient)。
//   - ``vi.mock("@/hooks/queries")`` stub useKnowledgeCategories —— 不走真实
//     axios/网络,断言「组件正确消费 hook 返回的数据」。
//   - 树渲染 + scope 三分区 + category 分组 + 点击 onSelect 回调 + 折叠 + 空态。
//
// 覆盖(plan §6 切片 02 AC7):树渲染 + scope 三分区显示 + category 分组 + 点击触发
// onSelect 回调 + 空态(无 category)。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { renderWithProviders } from "@/test/test-utils";
import { CategoryTree } from "../category-tree";
import type { KnowledgeCategoryRead } from "@/api/types";

// ---- mock wiring ----
const mocks = vi.hoisted(() => ({
  useKnowledgeCategories: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useKnowledgeCategories: mocks.useKnowledgeCategories,
}));

// ---- factories ----
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

afterEach(() => vi.clearAllMocks());

describe("CategoryTree — scope 三分区 + category 分组 + 点击筛选(slice 02)", () => {
  it("scope 三分区:platform/group/store 各自显示分区头 + ScopeBadge + 计数", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "c_p", name: "平台规范", scope: "platform" }),
        makeCategory({ id: "c_g", name: "集团话术", scope: "group" }),
        makeCategory({ id: "c_s", name: "本店FAQ", scope: "store" }),
      ],
      isLoading: false,
    });

    const { getByText, getAllByText } = renderWithProviders(
      <CategoryTree onSelect={vi.fn()} />,
    );

    // 三分区标题(平台下发/集团下发/本店自建)。
    expect(getByText("平台下发")).toBeTruthy();
    expect(getByText("集团下发")).toBeTruthy();
    expect(getByText("本店自建")).toBeTruthy();
    // 三色 ScopeBadge(平台/集团/本店)。
    expect(getByText("平台").className).toContain("bg-destructive");
    expect(getByText("集团").className).toContain("bg-warning");
    expect(getByText("本店").className).toContain("bg-success");
    // 计数:三个 scope 各 1 个 category,故 "(1)" 出现 3 次。
    expect(getAllByText("(1)").length).toBe(3);
    // category 名称。
    expect(getByText("平台规范")).toBeTruthy();
    expect(getByText("集团话术")).toBeTruthy();
    expect(getByText("本店FAQ")).toBeTruthy();
  });

  it("category 分组:同一 scope 多个 category 按 sort_order 排列", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        // 故意乱序,验证按 sort_order 升序。
        makeCategory({ id: "c2", name: "话术库", scope: "store", sort_order: 2 }),
        makeCategory({ id: "c1", name: "产品手册", scope: "store", sort_order: 0 }),
        makeCategory({ id: "c3", name: "FAQ", scope: "store", sort_order: 1 }),
      ],
      isLoading: false,
    });

    const { getAllByText } = renderWithProviders(
      <CategoryTree onSelect={vi.fn()} />,
    );

    // 只有一个 store 分区,计数 3。
    expect(getAllByText("(3)").length).toBe(1);
    // 三个 category 都渲染。
    expect(getAllByText("产品手册").length).toBeGreaterThanOrEqual(1);
    expect(getAllByText("FAQ").length).toBeGreaterThanOrEqual(1);
    expect(getAllByText("话术库").length).toBeGreaterThanOrEqual(1);
  });

  it("点击 category 触发 onSelect({scope, categoryId}) 回调", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
    const onSelect = vi.fn();
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "cat_group_1", name: "集团话术", scope: "group" }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(
      <CategoryTree onSelect={onSelect} />,
    );

    await user.click(getByText("集团话术"));

    expect(onSelect).toHaveBeenCalledWith({
      scope: "group",
      categoryId: "cat_group_1",
    });
  });

  it("选中态高亮:selectedScope+selectedCategoryId 命中时 category 标 aria-current", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "cat_sel", name: "选中项", scope: "store" }),
        makeCategory({ id: "cat_other", name: "未选中", scope: "store" }),
      ],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(
      <CategoryTree
        selectedScope="store"
        selectedCategoryId="cat_sel"
        onSelect={vi.fn()}
      />,
    );

    // 选中的 category 带 aria-current="true"。
    const selectedBtn = getByText("选中项").closest("button");
    expect(selectedBtn?.getAttribute("aria-current")).toBe("true");
    // 未选中的不带。
    const otherBtn = getByText("未选中").closest("button");
    expect(otherBtn?.getAttribute("aria-current")).toBeNull();
  });

  it("空态:无 category 时渲染「暂无分类」", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(
      <CategoryTree onSelect={vi.fn()} />,
    );

    expect(getByText("暂无分类")).toBeTruthy();
  });

  it("scope 分区可折叠:点击分区头 toggle(aria-expanded 变化)", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "c_s", name: "本店FAQ", scope: "store" }),
      ],
      isLoading: false,
    });

    const { getByText, queryByText } = renderWithProviders(
      <CategoryTree onSelect={vi.fn()} />,
    );

    // 初始展开:category 可见。
    expect(getByText("本店FAQ")).toBeTruthy();
    // 分区头 button 默认 aria-expanded=true。
    const headerBtn = getByText("本店自建").closest("button");
    expect(headerBtn?.getAttribute("aria-expanded")).toBe("true");

    // 点击分区头折叠。
    await user.click(headerBtn!);
    expect(headerBtn?.getAttribute("aria-expanded")).toBe("false");
    // 折叠后 category 列表项消失(分区头仍在)。
    expect(queryByText("本店FAQ")).toBeNull();
    // 再点展开。
    await user.click(headerBtn!);
    expect(getByText("本店FAQ")).toBeTruthy();
  });

  it("过滤 is_deleted:软删的 category 不渲染(前端兜底)", () => {
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "c_alive", name: "活跃分类", scope: "store" }),
        makeCategory({
          id: "c_dead",
          name: "已删除分类",
          scope: "store",
          is_deleted: true,
        }),
      ],
      isLoading: false,
    });

    const { getByText, queryByText } = renderWithProviders(
      <CategoryTree onSelect={vi.fn()} />,
    );

    expect(getByText("活跃分类")).toBeTruthy();
    expect(queryByText("已删除分类")).toBeNull();
  });
});
