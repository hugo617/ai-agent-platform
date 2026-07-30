/**
 * queries/conversations — conversations (chat history; streaming is NOT a query).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  addConversationTag,
  batchDeleteConversations,
  deleteConversation,
  fetchConversationStatistics,
  fetchConversations,
  fetchMessages,
  removeConversationTag,
  renameConversation,
  setConversationPinned,
  setConversationStarred,
} from "@/api/endpoints";
import type {
  ConversationFilters,
} from "@/api/types";
// ---------- conversations (chat history; streaming is NOT a query) ----------
// sendChatStream is an async generator consumed imperatively in chat-page.tsx
// (streaming deltas don't fit useMutation's one-shot success semantics), so
// there is no useChatStream hook here by design.
//
// conversation-management (priority 50): useConversations accepts search/tag
// filters; the query key encodes them so each filter set caches independently.
// All mutations invalidate the whole ["conversations"] family so every filter
// view refetches after a change.
export function useConversations(filters?: ConversationFilters) {
  return useQuery({
    queryKey: qk.conversations(filters),
    queryFn: () => fetchConversations(filters),
  });
}

// Conversation counts (total + 7d/30d) for the dashboard card.
export function useConversationStatistics() {
  return useQuery({
    queryKey: qk.conversationStats,
    queryFn: fetchConversationStatistics,
  });
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: qk.messages(conversationId ?? ""),
    queryFn: () => fetchMessages(conversationId as string),
    enabled: !!conversationId,
  });
}

export function useDeleteConversation() {
  return useApiMutation(
    (conversationId: string) => deleteConversation(conversationId),
    [["conversations"]],
  );
}

// conversation-management mutations (priority 50). Each invalidates the whole
// conversations family so the list (any active filter view) refetches.
export function useRenameConversation() {
  return useApiMutation(
    ({ id, title }: { id: string; title: string }) =>
      renameConversation(id, title),
    [["conversations"]],
  );
}

export function useAddConversationTag() {
  return useApiMutation(
    ({ id, tag }: { id: string; tag: string }) =>
      addConversationTag(id, tag),
    [["conversations"]],
  );
}

export function useRemoveConversationTag() {
  return useApiMutation(
    ({ id, tag }: { id: string; tag: string }) =>
      removeConversationTag(id, tag),
    [["conversations"]],
  );
}

export function useSetConversationPinned() {
  return useApiMutation(
    ({ id, pinned }: { id: string; pinned: boolean }) =>
      setConversationPinned(id, pinned),
    [["conversations"]],
  );
}

export function useSetConversationStarred() {
  return useApiMutation(
    ({ id, starred }: { id: string; starred: boolean }) =>
      setConversationStarred(id, starred),
    [["conversations"]],
  );
}

export function useBatchDeleteConversations() {
  return useApiMutation(
    (conversationIds: string[]) =>
      batchDeleteConversations(conversationIds),
    [["conversations"]],
  );
}

