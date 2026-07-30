// buildWorkingList —— 从 chat-page.tsx handleSend 抽出的「近纯函数」。
// (chat-page-split Ticket 1, expand 阶段。chat-page.tsx 本切片不移动。)
//
// 作用:把当前显示的消息列表(base)+ 用户输入,拼成带本地占位 user/assistant
// 两条消息的 working 列表,供流式渲染时把 delta 累加到末尾的 assistant 占位。
//
// 「近纯」而非「纯」:它读时间(Date.now)生成 local-user-/local-assistant-
// id 前缀和 created_at。为保持可测,把时间副作用收口到一个可注入的 `now`
// 参数(default Date.now);调用方不传时行为与旧内联代码逐字等价。
//
// 保持与旧 handleSend 完全等价的细节(plan AC:不改任何调用方行为):
//   - base 先 `.map((m) => ({ ...m }))` 浅拷贝,确保流式阶段 `working[i].content`
//     就地修改不会回写 history/localMessages 入参(handleRegenerate 一致性前提);
//   - 两条占位的 id 前缀与 created_at 都直接读 now()(各读两次),与旧内联代码
//     每处独立调 Date.now()/new Date().toISOString() 语义对齐 —— 默认 `Date.now`
//     时两次读仍可能跨 tick,但不依赖单次快照(与旧行为一致);测试注入常量 `now`
//     把它们钉成同一时间点。

import type { Message } from "@/api/types";

export function buildWorkingList(
  base: Message[],
  userText: string,
  now: () => number = Date.now,
): Message[] {
  const baseCopy = base.map((m) => ({ ...m }));
  const userMsg: Message = {
    id: `local-user-${now()}`,
    role: "user",
    content: userText,
    created_at: new Date(now()).toISOString(),
  };
  const assistantMsg: Message = {
    id: `local-assistant-${now()}`,
    role: "assistant",
    content: "",
    created_at: new Date(now()).toISOString(),
  };
  return [...baseCopy, userMsg, assistantMsg];
}
