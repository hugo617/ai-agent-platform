// chat-stream-wallet-gate 切片 02 —— ChatPage 402 充值引导面板组件测试。
//
// 覆盖 plan 切片 02 AC2/AC3:「catch instanceof ChatInsufficientBalanceError
// → balanceError state + 充值引导面板(标题 + 后端 detail + 前往充值 CTA),
// 其余错误维持 toast;发起发送前与切换会话双清除」。
//
// 测法:mock `@/api/endpoints/search` 的 sendChatStream(保留真实
// ChatInsufficientBalanceError 类供构造,错误分流逻辑已在
// chat-stream-402.test.ts 单元覆盖),断言组件级行为。ConversationListPanel
// 换成占位 stub(带一个触发 onSelectConversation 的按钮,供「切换会话
// 清除」用例);Panel 自身的交互已有专属测试文件。MemoryRouter 必须包:
// ChatPage 用 useSearchParams + useNavigate。
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/test-utils";
import { ChatPage } from "../index";
import { ChatInsufficientBalanceError } from "@/api/endpoints/search";

const BACKEND_DETAIL = "token 余额不足,请联系总部充值";
const PANEL_TITLE = "余额不足,无法发起对话";

// ---- mock wiring ----
const mocks = vi.hoisted(() => ({ sendChatStream: vi.fn() }));

vi.mock("@/api/endpoints/search", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/api/endpoints/search")>();
  return { ...mod, sendChatStream: mocks.sendChatStream };
});

vi.mock("@/hooks/queries", () => ({
  // ChatPage 自身消费的 4 个 hook(ConversationListPanel 已被 stub,树里
  // 不再有它的 9 个会话管理 hook)。
  useAgents: () => ({
    data: [
      {
        id: "agent-1",
        name: "测试智能体",
        is_orchestrator: false,
        specialist_ids: [],
      },
    ],
    isLoading: false,
  }),
  useConversations: () => ({ data: [] }),
  useCustomerProfiles: () => ({ data: [] }),
  useMessages: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: () => ({ me: null }),
}));

vi.mock("@/pages/chat/conversation-list-panel", () => ({
  ConversationListPanel: (props: {
    onSelectConversation: (id: string) => void;
  }) => (
    <div data-testid="panel-stub">
      <button type="button" onClick={() => props.onSelectConversation("conv-2")}>
        stub-select
      </button>
    </div>
  ),
}));

// 402:sendChatStream 首次 next() 即 reject(async generator 直接 throw,
// 忠实复刻真实 402 —— fetch 后、首个 yield 前就抛,组件还没收到任何 delta)。
function rejectWith402() {
  mocks.sendChatStream.mockImplementationOnce(
    // eslint-disable-next-line require-yield -- 只 throw 不 yield 是本 mock 的语义本体
    async function* () {
      throw new ChatInsufficientBalanceError(BACKEND_DETAIL);
    },
  );
}

function renderChat() {
  return renderWithProviders(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

async function send(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByTestId("message-input"), text);
  await user.click(screen.getByTestId("send-btn"));
}

describe("ChatPage — 402 充值引导面板(chat-stream-wallet-gate slice 02)", () => {
  beforeEach(() => {
    // hoisted vi.fn() 跨用例共享,call history 必须逐用例重置。
    mocks.sendChatStream.mockReset();
  });

  it("402 → 面板渲染(标题 + 后端 detail + 前往充值 CTA),不弹泛化 toast,不留假消息", async () => {
    rejectWith402();
    renderChat();

    await send("你好");

    expect(await screen.findByText(PANEL_TITLE)).toBeTruthy();
    expect(screen.getByText(BACKEND_DETAIL)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "前往充值" }),
    ).toBeTruthy();
    // 其余错误才走 toast;402 不弹「对话失败」。
    expect(screen.queryByText("对话失败")).toBeNull();
    // 后端被拦时不落任何消息(切片 01 语义)——本地 working list 回滚,
    // 不显示假的用户消息 / 空 assistant 占位。
    expect(screen.queryByText("你好")).toBeNull();
  });

  it("面板显示后再次发送成功 → 发送前清除(双清除之一)", async () => {
    rejectWith402();
    renderChat();

    await send("第一次");
    expect(await screen.findByText(PANEL_TITLE)).toBeTruthy();

    // 第二次发送成功(yield 一个 delta 后结束)——发送前应清掉面板。
    mocks.sendChatStream.mockImplementationOnce(async function* () {
      yield { delta: "好的" };
    });
    await send("第二次");

    await waitFor(() => {
      expect(screen.queryByText(PANEL_TITLE)).toBeNull();
    });
    expect(mocks.sendChatStream).toHaveBeenCalledTimes(2);
    // 成功流式正常渲染(第二条对话的 assistant 回复)。
    expect(await screen.findByText("好的")).toBeTruthy();
  });

  it("面板显示后切换会话 → 清除(双清除之二)", async () => {
    rejectWith402();
    renderChat();

    await send("你好");
    expect(await screen.findByText(PANEL_TITLE)).toBeTruthy();

    const user = userEvent.setup();
    await user.click(screen.getByText("stub-select"));

    await waitFor(() => {
      expect(screen.queryByText(PANEL_TITLE)).toBeNull();
    });
  });
});
