import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  Check,
  Copy,
  MessageSquare,
  MoreVertical,
  Pin,
  Plus,
  RotateCcw,
  Send,
  Square,
  Star,
  Tags,
  Trash2,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { MarkdownView } from "@/components/chat/markdown-view";
import { apiErrorMessage } from "@/api/client";
import { sendChatStream } from "@/api/endpoints";
import type { Conversation, Message } from "@/api/types";
import {
  useAddConversationTag,
  useAgents,
  useBatchDeleteConversations,
  useConversations,
  useCustomerProfiles,
  useDeleteConversation,
  useMessages,
  useRemoveConversationTag,
  useRenameConversation,
  useSetConversationPinned,
  useSetConversationStarred,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

/**
 * Pick a display label for a conversation: its title, or a snippet of the
 * first user message, or a fallback. (Backend may leave title null on first
 * turn; the list should still show something legible.)
 */
function conversationLabel(c: Conversation, firstMessage?: Message): string {
  if (c.title) return c.title;
  if (firstMessage?.content) {
    const snippet = firstMessage.content.trim().slice(0, 20);
    return snippet.length < firstMessage.content.trim().length
      ? `${snippet}…`
      : snippet;
  }
  return "新对话";
}

export function ChatPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const { me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const { data: agents, isLoading: agentsLoading } = useAgents();

  // ---------------- conversation-management state ----------------
  // Debounced search: a separate "committed" value drives the query, updated
  // 300ms after the input stops changing so each keystroke doesn't fire a
  // request. Empty string → undefined so the bare query key is reused.
  // Seed the conversation search box from a ?search= URL param so the global-
  // search-box "查看全部" deep link carries the term into this page. Existing
  // URL reads (customer_id) are preserved.
  const [searchInput, setSearchInput] = useState(
    searchParams.get("search") ?? "",
  );
  const [searchCommitted, setSearchCommitted] = useState<string | undefined>(
    searchParams.get("search")
      ? (searchParams.get("search") as string).trim() || undefined
      : undefined,
  );
  useEffect(() => {
    const handle = setTimeout(() => {
      const v = searchInput.trim();
      setSearchCommitted(v.length > 0 ? v : undefined);
    }, 300);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const { data: conversations, isLoading: convsLoading } = useConversations(
    searchCommitted ? { search: searchCommitted } : undefined,
  );
  // Multi-select for batch operations. Cleared whenever the list refetches
  // (mutations invalidate) — tracked via an effect on the conversations array.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // Clear the multi-selection only when the *set* of conversation ids actually
  // changes (a conversation was added or removed), NOT on every background
  // refetch. Keying on the id-join (a primitive string) means a pin/star toggle
  // that merely reorders the list (same ids, new array reference) no longer
  // wipes an in-progress multi-select.
  const conversationIdSet = conversations?.map((c) => c.id).join(",") ?? "";
  useEffect(() => {
    setSelectedIds(new Set());
  }, [conversationIdSet]);

  // Store customer profiles for the "关联客户" picker (store users only).
  // super_admin doesn't serve individual store customers, so we disable the
  // query for them (the endpoint permits super_admin, but the picker is hidden
  // via !isSuperAdmin(me) — no point fetching every store's profiles).
  const { data: customerProfiles } = useCustomerProfiles(!isSuperAdmin(me));

  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null);
  // Token 费用管理系列 3/4: optional customer attribution for a NEW chat.
  // Cleared whenever an existing conversation is selected (attribution is set
  // at creation time only — follow-up turns keep the original binding).
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");

  const { data: history, isLoading: historyLoading } = useMessages(
    selectedConversationId,
  );
  const deleteConv = useDeleteConversation();
  const renameConv = useRenameConversation();
  const addTagMut = useAddConversationTag();
  const removeTagMut = useRemoveConversationTag();
  const pinMut = useSetConversationPinned();
  const starMut = useSetConversationStarred();
  const batchDeleteMut = useBatchDeleteConversations();

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  // Local messages layered on top of (or instead of) the loaded history while
  // a reply is being streamed, so the assistant's text appears progressively.
  const [localMessages, setLocalMessages] = useState<Message[] | null>(null);

  // Rename + add-tag dialog state (one open at a time over a target conv).
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [tagTarget, setTagTarget] = useState<Conversation | null>(null);
  const [tagValue, setTagValue] = useState("");

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Tracks which message currently shows the "copied" check, so each row has
  // independent feedback without per-row state.
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Auto-select the first agent once the list loads.
  useEffect(() => {
    if (!selectedAgentId && agents && agents.length > 0) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId]);

  // "为客户咨询" deep link: arriving at /chat?customer_id=<id> pre-fills the
  // customer picker so the next new conversation is attributed to them.
  useEffect(() => {
    const cid = searchParams.get("customer_id");
    if (cid) {
      setSelectedConversationId(null); // start a fresh conversation
      setSelectedCustomerId(cid);
      // Clear the param so a later manual "new chat" doesn't re-bind silently.
      searchParams.delete("customer_id");
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // A lookup from customer_id → display name, for showing attribution in the
  // conversation header / list (falls back to the bare id if not loaded).
  const customerNameOf = (cid: string | null): string | null => {
    if (!cid) return null;
    const p = customerProfiles?.find((x) => x.customer_id === cid);
    return p?.customer.name ?? null;
  };

  // Show loaded history unless we're streaming (then show localMessages).
  const messages = localMessages ?? history ?? [];

  // Auto-scroll to the bottom whenever the message count or the last message's
  // content changes (e.g. a streaming delta arrives). Keying on these derived
  // primitives avoids re-firing on every render, which an array dep would do.
  const lastContent = messages[messages.length - 1]?.content ?? "";
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, lastContent]);

  // Reset local overlay when switching conversations.
  useEffect(() => {
    setLocalMessages(null);
  }, [selectedConversationId]);

  const startNewConversation = () => {
    if (streaming) return;
    setSelectedConversationId(null);
    setSelectedCustomerId("");
    setLocalMessages(null);
    setInput("");
  };

  const selectConversation = (id: string) => {
    if (streaming) return;
    setSelectedConversationId(id);
    // Clear the customer picker — existing conversations keep their original
    // attribution; the picker only drives NEW conversations.
    setSelectedCustomerId("");
  };

  const handleDeleteConversation = async (conv: Conversation) => {
    if (streaming) return;
    if (!confirm("确认删除这个会话？此操作不可撤销。")) return;
    try {
      await deleteConv.mutateAsync(conv.id);
      if (selectedConversationId === conv.id) {
        setSelectedConversationId(null);
        setLocalMessages(null);
      }
      toast.success("已删除会话");
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  // ---------------- conversation-management handlers ----------------
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBatchDelete = async () => {
    if (streaming) return;
    if (selectedIds.size === 0) return;
    if (!confirm(`确认删除选中的 ${selectedIds.size} 个会话？此操作不可撤销。`))
      return;
    const ids = Array.from(selectedIds);
    try {
      const res = await batchDeleteMut.mutateAsync(ids);
      if (selectedConversationId && ids.includes(selectedConversationId)) {
        setSelectedConversationId(null);
        setLocalMessages(null);
      }
      toast.success(`已删除 ${res.deleted} 个会话`);
    } catch (err) {
      toast.error("批量删除失败", apiErrorMessage(err));
    }
  };

  const openRename = (conv: Conversation) => {
    setRenameTarget(conv);
    setRenameValue(conv.title ?? "");
  };

  const submitRename = async () => {
    if (!renameTarget) return;
    const title = renameValue.trim();
    if (!title) return;
    try {
      await renameConv.mutateAsync({ id: renameTarget.id, title });
      setRenameTarget(null);
      toast.success("已重命名");
    } catch (err) {
      toast.error("重命名失败", apiErrorMessage(err));
    }
  };

  const openAddTag = (conv: Conversation) => {
    setTagTarget(conv);
    setTagValue("");
  };

  const submitAddTag = async () => {
    if (!tagTarget) return;
    const tag = tagValue.trim();
    if (!tag) return;
    try {
      await addTagMut.mutateAsync({ id: tagTarget.id, tag });
      setTagValue("");
      toast.success("已添加标签");
    } catch (err) {
      toast.error("添加标签失败", apiErrorMessage(err));
    }
  };

  const handleRemoveTag = async (conv: Conversation, tag: string) => {
    try {
      await removeTagMut.mutateAsync({ id: conv.id, tag });
    } catch (err) {
      toast.error("删除标签失败", apiErrorMessage(err));
    }
  };

  const handleTogglePin = async (conv: Conversation) => {
    try {
      await pinMut.mutateAsync({ id: conv.id, pinned: !conv.is_pinned });
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };

  const handleToggleStar = async (conv: Conversation) => {
    try {
      await starMut.mutateAsync({ id: conv.id, starred: !conv.is_starred });
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    if (!selectedAgentId) {
      toast.error("请先选择一个智能体");
      return;
    }

    setInput("");
    setStreaming(true);

    // Build the working message list: the currently-shown messages + the user
    // turn + an empty assistant placeholder that we'll fill as deltas arrive.
    // We branch on `localMessages ?? history` (the displayed list) rather than
    // just `history` so a regenerate stays consistent: handleRegenerate drops
    // the trailing assistant turn into `localMessages`, and basing the next
    // send on that trimmed view means the old assistant reply is NOT re-sent
    // as context and the user turn isn't duplicated in the working list.
    const base = (localMessages ?? history ?? []).map((m) => ({ ...m }));
    const userMsg: Message = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    const assistantMsg: Message = {
      id: `local-assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };
    const working = [...base, userMsg, assistantMsg];
    setLocalMessages(working);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const chunk of sendChatStream(
        {
          agent_id: selectedAgentId,
          conversation_id: selectedConversationId ?? undefined,
          message: text,
          // Only attribute a NEW conversation; follow-up turns reuse the
          // existing conversation_id (whose customer_id was set at creation).
          customer_id: selectedConversationId
            ? undefined
            : selectedCustomerId || undefined,
        },
        controller.signal,
      )) {
        if (chunk.error) {
          toast.error("对话出错", chunk.error);
          break;
        }
        if (chunk.delta) {
          assistantMsg.content += chunk.delta;
          setLocalMessages([...working]);
        }
      }
    } catch (err) {
      // User-initiated abort (stop button) is not an error — the partial reply
      // stays on screen and the finally block cleans up. Distinguish by name
      // since fetch abort throws a DOMException named "AbortError".
      if (err instanceof Error && err.name === "AbortError") return;
      toast.error("对话失败", apiErrorMessage(err));
    } finally {
      setStreaming(false);
      abortRef.current = null;
      // Refresh the conversation list (a new conversation may have been
      // created on first turn; the list now reflects updated_at ordering).
      qc.invalidateQueries({ queryKey: ["conversations"] });
    }
  };

  const handleStop = () => {
    // Abort the in-flight SSE stream. The finally block in handleSend then
    // resets `streaming` and refreshes the conversation list. The partial
    // assistant content already rendered stays on screen (not persisted by the
    // backend, since aborting the request cancels server-side generation).
    abortRef.current?.abort();
  };

  const handleCopyMessage = async (msg: Message) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // clipboard unavailable (insecure context, e.g. non-HTTPS) — surface it
      // so the user isn't left wondering why "copy" did nothing.
      toast.error("复制失败", "剪贴板不可用(需 HTTPS 环境)");
    }
  };

  // Regenerate the last assistant reply: drop the trailing assistant placeholder
  // and put the preceding user message's text back into the input box for the
  // user to re-send. This is the "simplified" plan variant — it avoids the
  // backend storing a duplicate user message (which a full auto-resend would
  // cause). Only available on the last assistant message and when not streaming.
  const handleRegenerate = () => {
    if (streaming) return;
    const msgs = messages;
    const last = msgs[msgs.length - 1];
    if (!last || last.role !== "assistant") return;
    const prevUser = msgs[msgs.length - 2];
    if (!prevUser || prevUser.role !== "user") return;
    // Remove the trailing assistant turn from the local view; if localMessages
    // is null (viewing pure history), switch to a local copy sans last turn.
    const trimmed = msgs.slice(0, -1);
    setLocalMessages(trimmed);
    setInput(prevUser.content);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    // Enter to send, Shift+Enter for newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      {/* ---- conversation list ---- */}
      <Card className="flex h-[70vh] flex-col lg:h-[calc(100vh-12rem)] lg:order-1 order-2">
        <CardHeader className="space-y-2">
          <div className="flex-row flex items-center justify-between">
            <CardTitle className="text-base">会话</CardTitle>
            <div className="flex items-center gap-1">
              {selectedIds.size > 0 && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleBatchDelete}
                  title="批量删除选中"
                  disabled={streaming}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={startNewConversation}
                title="新建对话"
                disabled={streaming}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {/* Debounced search box. Empty input clears the filter (lists all). */}
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="搜索标题或内容…"
            className="h-8 text-sm"
          />
        </CardHeader>
        <CardContent className="min-h-0 flex-1 overflow-y-auto p-2">
          {convsLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !conversations?.length ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <MessageSquare className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {searchCommitted ? "没有匹配的会话" : "还没有会话，发送消息开始对话"}
              </p>
            </div>
          ) : (
            <ul className="space-y-1">
              {conversations.map((conv) => {
                const active = conv.id === selectedConversationId;
                const isSelected = selectedIds.has(conv.id);
                return (
                  <li key={conv.id}>
                    <div
                      className={`group flex items-center gap-1 rounded-md px-2 py-2 text-sm transition-colors ${
                        active
                          ? "bg-accent text-accent-foreground"
                          : isSelected
                            ? "bg-accent/30"
                            : "hover:bg-accent/50"
                      }`}
                    >
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => toggleSelect(conv.id)}
                        className="h-3.5 w-3.5 shrink-0"
                        aria-label="选择会话"
                      />
                      <button
                        className="flex min-h-[28px] flex-1 flex-col items-start truncate text-left"
                        onClick={() => selectConversation(conv.id)}
                        title={conversationLabel(conv)}
                      >
                        <span className="flex w-full items-center gap-1 truncate">
                          {conv.is_pinned && (
                            <Pin className="h-3 w-3 shrink-0 text-amber-500" />
                          )}
                          {conv.is_starred && (
                            <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-400" />
                          )}
                          <span className="truncate">
                            {conversationLabel(conv)}
                          </span>
                        </span>
                        <span className="flex w-full items-center gap-1 text-[11px] text-muted-foreground">
                          {conv.customer_id && (() => {
                            const n = customerNameOf(conv.customer_id);
                            return n ? (
                              <span className="inline-flex items-center gap-0.5">
                                <User className="h-2.5 w-2.5" />
                                {n}
                              </span>
                            ) : null;
                          })()}
                          {fmt(conv.created_at)}
                        </span>
                        {/* Tag chips: click a chip to remove it. */}
                        {conv.tags.length > 0 && (
                          <span className="mt-0.5 flex flex-wrap gap-1">
                            {conv.tags.map((t) => (
                              <span
                                key={t}
                                className="inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-px text-[10px]"
                              >
                                {t}
                                <button
                                  type="button"
                                  className="text-muted-foreground hover:text-foreground"
                                  title={`删除标签 ${t}`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleRemoveTag(conv, t);
                                  }}
                                >
                                  ×
                                </button>
                              </span>
                            ))}
                          </span>
                        )}
                      </button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            className="inline-flex min-h-[28px] min-w-[28px] items-center justify-center opacity-0 transition-opacity group-hover:opacity-100 data-[state=open]:opacity-100"
                            title="更多操作"
                            disabled={streaming}
                          >
                            <MoreVertical className="h-3.5 w-3.5" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openRename(conv)}>
                            重命名…
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openAddTag(conv)}>
                            <Tags className="h-3.5 w-3.5" />
                            添加标签…
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleTogglePin(conv)}>
                            <Pin className="h-3.5 w-3.5" />
                            {conv.is_pinned ? "取消置顶" : "置顶"}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => handleToggleStar(conv)}
                          >
                            <Star className="h-3.5 w-3.5" />
                            {conv.is_starred ? "取消收藏" : "收藏"}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => handleDeleteConversation(conv)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            删除
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ---- chat panel ---- */}
      <Card className="flex h-[70vh] flex-col lg:h-[calc(100vh-12rem)] lg:order-2 order-1">
        {/* agent picker + header */}
        <CardHeader className="flex-row items-center justify-between space-y-0 border-b">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base">对话</CardTitle>
            <Select
              value={selectedAgentId}
              onValueChange={setSelectedAgentId}
              disabled={streaming || agentsLoading}
            >
              <SelectTrigger className="h-8 w-48">
                <SelectValue
                  placeholder={agentsLoading ? "加载中…" : "选择智能体"}
                />
              </SelectTrigger>
              <SelectContent>
                {agents?.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Multi-agent orchestration (priority 58): when an orchestrator is
                selected, hint that messages will be routed to specialists. MVP
                does not show real-time specialist attribution (SSE frames carry
                no source field); only this static hint. */}
            {(() => {
              const agent = agents?.find((a) => a.id === selectedAgentId);
              if (!agent?.is_orchestrator) return null;
              const n = agent.specialist_ids.length;
              return (
                <span className="rounded-md bg-accent px-2 py-1 text-xs text-muted-foreground">
                  编排器{n > 0 ? `:将路由到 ${n} 个 specialist` : ":未挂载 specialist"}
                </span>
              );
            })()}

            {/* Token 费用管理系列 3/4: optional customer attribution picker.
                Store users can tag a NEW chat as "serving customer X". Hidden
                for super_admin (they don't serve store customers) and disabled
                when viewing an existing conversation (attribution is fixed at
                creation). */}
            {!isSuperAdmin(me) && !selectedConversationId && (
              <Select
                value={selectedCustomerId || "_none"}
                onValueChange={(v) =>
                  setSelectedCustomerId(v === "_none" ? "" : v)
                }
                disabled={streaming}
              >
                <SelectTrigger className="h-8 w-44">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <User className="h-3.5 w-3.5" />
                    <SelectValue placeholder="关联客户(可选)" />
                  </span>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">不关联客户</SelectItem>
                  {customerProfiles?.map((p) => (
                    <SelectItem key={p.customer_id} value={p.customer_id}>
                      {p.customer.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {/* When viewing an existing conversation that's attributed to a
                customer, show a read-only badge so the staff member knows who
                they're serving in this chat. */}
            {!isSuperAdmin(me) && selectedConversationId && (() => {
              const conv = conversations?.find(
                (c) => c.id === selectedConversationId,
              );
              const cname = customerNameOf(conv?.customer_id ?? null);
              return cname ? (
                <span className="flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs">
                  <User className="h-3 w-3" />
                  {cname}
                </span>
              ) : null;
            })()}
          </div>
          {selectedConversationId && (
            <span className="text-xs text-muted-foreground">
              {fmt(
                conversations?.find((c) => c.id === selectedConversationId)
                  ?.updated_at ?? null,
              )}
            </span>
          )}
        </CardHeader>

        {/* message stream */}
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-6">
          {historyLoading && !localMessages ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <MessageSquare className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                选择一个智能体，发送消息开始对话
              </p>
            </div>
          ) : (
            messages.map((msg, idx) => {
              const isAssistant = msg.role === "assistant";
              const isLastAssistant =
                isAssistant && idx === messages.length - 1;
              return (
                <div
                  key={msg.id}
                  data-testid={isAssistant ? "assistant-message" : "user-message"}
                  className={`group flex ${
                    isAssistant ? "justify-start" : "justify-end"
                  }`}
                >
                  <div
                    className={`relative max-w-[85%] overflow-hidden rounded-lg px-4 py-2 text-sm ${
                      isAssistant ? "bg-muted" : "bg-primary text-primary-foreground"
                    }`}
                  >
                    {isAssistant ? (
                      msg.content ? (
                        <div className="overflow-x-auto">
                          <MarkdownView content={msg.content} />
                        </div>
                      ) : (
                        <span className="text-muted-foreground">…</span>
                      )
                    ) : (
                      <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                        {msg.content}
                      </div>
                    )}

                    {isAssistant && msg.content && (
                      <div className="mt-1.5 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                        <button
                          type="button"
                          onClick={() => handleCopyMessage(msg)}
                          title="复制"
                          className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          {copiedId === msg.id ? (
                            <Check className="h-3.5 w-3.5" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                        {isLastAssistant && !streaming && (
                          <button
                            type="button"
                            onClick={handleRegenerate}
                            title="重新生成"
                            className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* input */}
        <CardContent className="border-t p-4">
          <div className="flex items-end gap-2">
            <textarea
              className="flex min-h-[40px] max-h-32 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="输入消息…(Enter 发送，Shift+Enter 换行)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              disabled={streaming}
              rows={1}
              data-testid="message-input"
            />
            {streaming ? (
              <Button
                onClick={handleStop}
                size="icon"
                variant="destructive"
                title="停止生成"
                data-testid="send-btn"
              >
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                onClick={handleSend}
                disabled={!input.trim()}
                size="icon"
                title="发送"
                data-testid="send-btn"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ---- rename dialog ---- */}
      <Dialog
        open={renameTarget !== null}
        onOpenChange={(open) => !open && setRenameTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rename-input">标题</Label>
            <Input
              id="rename-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitRename();
              }}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameTarget(null)}>
              取消
            </Button>
            <Button
              onClick={submitRename}
              disabled={!renameValue.trim() || renameConv.isPending}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---- add-tag dialog ---- */}
      <Dialog
        open={tagTarget !== null}
        onOpenChange={(open) => !open && setTagTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加标签</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="tag-input">标签名</Label>
            <Input
              id="tag-input"
              value={tagValue}
              onChange={(e) => setTagValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitAddTag();
              }}
              placeholder="如：重要、待跟进"
              autoFocus
            />
            {tagTarget && tagTarget.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {tagTarget.tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-px text-[11px]"
                  >
                    {t}
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => handleRemoveTag(tagTarget, t)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTagTarget(null)}>
              完成
            </Button>
            <Button
              onClick={submitAddTag}
              disabled={!tagValue.trim() || addTagMut.isPending}
            >
              添加
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
