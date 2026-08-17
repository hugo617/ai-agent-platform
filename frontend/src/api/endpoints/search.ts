/**
 * endpoints/search — global cross-entity search (priority 51).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  AUTH_EXPIRED_EVENT,
  api,
  getStoredToken,
  setStoredToken,
} from "../client";
import type {
  GlobalSearchResult,
} from "../types";
// ---------- global cross-entity search (priority 51) ----------
// GET /search?q=&limit_per_type= fans a single query across agents / customers /
// conversations (+ users / tenants for super_admin / hq_staff). The backend
// enforces tenant scoping: store users see their own tenant; cross-tenant
// viewers additionally get users + tenants. Short queries (< 2 chars) return an
// empty result, so callers gate the request on q.length >= 2 to avoid noise.
export async function globalSearch(
  q: string,
  limitPerType = 5,
): Promise<GlobalSearchResult> {
  const { data } = await api.get<GlobalSearchResult>("/search", {
    params: { q, limit_per_type: limitPerType },
  });
  return data;
}

export interface ChatStreamChunk {
  delta?: string;
  error?: string;
}

/**
 * Raised when POST /chat/stream returns 402 before the stream starts.
 *
 * chat-stream-wallet-gate: the backend pre-checks the wallet balance before
 * establishing the SSE connection (same gate + same detail body as composite),
 * so a low wallet rejects the turn with a real HTTP 402 instead of a mid-stream
 * error frame. Mirror of `CompositeInsufficientBalanceError` — callers catch
 * it to render the recharge guidance panel instead of a generic toast.
 */
export class ChatInsufficientBalanceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatInsufficientBalanceError";
  }
}

export interface ChatStreamPayload {
  agent_id: string;
  conversation_id?: string;
  message: string;
  // Optional customer attribution (Token 费用管理系列 3/4). Only takes
  // effect when creating a new conversation (no conversation_id). Lets a
  // staff member tag a chat as "serving customer X" for usage attribution.
  customer_id?: string;
}

/**
 * Stream a chat reply from `POST /chat/stream` (Server-Sent Events).
 *
 * Yields `{ delta }` chunks as the assistant's reply arrives (for a typewriter
 * effect), `{ error }` if the server reports one mid-stream, then returns when
 * the `data: [DONE]` sentinel arrives. Pass an AbortSignal to cancel.
 */
export async function* sendChatStream(
  payload: ChatStreamPayload,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamChunk> {
  const token = getStoredToken();
  const resp = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!resp.ok) {
    // Replicate the axios interceptor's 401 handling: a stale token clears
    // local state and fires the event AuthProvider listens for (→ /login).
    if (resp.status === 401) {
      setStoredToken(null);
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    // Wallet-gate 402 arrives before the stream starts (fetch path, so we
    // parse the JSON body ourselves rather than going through apiErrorMessage,
    // which only knows AxiosError). Tolerate a non-JSON body (e.g. a bare
    // gateway 402 page) by falling back to the backend's canonical wording.
    if (resp.status === 402) {
      let detail = "token 余额不足,请联系总部充值";
      try {
        const body = (await resp.json()) as { detail?: unknown };
        if (typeof body.detail === "string" && body.detail) detail = body.detail;
      } catch {
        // non-JSON body — keep the fallback detail
      }
      throw new ChatInsufficientBalanceError(detail);
    }
    throw new Error(`对话请求失败: ${resp.status}`);
  }
  if (!resp.body) throw new Error("浏览器不支持流式响应");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; the last segment may be a
    // partial frame, so keep it buffered for the next read.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      const data = line.slice(line.indexOf(":") + 1).trim();
      if (data === "[DONE]") return;
      try {
        yield JSON.parse(data) as ChatStreamChunk;
      } catch {
        // Non-JSON frame (e.g. keep-alive comment) — skip.
      }
    }
  }
}

