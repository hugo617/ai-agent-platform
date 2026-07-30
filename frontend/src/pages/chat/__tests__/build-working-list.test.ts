import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Message } from "@/api/types";

import { buildWorkingList } from "../build-working-list";

// buildWorkingList 是从 chat-page.tsx handleSend 抽出的「近纯函数」(plan
// chat-page-split Ticket 1):把当前显示的消息列表(base)+ 用户输入,拼成带
// 本地占位 user/assistant 两条消息的 working 列表,供流式渲染。
//
// 「近纯」而非「纯」:它读 Date.now 生成 local-user-/local-assistant- id 前缀
// 和 created_at。Ticket 1 注入 `now` 参数(default Date.now)把时间副作用收口
// 到一个可替换的注入点 —— 单测里用 fake timers 钉死时间,产出完全确定。

const FIXED_MS = 1_700_000_000_000; // 2023-11-14T22:13:20.000Z

describe("buildWorkingList — chat-page-split Ticket 1", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_MS);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("空 base → 仅返回 [userMsg, assistantMsg] 两条占位", () => {
    const working = buildWorkingList([], "你好");

    expect(working).toHaveLength(2);
    expect(working[0]).toMatchObject({ role: "user", content: "你好" });
    expect(working[1]).toMatchObject({ role: "assistant", content: "" });
  });

  it("非空 base → base 浅拷贝 + user + assistant 追加,长度 = base.length + 2", () => {
    const base: Message[] = [
      { id: "m1", role: "user", content: "历史问", created_at: "2023-01-01T00:00:00.000Z" },
      { id: "m2", role: "assistant", content: "历史答", created_at: "2023-01-01T00:00:01.000Z" },
    ];

    const working = buildWorkingList(base, "新问");

    expect(working).toHaveLength(4);
    // base 部分逐字保留(顺序 + 内容不变)。
    expect(working[0]).toEqual(base[0]);
    expect(working[1]).toEqual(base[1]);
    // 末两条是新增的占位。
    expect(working[2]).toMatchObject({ role: "user", content: "新问" });
    expect(working[3]).toMatchObject({ role: "assistant", content: "" });
  });

  it("注入 now → id 前缀与 created_at 用 now() 钉死时间(确定性)", () => {
    const ts = FIXED_MS;
    const iso = new Date(ts).toISOString();

    const working = buildWorkingList([], "hi", () => ts);

    expect(working[0]).toEqual({
      id: `local-user-${ts}`,
      role: "user",
      content: "hi",
      created_at: iso,
    });
    expect(working[1]).toEqual({
      id: `local-assistant-${ts}`,
      role: "assistant",
      content: "",
      created_at: iso,
    });
  });

  it("base 浅拷贝非别名 —— 改返回项不污染入参", () => {
    const base: Message[] = [
      { id: "m1", role: "user", content: "原", created_at: "2023-01-01T00:00:00.000Z" },
    ];

    const working = buildWorkingList(base, "新");
    // 调用方就地改 working 的某条 base 项(模拟 handleSend 流式填充)。
    (working[0] as Message).content = "被改了";

    // 入参 base 不应被影响 —— 这正是旧代码 `.map((m) => ({ ...m }))` 的语义。
    expect(base[0].content).toBe("原");
  });

  it("不注入 now → 回退 Date.now(用 fake timers 验证默认值)", () => {
    // 不传第三个参数,函数内部应走 Date.now —— 此时被 fake timers 钉在 FIXED_MS。
    const working = buildWorkingList([], "默认时钟");

    expect(working[0].id).toBe(`local-user-${FIXED_MS}`);
    expect(working[1].id).toBe(`local-assistant-${FIXED_MS}`);
    expect(working[0].created_at).toBe(new Date(FIXED_MS).toISOString());
  });
});
