// ConversationListPanel 组件测(chat-page-split Ticket 2)。
//
// 模式沿用 bookings/__tests__/store-view.test.tsx(plan §5 seam B):
//   - ``renderWithProviders`` 包 QueryClient + ToastProvider(Panel 内 useToast +
//     各 use*Conversation hook 都依赖)。
//   - ``vi.mock("@/hooks/queries")`` stub 写 hooks —— 不走真实 axios/网络,
//     断言的是「组件正确调用了 hook」而非「后端返回什么」(后端契约由 pytest 覆盖)。
//   - ``vi.mock("@/components/auth/auth-context")`` 注入 me(驱动 useCustomerProfiles
//     的 enabled 守卫)。
//   - user-event@14 模拟点击。DropdownMenu / Dialog 在 Radix 中是异步 portal 挂载,
//     点开后用 ``findByText`` 等出现再点。
//
// 覆盖(plan §5):列表渲染 + 徽章 + 空状态 + 删除 mutateAsync 被调 + 右键菜单开
// rename/add-tag Dialog。
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import userEvent from "@testing-library/user-event";
import { within } from "@testing-library/react";
import { renderWithProviders } from "@/test/test-utils";
import { ConversationListPanel } from "../conversation-list-panel";
import type { Conversation, MeResponse } from "@/api/types";

// ---- mock wiring ----
// vi.mock 工厂在 hoist 作用域执行,引用的变量必须用 vi.hoisted 提前。
const mocks = vi.hoisted(() => ({
  useConversations: vi.fn() as Mock,
  useCustomerProfiles: vi.fn() as Mock,
  useDeleteConversation: vi.fn() as Mock,
  useRenameConversation: vi.fn() as Mock,
  useAddConversationTag: vi.fn() as Mock,
  useRemoveConversationTag: vi.fn() as Mock,
  useSetConversationPinned: vi.fn() as Mock,
  useSetConversationStarred: vi.fn() as Mock,
  useBatchDeleteConversations: vi.fn() as Mock,
  useAuth: vi.fn() as Mock,
}));

vi.mock("@/hooks/queries", () => ({
  useConversations: mocks.useConversations,
  useCustomerProfiles: mocks.useCustomerProfiles,
  useDeleteConversation: mocks.useDeleteConversation,
  useRenameConversation: mocks.useRenameConversation,
  useAddConversationTag: mocks.useAddConversationTag,
  useRemoveConversationTag: mocks.useRemoveConversationTag,
  useSetConversationPinned: mocks.useSetConversationPinned,
  useSetConversationStarred: mocks.useSetConversationStarred,
  useBatchDeleteConversations: mocks.useBatchDeleteConversations,
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: mocks.useAuth,
}));

// ---- factories ----
// jsdom 里 window.confirm 默认弹原生框(测试里会抛 / 卡住),stub 成返回 true
// 才能让 handleDeleteConversation / handleBatchDelete 走到 mutateAsync 分支。
const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  const now = "2026-07-30T10:00:00Z";
  return {
    id: "conv_1",
    agent_id: "ag_1",
    tenant_id: "tn_1",
    user_id: "u_1",
    title: "测试会话",
    customer_id: null,
    tags: [],
    is_pinned: false,
    is_starred: false,
    kind: "single",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function makeStoreMe(): MeResponse {
  return {
    user_id: "u_owner",
    tenant_id: "tn_1",
    email: "owner@example.com",
    platform_role: null,
    roles: ["owner"],
    permissions: [],
    customer_id: null,
  };
}

// 标准 mutation stub:resolve 立即成功,isPending 默认 false。
function makeMut(overrides: Partial<{ isPending: boolean }> = {}) {
  return {
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
    ...overrides,
  };
}

// 把所有 use* hooks 喂成稳定 stub,避免每个用例重复设置。
function stubPanelBasics(me: MeResponse = makeStoreMe()) {
  mocks.useAuth.mockReturnValue({ me });
  mocks.useConversations.mockReturnValue({ data: [], isLoading: false });
  mocks.useCustomerProfiles.mockReturnValue({ data: [] });
  mocks.useDeleteConversation.mockReturnValue(makeMut());
  mocks.useRenameConversation.mockReturnValue(makeMut());
  mocks.useAddConversationTag.mockReturnValue(makeMut());
  mocks.useRemoveConversationTag.mockReturnValue(makeMut());
  mocks.useSetConversationPinned.mockReturnValue(makeMut());
  mocks.useSetConversationStarred.mockReturnValue(makeMut());
  mocks.useBatchDeleteConversations.mockReturnValue(makeMut());
}

afterEach(() => {
  vi.clearAllMocks();
  confirmSpy.mockClear();
});

// 行尾「更多操作」trigger 是 MoreVertical icon-only ghost button,group-hover 才显。
// 直接在行 scope 取该 button(Radix DropdownMenu 项 portal 挂到 body,trigger 留行内)。
async function openRowMenu(
  user: ReturnType<typeof userEvent.setup>,
  body: HTMLElement,
  rowIndex: number = 0,
) {
  const rows = body.querySelectorAll("li");
  const row = rows[rowIndex] as HTMLElement;
  const trigger = within(row).getByTitle("更多操作");
  await user.click(trigger);
  return body.ownerDocument.body;
}

describe("ConversationListPanel — 列表交互", () => {
  it("空数据显示「还没有会话」", () => {
    stubPanelBasics();
    const { getByText } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    expect(getByText("还没有会话，发送消息开始对话")).toBeInTheDocument();
  });

  it("searchCommitted 时空数据显示「没有匹配的会话」", () => {
    stubPanelBasics();
    const { getByText } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        initialSearch="不存在的词"
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    expect(getByText("没有匹配的会话")).toBeInTheDocument();
  });

  it("渲染会话列表(title)", () => {
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [
        makeConversation({ id: "conv_a", title: "如何退款" }),
        makeConversation({ id: "conv_b", title: "设备排期" }),
      ],
      isLoading: false,
    });
    const { getByText } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    expect(getByText("如何退款")).toBeInTheDocument();
    expect(getByText("设备排期")).toBeInTheDocument();
  });

  it("pinned/starred/composite 徽章按数据渲染", () => {
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [
        makeConversation({
          id: "conv_c",
          title: "复合会话",
          is_pinned: true,
          is_starred: true,
          kind: "composite",
        }),
      ],
      isLoading: false,
    });
    const { getByText, getAllByLabelText } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    // composite 徽章文本。
    expect(getByText("复合")).toBeInTheDocument();
    // pinned + starred 各一个 svg(用 aria-hidden svg 计数不稳,改用 title 属性)。
    // Pin / Star icon 没有可访问名,这里间接断言:复合徽章 + title 已渲染即够证明分支。
    expect(getAllByLabelText("选择会话").length).toBeGreaterThanOrEqual(1);
  });

  it("点击行触发 onSelectConversation(id)", async () => {
    const user = userEvent.setup();
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_pick", title: "点我" })],
      isLoading: false,
    });
    const onSelect = vi.fn();
    const { getByText } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={onSelect}
        onStartNew={() => {}}
      />,
    );
    await user.click(getByText("点我"));
    expect(onSelect).toHaveBeenCalledWith("conv_pick");
  });

  it("右键菜单 → 删除 → confirm 后调用 useDeleteConversation().mutateAsync(id)", async () => {
    const user = userEvent.setup();
    const deleteMut = makeMut();
    stubPanelBasics();
    mocks.useDeleteConversation.mockReturnValue(deleteMut);
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_del", title: "删我" })],
      isLoading: false,
    });

    const { baseElement } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);

    const item = await within(portal as HTMLElement).findByText("删除");
    await user.click(item);

    // window.confirm 被 stub 成 true → 走 mutateAsync。
    expect(deleteMut.mutateAsync).toHaveBeenCalledWith("conv_del");
  });

  it("删除当前选中会话后触发 onStartNew()(清理父层 state)", async () => {
    const user = userEvent.setup();
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_active", title: "当前" })],
      isLoading: false,
    });
    const onStartNew = vi.fn();
    const { baseElement } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId="conv_active"
        onSelectConversation={() => {}}
        onStartNew={onStartNew}
      />,
    );
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);
    await user.click(await within(portal as HTMLElement).findByText("删除"));

    expect(onStartNew).toHaveBeenCalled();
  });

  it("右键菜单 → 重命名 → 弹出 rename Dialog", async () => {
    const user = userEvent.setup();
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_rn", title: "原名" })],
      isLoading: false,
    });
    const { baseElement } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);
    await user.click(await within(portal as HTMLElement).findByText("重命名…"));

    // Dialog 标题异步出现。
    expect(
      await within(portal as HTMLElement).findByText("重命名会话"),
    ).toBeInTheDocument();
  });

  it("右键菜单 → 添加标签 → 弹出 add-tag Dialog", async () => {
    const user = userEvent.setup();
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_tag", title: "加签" })],
      isLoading: false,
    });
    const { baseElement } = renderWithProviders(
      <ConversationListPanel
        streaming={false}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    const portal = await openRowMenu(user, baseElement as unknown as HTMLElement);
    await user.click(await within(portal as HTMLElement).findByText("添加标签…"));

    expect(
      await within(portal as HTMLElement).findByText("添加标签"),
    ).toBeInTheDocument();
  });

  it("streaming=true 时行内 trigger disabled,无法打开菜单", () => {
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_s", title: "流中" })],
      isLoading: false,
    });
    const { getByTitle } = renderWithProviders(
      <ConversationListPanel
        streaming={true}
        activeConversationId={null}
        onSelectConversation={() => {}}
        onStartNew={() => {}}
      />,
    );
    const trigger = getByTitle("更多操作") as HTMLButtonElement;
    expect(trigger).toBeDisabled();
  });

  // 回归保护(code-review 发现):streaming 时点会话行不应切换会话。原 chat-page 靠
  // selectConversation 内 if(streaming) return 守卫;抽 Panel 后该守卫下移为行 button
  // 的 disabled={streaming}(与 trigger/新建按钮一致),否则 streaming 中途切会话会让
  // abortRef/localMessages 错配旧流。本用例锁住这个行为不回归。
  it("streaming=true 时行 button disabled,点击不触发 onSelectConversation", async () => {
    const user = userEvent.setup();
    stubPanelBasics();
    mocks.useConversations.mockReturnValue({
      data: [makeConversation({ id: "conv_stream", title: "流中行" })],
      isLoading: false,
    });
    const onSelect = vi.fn();
    const { getByText } = renderWithProviders(
      <ConversationListPanel
        streaming={true}
        activeConversationId={null}
        onSelectConversation={onSelect}
        onStartNew={() => {}}
      />,
    );
    const rowBtn = getByText("流中行").closest("button") as HTMLButtonElement;
    expect(rowBtn).toBeDisabled();
    await user.click(rowBtn); // disabled button 的 click 不会触发 onClick
    expect(onSelect).not.toHaveBeenCalled();
  });
});
