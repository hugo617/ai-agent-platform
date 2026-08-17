// chat-stream-wallet-gate 切片 02 —— sendChatStream 402 钱包门分支单元测试。
//
// 覆盖 plan 切片 02 AC1:「401 特判不动,402 → 容错解析 body detail → 抛
// ChatInsufficientBalanceError,其余维持泛化错误」+ AC3 的 401 不回归部分。
// 后端契约(切片 01):/chat/stream 在建立连接前统一预检,无钱包/零余额/
// 负余额/inactive → 402 + detail「token 余额不足,请联系总部充值」(与
// composite 路径同函数同错误体,矩阵 ⑦ 逐字一致断言)。
//
// 测法:stub 全局 fetch。sendChatStream 用原生 fetch(非 axios 实例,不经过
// client.ts 拦截器),所以 R1 rate-limited-toast.test 的「真 axios adapter」
// 范式在这里不适用;手工构造 { ok, status, json() } 最小 Response 形状,
// 断言公开行为(错误类型 / message / 副作用)。async generator 首次 next()
// 才执行到 fetch。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_EXPIRED_EVENT,
  getStoredToken,
  setStoredToken,
} from "@/api/client";
import {
  ChatInsufficientBalanceError,
  sendChatStream,
  type ChatStreamPayload,
} from "@/api/endpoints/search";

const BACKEND_DETAIL = "token 余额不足,请联系总部充值";

// sendChatStream 只消费 resp.ok / resp.status / resp.body / resp.json(),
// 手工最小 stub 比构造真 Response 更聚焦(也不依赖 jsdom 环境的 Response)。
function resp(status: number, body?: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json:
      body === undefined
        ? () => Promise.reject(new SyntaxError("Unexpected token in JSON"))
        : () => Promise.resolve(body),
  } as Response;
}

const payload: ChatStreamPayload = { agent_id: "agent-1", message: "你好" };

describe("sendChatStream — 402 钱包门分支(chat-stream-wallet-gate slice 02)", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("402 + JSON body → ChatInsufficientBalanceError,后端 detail 透传", async () => {
    fetchMock.mockResolvedValueOnce(resp(402, { detail: BACKEND_DETAIL }));
    const gen = sendChatStream(payload);
    let caught: unknown;
    try {
      await gen.next();
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ChatInsufficientBalanceError);
    expect((caught as Error).message).toBe(BACKEND_DETAIL);
  });

  it("402 + body 非 JSON(如网关裸 402 页)→ 仍抛 ChatInsufficientBalanceError,兜底文案", async () => {
    fetchMock.mockResolvedValueOnce(resp(402)); // json() reject → 容错分支
    const gen = sendChatStream(payload);
    let caught: unknown;
    try {
      await gen.next();
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ChatInsufficientBalanceError);
    // 兜底文案与后端 detail 同文(切片 01 矩阵 ⑦ 的统一口径)。
    expect((caught as Error).message).toBe(BACKEND_DETAIL);
  });

  it("401 → 既有行为不回归:清 token + 派发 AUTH_EXPIRED_EVENT + 泛化错误", async () => {
    setStoredToken("tok-stale");
    const expiredSpy = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expiredSpy);
    try {
      fetchMock.mockResolvedValueOnce(resp(401, { detail: "token expired" }));
      const gen = sendChatStream(payload);
      let caught: unknown;
      try {
        await gen.next();
      } catch (err) {
        caught = err;
      }
      expect(caught).not.toBeInstanceOf(ChatInsufficientBalanceError);
      expect((caught as Error).message).toBe("对话请求失败: 401");
      expect(getStoredToken()).toBeNull();
      expect(expiredSpy).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, expiredSpy);
    }
  });

  it("500 → 维持泛化错误(不误判为余额不足)", async () => {
    fetchMock.mockResolvedValueOnce(resp(500, { detail: "boom" }));
    const gen = sendChatStream(payload);
    let caught: unknown;
    try {
      await gen.next();
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(Error);
    expect(caught).not.toBeInstanceOf(ChatInsufficientBalanceError);
    expect((caught as Error).message).toBe("对话请求失败: 500");
  });
});
