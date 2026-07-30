/**
 * endpoints/conversations-+-chat — conversations + chat (SSE streaming).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Conversation,
  ConversationStatistics,
  Message,
} from "../types";
// ---------- conversations + chat (SSE streaming) ----------
//
// `sendChatStream` is the one endpoint that bypasses the axios `api` instance:
// SSE responses must be consumed frame-by-frame, and axios buffers the whole
// body (losing the streaming effect). We use a raw `fetch` + ReadableStream
// instead, manually attaching the bearer token (axios interceptor can't run)
// and replicating the client's 401 → auth-expired handling.

export async function fetchConversations(params?: {
  search?: string;
  tag?: string;
}): Promise<Conversation[]> {
  const { data } = await api.get<Conversation[]>("/conversations/", {
    params: { search: params?.search, tag: params?.tag },
  });
  return data;
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const { data } = await api.get<Message[]>(
    `/conversations/${conversationId}/messages`,
  );
  return data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`/conversations/${conversationId}`);
}

// conversation-management (priority 50): rename / tags / pin / star / batch.
// All gated by conversations:update (or :delete) on the backend; ownership is
// re-checked server-side (only the conversation owner may mutate it).
export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/conversations/${conversationId}/title`,
    { title },
  );
  return data;
}

export async function addConversationTag(
  conversationId: string,
  tag: string,
): Promise<Conversation> {
  const { data } = await api.post<Conversation>(
    `/conversations/${conversationId}/tags`,
    { tag },
  );
  return data;
}

export async function removeConversationTag(
  conversationId: string,
  tag: string,
): Promise<Conversation> {
  const { data } = await api.delete<Conversation>(
    `/conversations/${conversationId}/tags/${encodeURIComponent(tag)}`,
  );
  return data;
}

export async function setConversationPinned(
  conversationId: string,
  pinned: boolean,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/conversations/${conversationId}/pin`,
    { pinned },
  );
  return data;
}

export async function setConversationStarred(
  conversationId: string,
  starred: boolean,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/conversations/${conversationId}/star`,
    { starred },
  );
  return data;
}

export async function batchDeleteConversations(
  conversationIds: string[],
): Promise<{ deleted: number }> {
  const { data } = await api.post<{ deleted: number }>(
    "/conversations/batch-delete",
    { conversation_ids: conversationIds },
  );
  return data;
}

// Conversation counts (total + 7d/30d windows) for the dashboard card. Store
// users are scoped to their tenant; super_admin aggregates across tenants.
export async function fetchConversationStatistics(): Promise<ConversationStatistics> {
  const { data } = await api.get<ConversationStatistics>(
    "/conversations/statistics",
  );
  return data;
}

