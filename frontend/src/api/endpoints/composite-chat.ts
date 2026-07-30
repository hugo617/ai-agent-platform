/**
 * endpoints/composite-chat — composite chat (priority 72, non-streaming).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import { AxiosError } from "axios";
import {
  api,
  apiErrorMessage,
} from "../client";
import type {
  CompositeRequest,
  CompositeResponse,
} from "../types";
// ---------- composite chat (priority 72, non-streaming) ----------
//
// POST /chat/composite fans out to N agents and synthesizes one answer. Unlike
// sendChatStream above, this is a plain JSON request/response (the synthesis is
// a single payload, not a token stream), so it goes through the axios `api`
// instance like every other endpoint.
//
// 402 is the project's first real HTTP Payment Required (AC4.8): the backend
// rejects a composite turn when the wallet can't cover the N+1 token cost
// (strict, unlike /chat/stream's "no wallet = let it through" SSE error frame).
// We surface it as a distinct error class so the UI can show a recharge prompt
// instead of a generic toast — callers catch `CompositeInsufficientBalanceError`
// to render the recharge guidance, everything else falls through to
// `apiErrorMessage`.

/** Raised when POST /chat/composite returns 402 (wallet can't cover N+1 cost). */
export class CompositeInsufficientBalanceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CompositeInsufficientBalanceError";
  }
}

/** POST /chat/composite — fan out to N agents, return one synthesized answer. */
export async function compositeChat(
  payload: CompositeRequest,
): Promise<CompositeResponse> {
  try {
    const { data } = await api.post<CompositeResponse>("/chat/composite", payload);
    return data;
  } catch (err) {
    if (err instanceof AxiosError && err.response?.status === 402) {
      // Lift the backend detail (or fall back to a stable message) so the UI's
      // recharge prompt has something concrete to show.
      const detail = apiErrorMessage(err);
      throw new CompositeInsufficientBalanceError(detail);
    }
    throw err;
  }
}

