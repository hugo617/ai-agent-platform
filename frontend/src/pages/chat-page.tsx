import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus, Send, Trash2 } from "lucide-react";
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
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { sendChatStream } from "@/api/endpoints";
import {
  useAgents,
  useConversations,
  useDeleteConversation,
  useMessages,
} from "@/hooks/queries";
import { qk } from "@/hooks/queries";
import type { Conversation, Message } from "@/api/types";

const fmt = (s: string | null): string =>
  s ? new Date(s).toLocaleString() : "-";

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

  const { data: agents, isLoading: agentsLoading } = useAgents();
  const { data: conversations, isLoading: convsLoading } = useConversations();

  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null);

  const { data: history, isLoading: historyLoading } = useMessages(
    selectedConversationId,
  );
  const deleteConv = useDeleteConversation();

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  // Local messages layered on top of (or instead of) the loaded history while
  // a reply is being streamed, so the assistant's text appears progressively.
  const [localMessages, setLocalMessages] = useState<Message[] | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-select the first agent once the list loads.
  useEffect(() => {
    if (!selectedAgentId && agents && agents.length > 0) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId]);

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
    setLocalMessages(null);
    setInput("");
  };

  const selectConversation = (id: string) => {
    if (streaming) return;
    setSelectedConversationId(id);
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

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    if (!selectedAgentId) {
      toast.error("请先选择一个智能体");
      return;
    }

    setInput("");
    setStreaming(true);

    // Build the working message list: existing history + the user turn + an
    // empty assistant placeholder that we'll fill as deltas arrive.
    const base = (history ?? []).map((m) => ({ ...m }));
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
      toast.error("对话失败", apiErrorMessage(err));
    } finally {
      setStreaming(false);
      abortRef.current = null;
      // Refresh the conversation list (a new conversation may have been
      // created on first turn; the list now reflects updated_at ordering).
      qc.invalidateQueries({ queryKey: qk.conversations });
    }
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
      <Card className="h-[calc(100vh-12rem)] lg:order-1 order-2">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">会话</CardTitle>
          <Button
            variant="ghost"
            size="icon"
            onClick={startNewConversation}
            title="新建对话"
            disabled={streaming}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="overflow-y-auto p-2">
          {convsLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !conversations?.length ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <MessageSquare className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                还没有会话，发送消息开始对话
              </p>
            </div>
          ) : (
            <ul className="space-y-1">
              {conversations.map((conv) => {
                const active = conv.id === selectedConversationId;
                return (
                  <li key={conv.id}>
                    <div
                      className={`group flex items-center gap-1 rounded-md px-2 py-2 text-sm transition-colors ${
                        active
                          ? "bg-accent text-accent-foreground"
                          : "hover:bg-accent/50"
                      }`}
                    >
                      <button
                        className="flex-1 truncate text-left"
                        onClick={() => selectConversation(conv.id)}
                        title={conversationLabel(conv)}
                      >
                        {conversationLabel(conv)}
                      </button>
                      <button
                        className="opacity-0 transition-opacity group-hover:opacity-100"
                        title="删除会话"
                        disabled={streaming}
                        onClick={() => handleDeleteConversation(conv)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ---- chat panel ---- */}
      <Card className="flex h-[calc(100vh-12rem)] flex-col lg:order-2 order-1">
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
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  {msg.content || (
                    <span className="text-muted-foreground">…</span>
                  )}
                </div>
              </div>
            ))
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
            />
            <Button
              onClick={handleSend}
              disabled={streaming || !input.trim()}
              size="icon"
              title="发送"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
