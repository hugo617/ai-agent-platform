// DocumentList 组件测试(reader-ui slice 01 + slice 03)。
//
// 模式沿用 devices/__tests__/store-view.test.tsx(已落地的 vitest 基建):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(useDocuments / mutation
//     hooks / useToast 需要)。
//   - ``vi.mock("@/hooks/queries")`` stub useDocuments + useCreateDocument +
//     useDeleteDocument —— 不走真实 axios/网络,断言「组件正确消费了 hook 返回的数据」
//     (后端契约由 msw 集成测试 + pytest 覆盖,组件测试只测渲染 + 交互层)。
//   - ``vi.mock("@/components/auth/auth-context")`` 注入不同 me 变体(owner /
//     member),驱动按钮的 ``canCreate``/``canDelete`` 守卫(真实 hasPermission 逻辑,
//     靠 me.permissions 数组驱动,与 devices store-view 测试一致)。
//   - user-event@14 模拟点击。DropdownMenu 项在 Radix 中是异步 portal 挂载,点开后
//     再 await findByText 拿菜单项。
//
// 覆盖:
//   - slice 01:列表渲染(标题/scope 徽章/状态徽章/时间/chunk 数)+ 空态 + filter
//     透传 + 选中态。
//   - slice 03 AC3:CRUD 守卫(member 只读无写按钮 / owner 有录入+删除)+ 录入 Dialog
//     弹出 + 填表提交触发 useCreateDocument.mutateAsync + 删除菜单触发
//     useDeleteDocument.mutateAsync。
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
import { DocumentList } from "../document-list";
import type { DocumentRead, KnowledgeCategoryRead, MeResponse } from "@/api/types";

// ---- mock wiring ----
// ``vi.mock`` 工厂在 hoist 作用域执行,引用的变量必须用 ``vi.hoisted`` 提前。
const mocks = vi.hoisted(() => ({
  useDocuments: vi.fn() as Mock,
  useCreateDocument: vi.fn() as Mock,
  useDeleteDocument: vi.fn() as Mock,
  useKnowledgeCategories: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useDocuments: mocks.useDocuments,
  useCreateDocument: mocks.useCreateDocument,
  useDeleteDocument: mocks.useDeleteDocument,
  useKnowledgeCategories: mocks.useKnowledgeCategories,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
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

// owner me:含 create + delete 权限。member me:只有 read(无写)。
// 真实 hasPermission:super_admin 直接 true;否则查 me.permissions 数组成员。
function makeOwnerMe(): MeResponse {
  return {
    user_id: "u_owner",
    tenant_id: "tn_1",
    email: "owner@example.com",
    platform_role: null,
    roles: ["owner"],
    permissions: [
      "knowledge:read",
      "knowledge:create",
      "knowledge:delete",
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
    permissions: ["knowledge:read"],
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
// useKnowledgeCategories 默认返回空数组(slice 05:reader 录入 Dialog 的 category 下拉
// 数据源;现有 slice 01/03 测试不关心 category,空数组 → 下拉不渲染,零回归)。
function stubBasics(me: MeResponse) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });
  mocks.useCreateDocument.mockReturnValue(makeMut());
  mocks.useDeleteDocument.mockReturnValue(makeMut());
  mocks.useKnowledgeCategories.mockReturnValue({ data: [] });
}

afterEach(() => vi.clearAllMocks());

// ============================================================================
// slice 01:卡片渲染 + scope/状态徽章 + 空态 + filter 透传 + 选中态
// (与旧 slice 01 测试等价,改用真实 hasPermission + me 注入范式)
// ============================================================================

describe("DocumentList — 卡片渲染 + scope/状态徽章 + 空态(slice 01)", () => {
  beforeEach(() => stubBasics(makeOwnerMe()));

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
    // 渲染了一张卡片(内层点击 button 元素)。
    const clickButtons = container.querySelectorAll(
      "button[type='button']:not([aria-label='操作'])",
    );
    expect(clickButtons.length).toBe(1);
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

  it("空态:无文档时渲染「暂无文档」+ 总数 0(owner 附「点击录入文档添加」提示)", () => {
    mocks.useDocuments.mockReturnValue({
      data: [],
      isLoading: false,
    });

    const { getByText } = renderWithProviders(<DocumentList />);

    expect(getByText(/共 0 篇文档/)).toBeTruthy();
    // owner 有 create 权限 → 空态文案带引导(与旧 legacy-page 一致,零回归)。
    expect(getByText(/暂无文档/)).toBeTruthy();
    expect(getByText(/点击「录入文档」添加/)).toBeTruthy();
  });

  it("空态 member:无文档时只显示「暂无文档」(无录入引导,member 只读)", () => {
    stubBasics(makeMemberMe());
    mocks.useDocuments.mockReturnValue({
      data: [],
      isLoading: false,
    });

    const { getByText, queryByText } = renderWithProviders(<DocumentList />);

    expect(getByText(/共 0 篇文档/)).toBeTruthy();
    expect(getByText("暂无文档")).toBeTruthy();
    // member 无 create → 不显示录入引导。
    expect(queryByText(/点击「录入文档」添加/)).toBeNull();
  });

  it("filter 透传:scope/categoryId props 透传给 useDocuments(query 参数管线基础)", () => {
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    renderWithProviders(<DocumentList scope="group" categoryId="cat_1" />);

    // 核心断言:useDocuments 被以 {scope, category_id} filter 调用。这是切片 02
    // CategoryTree 点击 → DocumentList 过滤的管线基础(本片只验证透传正确)。
    expect(mocks.useDocuments).toHaveBeenCalledWith({
      scope: "group",
      category_id: "cat_1",
    });
  });

  it("点击卡片触发 onSelectDoc 回调(选中态下传,切片 02 MarkdownReader 联动基础)", async () => {
    const user = userEvent.setup();
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

// ============================================================================
// slice 03 AC3:CRUD Dialog + member 只读守卫
// ============================================================================

describe("DocumentList — CRUD Dialog + member 只读守卫(slice 03)", () => {
  it("owner 角色:渲染「录入文档」按钮 + 文档卡片的删除 DropdownMenu", () => {
    stubBasics(makeOwnerMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDocument({ id: "doc_1", name: "颈椎理疗话术" })],
      isLoading: false,
    });

    const { getByText, getAllByLabelText } = renderWithProviders(
      <DocumentList />,
    );

    // owner 有 create 权限 → 「录入文档」按钮可见。
    expect(getByText("录入文档")).toBeTruthy();
    // owner 有 delete 权限 → 每张卡片有「操作」DropdownMenu 触发器。
    expect(getAllByLabelText("操作").length).toBe(1);
  });

  it("member 角色:无「录入文档」按钮 + 无删除 DropdownMenu(只读守卫)", () => {
    stubBasics(makeMemberMe());
    mocks.useDocuments.mockReturnValue({
      data: [makeDocument({ id: "doc_1", name: "颈椎理疗话术" })],
      isLoading: false,
    });

    const { queryByText, queryAllByLabelText } = renderWithProviders(
      <DocumentList />,
    );

    // member 只有 read → 「录入文档」按钮隐藏。
    expect(queryByText("录入文档")).toBeNull();
    // member 无 delete → 「操作」DropdownMenu 触发器隐藏(纯只读列表)。
    expect(queryAllByLabelText("操作").length).toBe(0);
  });

  it("录入流程:点「录入文档」弹 Dialog → 填表 → 提交触发 useCreateDocument.mutateAsync", async () => {
    const user = userEvent.setup();
    const createMut = makeMut();
    stubBasics(makeOwnerMe());
    mocks.useCreateDocument.mockReturnValue(createMut);
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText, getByPlaceholderText, queryByText } =
      renderWithProviders(<DocumentList />);

    // 1. 点「录入文档」→ Dialog 弹出(标题「录入知识文档」可见)。
    await user.click(getByText("录入文档"));
    expect(getByText("录入知识文档")).toBeTruthy();

    // 2. 填文档名称 + 内容(手动录入模式,默认选中)。
    await user.type(
      getByPlaceholderText("如 颈椎理疗服务话术"),
      "颈椎理疗话术",
    );
    await user.type(
      getByPlaceholderText(
        "粘贴或输入知识库文本(产品说明、FAQ、话术等)...",
      ),
      "欢迎光临,请这边坐。",
    );

    // 3. 点「创建并索引」→ 触发 mutateAsync(name/content/source_type)。
    await user.click(getByText("创建并索引"));

    expect(createMut.mutateAsync).toHaveBeenCalledWith({
      name: "颈椎理疗话术",
      content: "欢迎光临,请这边坐。",
      source_type: "text",
    });
    // 成功后 Dialog 关闭(标题消失)。
    expect(queryByText("录入知识文档")).toBeNull();
  });

  it("录入校验:未填名称时 toast 报错,不触发 mutateAsync", async () => {
    const user = userEvent.setup();
    const createMut = makeMut();
    stubBasics(makeOwnerMe());
    mocks.useCreateDocument.mockReturnValue(createMut);
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<DocumentList />);

    await user.click(getByText("录入文档"));
    // 不填任何字段,直接点创建。
    await user.click(getByText("创建并索引"));

    // 校验失败:不触发 mutateAsync。
    expect(createMut.mutateAsync).not.toHaveBeenCalled();
    // toast 错误文案可见(useToast 渲染在 ToastProvider 内)。
    expect(getByText("请填写文档名称")).toBeTruthy();
  });

  it("删除流程:点卡片「操作」菜单 → 删除项 → 确认 Dialog → 触发 useDeleteDocument.mutateAsync", async () => {
    const user = userEvent.setup();
    const deleteMut = makeMut();
    stubBasics(makeOwnerMe());
    mocks.useDeleteDocument.mockReturnValue(deleteMut);
    mocks.useDocuments.mockReturnValue({
      data: [makeDocument({ id: "doc_1", name: "颈椎理疗话术" })],
      isLoading: false,
    });

    const { getByLabelText, getByText, findByText } = renderWithProviders(
      <DocumentList />,
    );

    // 1. 点卡片的「操作」DropdownMenu 触发器。
    await user.click(getByLabelText("操作"));
    // 2. 菜单弹出(异步 portal),await 拿「删除」菜单项。
    const deleteItem = await findByText("删除");
    await user.click(deleteItem);

    // 3. 确认 Dialog 弹出(标题「确认删除」)。
    expect(getByText("确认删除")).toBeTruthy();

    // 4. 点 Dialog 内的「删除」按钮(destructive)→ 触发 mutateAsync(doc id)。
    //    Dialog 里有「取消」+「删除」两个按钮;destructive variant 的是确认键。
    const confirmBtn = getByText("删除", {
      selector: "button",
    });
    await user.click(confirmBtn);

    expect(deleteMut.mutateAsync).toHaveBeenCalledWith("doc_1");
  });
});

// ============================================================================
// slice 05 AC2:reader 录入 Dialog 加 category 下拉(B4 零行为回归)
//   - 数据源 useKnowledgeCategories(后端按本店可见返回 platform + 本集团 group +
//     本店 store 三层)。
//   - 可选不选(默认 __none__ → 提交不透传 category_id,等价现有行为)。
//   - scope 固定 store(reader 录入不选 scope),提交 payload 无 scope 字段。
// ============================================================================

// category factory:默认 store scope,每用例 override。
function makeCategory(
  overrides: Partial<KnowledgeCategoryRead> = {},
): KnowledgeCategoryRead {
  return {
    id: "cat_store_1",
    name: "门店FAQ",
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

describe("DocumentList — reader 录入 Dialog category 下拉(slice 05 B4)", () => {
  it("录入 Dialog 弹出后渲染 category 下拉,含后端返回的本店可见分类(三层)", async () => {
    const user = userEvent.setup();
    stubBasics(makeOwnerMe());
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [
        makeCategory({ id: "cat_p", name: "平台手册", scope: "platform" }),
        makeCategory({ id: "cat_g", name: "集团话术", scope: "group" }),
        makeCategory({ id: "cat_s", name: "门店FAQ", scope: "store" }),
      ],
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText } = renderWithProviders(<DocumentList />);

    await user.click(getByText("录入文档"));
    // Dialog 弹出 + category 字段标签可见(下拉数据源为本店可见的全部分类)。
    expect(getByText("分类(可选)")).toBeTruthy();

    // 打开 category Select,三层分类都出现在选项里(后端已按角色过滤)。
    const trigger = document.querySelector(
      '[role="combobox"]',
    ) as HTMLElement;
    await user.click(trigger);
    const options = Array.from(
      document.querySelectorAll('[role="option"]'),
    ).map((o) => o.textContent ?? "");
    expect(options).toContain("平台手册");
    expect(options).toContain("集团话术");
    expect(options).toContain("门店FAQ");
    // 默认「不归类」选项存在(可选不选的语义入口)。
    expect(options).toContain("不归类");
  });

  it("选中 category 提交:useCreateDocument 收到 category_id(scope 固定 store 不在 payload)", async () => {
    const user = userEvent.setup();
    const createMut = makeMut();
    stubBasics(makeOwnerMe());
    mocks.useCreateDocument.mockReturnValue(createMut);
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory({ id: "cat_store_1", name: "门店FAQ" })],
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText, getByPlaceholderText } =
      renderWithProviders(<DocumentList />);

    await user.click(getByText("录入文档"));

    await user.type(
      getByPlaceholderText("如 颈椎理疗服务话术"),
      "颈椎理疗话术",
    );
    await user.type(
      getByPlaceholderText(
        "粘贴或输入知识库文本(产品说明、FAQ、话术等)...",
      ),
      "欢迎光临。",
    );

    // 选 category:打开 Select → 点「门店FAQ」option。
    const trigger = document.querySelector(
      '[role="combobox"]',
    ) as HTMLElement;
    await user.click(trigger);
    const option = Array.from(document.querySelectorAll('[role="option"]')).find(
      (o) => o.textContent === "门店FAQ",
    ) as HTMLElement;
    await user.click(option);

    await user.click(getByText("创建并索引"));

    // payload 含 category_id(reader scope 固定 store,不下拉,故无 scope 字段)。
    expect(createMut.mutateAsync).toHaveBeenCalledWith({
      name: "颈椎理疗话术",
      content: "欢迎光临。",
      source_type: "text",
      category_id: "cat_store_1",
    });
  });

  it("不选 category(默认「不归类」)提交:payload 无 category_id(零行为回归)", async () => {
    const user = userEvent.setup();
    const createMut = makeMut();
    stubBasics(makeOwnerMe());
    mocks.useCreateDocument.mockReturnValue(createMut);
    // 有分类可选,但用户不动 category 下拉(保持默认不归类)。
    mocks.useKnowledgeCategories.mockReturnValue({
      data: [makeCategory({ id: "cat_store_1", name: "门店FAQ" })],
    });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText, getByPlaceholderText } =
      renderWithProviders(<DocumentList />);

    await user.click(getByText("录入文档"));
    await user.type(
      getByPlaceholderText("如 颈椎理疗服务话术"),
      "颈椎理疗话术",
    );
    await user.type(
      getByPlaceholderText(
        "粘贴或输入知识库文本(产品说明、FAQ、话术等)...",
      ),
      "欢迎光临。",
    );
    // 不碰 category Select,直接提交。
    await user.click(getByText("创建并索引"));

    // payload 与现有 slice 03 行为完全一致(无 category_id)。
    expect(createMut.mutateAsync).toHaveBeenCalledWith({
      name: "颈椎理疗话术",
      content: "欢迎光临。",
      source_type: "text",
    });
  });

  it("无可见分类时(useKnowledgeCategories 返回空):不渲染 category 下拉,提交零回归", async () => {
    const user = userEvent.setup();
    const createMut = makeMut();
    stubBasics(makeOwnerMe());
    mocks.useCreateDocument.mockReturnValue(createMut);
    // 无分类 → 下拉不渲染。
    mocks.useKnowledgeCategories.mockReturnValue({ data: [] });
    mocks.useDocuments.mockReturnValue({ data: [], isLoading: false });

    const { getByText, getByPlaceholderText, queryByText } =
      renderWithProviders(<DocumentList />);

    await user.click(getByText("录入文档"));
    // 无分类 → 不渲染 category 字段(空态降级,不阻挡录入)。
    expect(queryByText("分类(可选)")).toBeNull();

    await user.type(
      getByPlaceholderText("如 颈椎理疗服务话术"),
      "颈椎理疗话术",
    );
    await user.type(
      getByPlaceholderText(
        "粘贴或输入知识库文本(产品说明、FAQ、话术等)...",
      ),
      "欢迎光临。",
    );
    await user.click(getByText("创建并索引"));

    expect(createMut.mutateAsync).toHaveBeenCalledWith({
      name: "颈椎理疗话术",
      content: "欢迎光临。",
      source_type: "text",
    });
  });
});
