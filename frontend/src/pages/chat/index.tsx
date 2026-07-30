// chat/ index.tsx — the chat page's route entry (the public page export).
//
// Extracted from the original pages/chat-page.tsx (plan-chat-page-split
// Ticket 3). Pure locality move: zero behaviour change. The 583-line streaming
// half + orchestration lives here; the conversation-list half was already
// extracted to ConversationListPanel in Ticket 2.
//
// Why both ``index.tsx`` and ``chat-page.tsx``: ``index.tsx`` is the
// conventional folder-entry name (matches the "one module per folder" intent);
// ``chat-page.tsx`` is the named file App.tsx's lazy loader points at, kept to
// preserve the existing "page file name = route name" convention without
// touching the router. This mirrors the bookings/ double-entry pattern.
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import {
  Check,
  Copy,
  MessageSquare,
  RotateCcw,
  Send,
  Square,
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
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { MarkdownView } from "@/components/chat/markdown-view";
import { Switch } from "@/components/ui/switch";
import { apiErrorMessage } from "@/api/client";
import { sendChatStream } from "@/api/endpoints";
import { CompositeMode } from "@/pages/composite-mode";
import type { ConversationKind, Message } from "@/api/types";
import { buildWorkingList } from "@/pages/chat/build-working-list";
import { ConversationListPanel } from "@/pages/chat/conversation-list-panel";
import { customerNameOf } from "@/pages/chat/customer-helpers";
import {
  useAgents,
  useConversations,
  useCustomerProfiles,
  useMessages,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

export function ChatPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const { me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const { data: agents, isLoading: agentsLoading } = useAgents();

  // 列表半边(列表 + 右键菜单 + rename/add-tag Dialog)已抽到 ConversationListPanel
  // (chat-page-split Ticket 2)。本组件只留 streaming 半边 + 编排。conversations/
  // customerProfiles 在这里仍需读:header 的「关联客户」归因 badge、composite mode
  // 跟随会话 kind 的 effect、CompositeMode 的 history 入参,都依赖这两份数据。
  const { data: conversations } = useConversations();

  // customerProfiles 留在 ChatPage:header 的 customer picker(新建会话归因)+ 归因
  // badge 显示都依赖它。Panel 内有它自己的一份(调 useCustomerProfiles);归因 badge
  // 的 customerNameOf 已抽共享 helper(Ticket 3),两边共用,行为零变化。
  const { data: customerProfiles } = useCustomerProfiles(!isSuperAdmin(me));

  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null);
  // Token 费用管理系列 3/4: optional customer attribution for a NEW chat.
  // Cleared whenever an existing conversation is selected (attribution is set
  // at creation time only — follow-up turns keep the original binding).
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");

  // composite-chat (priority 72), slice 04 — single/composite mode switch.
  // Defaults to "single" (AC4.6 / H5: preserves backward compat with the
  // existing SSE stream). The mode is a *conversation-level* transient state
  // (NOT an Agent attribute like is_orchestrator); an effect below syncs it to
  // the selected conversation's `kind` so opening a composite conversation
  // shows its history in the composite view. Switching to composite starts a
  // NEW composite query (selecting an existing single conversation while in
  // composite mode is reconciled by the same effect).
  const [mode, setMode] = useState<ConversationKind>("single");

  const { data: history, isLoading: historyLoading } = useMessages(
    selectedConversationId,
  );

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  // Local messages layered on top of (or instead of) the loaded history while
  // a reply is being streamed, so the assistant's text appears progressively.
  const [localMessages, setLocalMessages] = useState<Message[] | null>(null);

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

  // composite mode follows the selected conversation's kind (AC4.6): opening a
  // composite conversation renders its fragments via CompositeMode; opening a
  // single conversation (or starting fresh) falls back to the SSE stream view.
  // When no conversation is selected the user's last-chosen mode is kept, so a
  // "new chat" started from composite mode stays composite until toggled off.
  useEffect(() => {
    if (!selectedConversationId) return;
    const conv = conversations?.find((c) => c.id === selectedConversationId);
    if (conv?.kind) setMode(conv.kind);
  }, [selectedConversationId, conversations]);

  // Panel 的向上回调:用户点某个会话或「新建对话」时,清理 streaming 半边 state。
  // streaming 进行中时这些交互在 Panel 内已被 disabled 守卫拦截(行 button /
  // 「新建对话」按钮 / 行菜单 trigger 均 disabled={streaming}),这里无需再判。
  const selectConversation = (id: string) => {
    setSelectedConversationId(id);
    // Clear the customer picker — existing conversations keep their original
    // attribution; the picker only drives NEW conversations.
    setSelectedCustomerId("");
  };

  const startNewConversation = () => {
    setSelectedConversationId(null);
    setSelectedCustomerId("");
    setLocalMessages(null);
    setInput("");
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
    //
    // The list assembly (base shallow-copy + local user/assistant placeholders)
    // lives in `buildWorkingList` so it can be unit-tested in isolation
    // (chat-page-split Ticket 1). The streaming loop below mutates the trailing
    // assistant placeholder in place, so we keep a reference to it.
    const working = buildWorkingList(localMessages ?? history ?? [], text);
    const assistantMsg = working[working.length - 1];
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
      {/* ---- conversation list (抽到 ConversationListPanel, Ticket 2) ----
          Panel 自调会话管理 hooks;streaming/active 是只读 UI 状态(双栏联动),
          onSelectConversation/onStartNew 是向上通知回调。initialSearch 从 ?search=
          URL 播种,保留全局搜索框「查看全部」深链行为。 */}
      <ConversationListPanel
        streaming={streaming}
        activeConversationId={selectedConversationId}
        initialSearch={searchParams.get("search") ?? ""}
        onSelectConversation={selectConversation}
        onStartNew={startNewConversation}
      />

      {/* ---- chat panel ---- */}
      <Card className="flex h-[70vh] flex-col lg:h-[calc(100vh-12rem)] lg:order-2 order-1">
        {/* agent picker + header */}
        <CardHeader className="flex-row items-center justify-between space-y-0 border-b">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base">对话</CardTitle>
            {mode === "single" && (
              <>
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
              </>
            )}
            {mode === "composite" && (
              <span className="rounded-md bg-accent px-2 py-1 text-xs text-muted-foreground">
                复合查询:并行问多个智能体，综合答案
              </span>
            )}
            {/* When viewing an existing conversation that's attributed to a
                customer, show a read-only badge so the staff member knows who
                they're serving in this chat. customerNameOf is the shared
                helper (Ticket 3 / plan D7); pass this ChatPage's loaded
                customerProfiles so the lookup is self-contained. */}
            {!isSuperAdmin(me) && selectedConversationId && (() => {
              const conv = conversations?.find(
                (c) => c.id === selectedConversationId,
              );
              const cname = customerNameOf(conv?.customer_id, customerProfiles);
              return cname ? (
                <span className="flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs">
                  <User className="h-3 w-3" />
                  {cname}
                </span>
              ) : null;
            })()}
          </div>
          <div className="flex items-center gap-3">
            {/* composite-chat (priority 72): single ↔ composite mode switch.
                Reuses the same Switch component as agents-page's orchestrator
                toggle, but this is conversation-level (not an Agent field). */}
            <Label className="text-xs text-muted-foreground">单智能体</Label>
            <Switch
              checked={mode === "composite"}
              onCheckedChange={(v) => {
                // Toggling to composite while a single conversation is open
                // would mismatch the view; drop the selection so the compose
                // form starts fresh (mirrors startNewConversation).
                if (v && mode === "single" && selectedConversationId) {
                  setSelectedConversationId(null);
                  setLocalMessages(null);
                }
                setMode(v ? "composite" : "single");
              }}
              disabled={streaming}
              aria-label="切换复合查询模式"
            />
            <Label className="text-xs text-muted-foreground">复合查询</Label>
            {selectedConversationId && (
              <span className="text-xs text-muted-foreground">
                {fmt(
                  conversations?.find((c) => c.id === selectedConversationId)
                    ?.updated_at ?? null,
                )}
              </span>
            )}
          </div>
        </CardHeader>

        {/* composite-chat (priority 72): composite mode renders its own panel
            (compose form + history with fragments); single mode keeps the
            existing SSE message stream + input below. */}
        {mode === "composite" ? (
          <CompositeMode
            agents={agents ?? []}
            selectedConversationId={selectedConversationId}
            history={history ?? []}
            selectedCustomerId={selectedCustomerId}
            onConversationCreated={(id) => {
              setSelectedConversationId(id);
              setSelectedCustomerId("");
            }}
            onRefreshConversations={() =>
              qc.invalidateQueries({ queryKey: ["conversations"] })
            }
          />
        ) : (
        <>
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
                <motion.div
                  key={msg.id}
                  data-testid={isAssistant ? "assistant-message" : "user-message"}
                  // Stagger each message in by 30ms (motion use-case #1, revamp
                  // plan §7). ``initial`` only runs on mount, so this is a one-
                  // time entrance — not a re-animation on every stream delta.
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, delay: Math.min(idx * 0.03, 0.3) }}
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
                        // Typing indicator — three pulsing dots while the
                        // assistant placeholder is still empty (before the
                        // first delta arrives). Pure CSS, no motion dep.
                        <span className="inline-flex items-center gap-1">
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s] [animation-duration:0.8s]" />
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s] [animation-duration:0.8s]" />
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-duration:0.8s]" />
                        </span>
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
                </motion.div>
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
        </>
        )}
      </Card>

    </div>
  );
}
