/**
 * composite-mode.tsx — the "composite query" panel for the chat page.
 *
 * composite-chat (priority 72), slice 04. Composite = fan-out + synthesize:
 * pick N agents, ask one question, get one synthesized answer plus each
 * agent's reply collapsed underneath. Contrast with the single-agent SSE
 * stream in chat-page.tsx and with Supervisor (priority 58), which routes to
 * ONE specialist.
 *
 * Boundary (plan H6 / AC4.5): chat-page owns ONLY the `mode` switch + this
 * component's conditional render. Everything composite-specific — agent
 * multi-select, the request, loading, synthesis + fragments rendering — lives
 * here. The request is a plain JSON POST (non-streaming); the synthesis is a
 * single payload, so there's no typewriter effect (unlike /chat/stream).
 *
 * Two views (plan M10 — MVP "view history only", no follow-up turns):
 *  - No selectedConversationId → the "compose" view: multi-select agents +
 *    input + 发起 button → loading → live result (synthesis + fragments).
 *  - selectedConversationId set → the "history" view: render that composite
 *    conversation's stored messages (the assistant turns carry `fragments`),
 *    read-only. Starting a brand-new composite query requires "新建对话" first.
 *
 * 402 handling (AC4.8, project's first real HTTP 402): the backend rejects a
 * composite turn when the wallet can't cover the N+1 token cost (strict, unlike
 * /chat/stream's "no wallet = let it through" SSE error frame). We catch
 * `CompositeInsufficientBalanceError` specifically and show a recharge prompt
 * instead of a generic error toast.
 */
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Layers, Send, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { MarkdownView } from "@/components/chat/markdown-view";
import {
  CompositeInsufficientBalanceError,
  compositeChat,
} from "@/api/endpoints";
import { apiErrorMessage } from "@/api/client";
import type { Agent, CompositeResponse, Message } from "@/api/types";

export interface CompositeModeProps {
  /** All agents in this tenant. CompositeMode filters out orchestrators
   * internally (orchestrators are a different routing model — Supervisor —
   * and don't belong in a fan-out set), so chat-page can pass its full
   * `agents` list without a pre-filter step (keeps chat-page's net-line count
   * bounded — plan AC4.5). */
  agents: Agent[];
  /** The currently-selected conversation id, or null for "new composite". */
  selectedConversationId: string | null;
  /** Stored messages for the selected conversation (assistant turns may carry
   * `fragments`). Empty when nothing is selected. */
  history: Message[];
  /** Customer attribution for a NEW composite conversation (store staff
   * serving a customer). Cleared by chat-page once a conversation exists. */
  selectedCustomerId: string;
  /** Called after the first turn creates a composite conversation, so chat-page
   * selects it (subsequent renders show the history view). */
  onConversationCreated: (id: string) => void;
  /** Invalidate the conversation list (a new conversation may have appeared). */
  onRefreshConversations: () => void;
}

export function CompositeMode({
  agents,
  selectedConversationId,
  history,
  selectedCustomerId,
  onConversationCreated,
  onRefreshConversations,
}: CompositeModeProps) {
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();

  // Filter orchestrators once per render: a Supervisor (priority 58) routes to
  // ONE specialist and has no first-class answer of its own, so it doesn't
  // belong in a fan-out set asked the same question in parallel. Done here
  // (not in chat-page) so chat-page passes its full agents list untouched.
  const compositeAgents = useMemo(
    () => agents.filter((a) => !a.is_orchestrator),
    [agents],
  );

  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(
    new Set(),
  );
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Live result from the most recent compositeChat call. Only populated in the
  // "compose" view (no selectedConversationId) between the response arriving
  // and the conversation list refetch selecting the new conversation.
  const [result, setResult] = useState<CompositeResponse | null>(null);
  // AC4.8 — project's first real HTTP 402. Rather than a bare error toast,
  // we surface a dedicated "insufficient balance" panel with a recharge CTA
  // (a plain toast can't carry an action button). Cleared on the next attempt
  // and on selection change.
  const [balanceError, setBalanceError] = useState<string | null>(null);
  // Which fragment is expanded in either the live result or history. Keyed by
  // `${agent_id}:${index}` (index disambiguates if the same agent appears twice
  // — the backend de-dupes, but this is robust regardless).
  const [expanded, setExpanded] = useState<string | null>(null);

  // Reset local compose state whenever the selection changes: switching from
  // "new" → an existing conversation (or back) should not carry over a stale
  // half-typed query or a stale live result.
  useEffect(() => {
    setResult(null);
    setInput("");
    setExpanded(null);
    setBalanceError(null);
  }, [selectedConversationId]);

  const toggleAgent = (id: string) => {
    setSelectedAgentIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    if (selectedAgentIds.size === 0) {
      toast.error("请至少选择一个智能体");
      return;
    }
    // Once a composite conversation exists, follow-up turns are out of MVP
    // scope (plan M10) — the user should start a fresh "新建对话" to ask again.
    if (selectedConversationId) {
      toast.error("复合会话暂不支持续问，请新建对话发起下一次复合查询");
      return;
    }

    setInput("");
    setLoading(true);
    setBalanceError(null); // clear any prior 402 prompt before retrying
    try {
      const resp = await compositeChat({
        agent_ids: Array.from(selectedAgentIds),
        message: text,
        customer_id: selectedCustomerId || undefined,
      });
      setResult(resp);
      onConversationCreated(resp.conversation_id);
      // Refresh the left-hand list so the new composite conversation appears,
      // and bust the messages cache so re-selecting shows server-persisted data.
      onRefreshConversations();
      qc.invalidateQueries({ queryKey: ["messages", resp.conversation_id] });
    } catch (err) {
      if (err instanceof CompositeInsufficientBalanceError) {
        // AC4.8 — project's first 402: show a recharge prompt (not a bare
        // toast). The message carries the backend's detail; the inline panel
        // below offers a CTA to the wallet page.
        setBalanceError(err.message);
      } else {
        toast.error("复合查询失败", apiErrorMessage(err));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ---- compose view (no conversation selected yet) ----
  if (!selectedConversationId) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-medium">选择参与的智能体</h3>
              <span className="text-xs text-muted-foreground">
                已选 {selectedAgentIds.size} 个(并行询问全部，再综合答案)
              </span>
            </div>
            {compositeAgents.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                本租户暂无可用的非编排器智能体。请先在「智能体」页创建。
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {compositeAgents.map((agent) => {
                  const checked = selectedAgentIds.has(agent.id);
                  return (
                    <label
                      key={agent.id}
                      className={`flex cursor-pointer items-start gap-2 rounded-md border p-2.5 text-sm transition-colors ${
                        checked
                          ? "border-primary bg-accent"
                          : "hover:bg-accent/50"
                      }`}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={() => toggleAgent(agent.id)}
                        className="mt-0.5"
                      />
                      <span className="flex flex-col">
                        <span className="font-medium">{agent.name}</span>
                        {agent.description && (
                          <span className="text-xs text-muted-foreground line-clamp-2">
                            {agent.description}
                          </span>
                        )}
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
          </section>

          {/* AC4.8 — 402 recharge prompt (project's first real HTTP 402).
              Composite's N+1 token cost is billed strictly, so a low wallet
              rejects the whole turn; surface a dedicated panel with a CTA
              rather than a bare error toast.
              切片 05 WCAG 收口:大面积警告框保留 bg-warning/10 浅橙底(语义),
              icon + 标题从 text-warning(亮色 2.13 < AA)改 text-foreground
              (亮 18.39 / 暗 16.73 双模式 AA)。正文 muted-foreground 达标不动。 */}
          {!loading && balanceError && (
            <div className="flex items-start gap-3 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm">
              <Wallet className="mt-0.5 h-4 w-4 shrink-0 text-foreground" />
              <div className="flex-1 space-y-1">
                <p className="font-medium text-foreground">余额不足，无法发起复合查询</p>
                <p className="text-xs text-muted-foreground">{balanceError}</p>
                <p className="text-xs text-muted-foreground">
                  复合查询会并行询问全部所选智能体(N+1 倍 token 成本)，需要钱包有足额余额。
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate("/billing")}
              >
                前往充值
              </Button>
            </div>
          )}

          {/* live result (synthesis + fragments) — shown after a response */}
          {loading && <CompositeResultSkeleton />}
          {!loading && result && (
            <CompositeResultView
              result={result}
              expanded={expanded}
              setExpanded={setExpanded}
            />
          )}
          {!loading && !result && selectedAgentIds.size > 0 && (
            <p className="text-center text-xs text-muted-foreground">
              选好智能体后，在下方输入问题并发起复合查询。
            </p>
          )}
        </div>

        {/* input */}
        <CardContent className="border-t p-4">
          <div className="flex items-end gap-2">
            <textarea
              className="flex min-h-[40px] max-h-32 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="输入要并行询问全部智能体的问题…(Enter 发送，Shift+Enter 换行)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              disabled={loading}
              rows={1}
              data-testid="composite-message-input"
            />
            <Button
              onClick={handleSend}
              disabled={loading || !input.trim() || selectedAgentIds.size === 0}
              size="icon"
              title="发起复合查询"
              data-testid="composite-send-btn"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </div>
    );
  }

  // ---- history view (an existing composite conversation is selected) ----
  // Read-only: render stored messages. Assistant turns carry `fragments`; user
  // turns render as plain text. No compose UI here (plan M10: MVP no follow-up).
  if (history.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
        <Layers className="h-8 w-8" />
        <p>该复合会话暂无消息</p>
      </div>
    );
  }
  return (
    <div className="flex-1 space-y-4 overflow-y-auto p-6">
      {history.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === "assistant" ? "justify-start" : "justify-end"}`}
        >
          <div
            className={`max-w-[90%] overflow-hidden rounded-lg px-4 py-2 text-sm ${
              msg.role === "assistant"
                ? "bg-muted"
                : "bg-primary text-primary-foreground"
            }`}
          >
            {msg.role === "assistant" ? (
              <div className="space-y-3">
                {msg.content && (
                  <div className="overflow-x-auto">
                    <MarkdownView content={msg.content} />
                  </div>
                )}
                {msg.fragments && msg.fragments.length > 0 && (
                  <FragmentsList
                    fragments={msg.fragments}
                    expanded={expanded}
                    setExpanded={setExpanded}
                  />
                )}
                {msg.status === "failed" && (
                  <p className="text-xs text-destructive">
                    {msg.error ?? "本轮综合失败"}
                  </p>
                )}
              </div>
            ) : (
              <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                {msg.content}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---- sub-components (kept in this file: composite-only, no other consumer) ----

/** A live CompositeResponse rendered as the synthesis + collapsible fragments. */
function CompositeResultView({
  result,
  expanded,
  setExpanded,
}: {
  result: CompositeResponse;
  expanded: string | null;
  setExpanded: (id: string | null) => void;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Badge variant="dot-success">综合答案</Badge>
      </div>
      <div className="overflow-x-auto rounded-lg bg-muted p-4">
        <MarkdownView content={result.synthesis} />
      </div>
      <FragmentsList
        fragments={result.fragments}
        expanded={expanded}
        setExpanded={setExpanded}
      />
    </section>
  );
}

/** Collapsible list of per-agent fragments, each with a status badge. */
function FragmentsList({
  fragments,
  expanded,
  setExpanded,
}: {
  fragments: NonNullable<Message["fragments"]>;
  expanded: string | null;
  setExpanded: (id: string | null) => void;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">
        各智能体原始回答({fragments.length})
      </p>
      {fragments.map((frag, idx) => {
        const key = `${frag.agent_id}:${idx}`;
        const isOpen = expanded === key;
        const ok = frag.status === "completed";
        return (
          <div key={key} className="rounded-md border">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-accent/50"
              onClick={() => setExpanded(isOpen ? null : key)}
              aria-expanded={isOpen}
            >
              <span className="flex items-center gap-2 truncate">
                <span className="truncate font-medium">{frag.agent_name}</span>
                {frag.total_tokens != null && (
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {frag.total_tokens} tokens
                  </span>
                )}
              </span>
              <Badge variant={ok ? "success" : "destructive"}>
                {ok ? "✓ 完成" : "✗ 失败"}
              </Badge>
            </button>
            {isOpen && (
              <div className="border-t px-3 py-2 text-sm">
                {ok ? (
                  <div className="overflow-x-auto">
                    <MarkdownView content={frag.snippet} />
                  </div>
                ) : (
                  <p className="text-destructive">
                    {frag.error ?? "该智能体本轮失败"}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Loading skeleton for an in-flight composite response. */
function CompositeResultSkeleton() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <div className="space-y-2 rounded-lg bg-muted p-4">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
      <div className="space-y-1.5">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-10 w-full rounded-md" />
        <Skeleton className="h-10 w-full rounded-md" />
      </div>
    </div>
  );
}
