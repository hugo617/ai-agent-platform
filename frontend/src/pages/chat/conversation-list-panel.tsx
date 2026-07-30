// ConversationListPanel —— 从 chat-page.tsx 抽出的「会话列表」半边。
// (chat-page-split Ticket 2, migrate 阶段。chat-page.tsx 本切片不移动。)
//
// 范式对齐 bookings/store-view(plan D2):Panel 自调 @/hooks/queries 的会话管理
// hooks(useConversations / useDeleteConversation / useRenameConversation /
// useAddConversationTag / useRemoveConversationTag / useSetConversationPinned /
// useSetConversationStarred / useBatchDeleteConversations / useCustomerProfiles),
// 列表渲染 + 右键菜单 + rename/add-tag 两个 Dialog + 4 个 dialog state +
// selectedIds + searchInput + searchCommitted + debounce effect + 清空 effect +
// conversationLabel helper 全部自含在 Panel 内部。
//
// 与 store-view 的差异(chat-page 特有):chat-page 是「列表 + 详情」双栏联动,
// streaming 半边由父层 ChatPage 拥有。因此本 Panel 不是 store-view 那样的「真零
// props」,而是接收 2 个向下只读 UI 状态 + 2 个向上通知回调(见 Props 注释)。
// 这是 plan §4.5「Panel 需通知父层」在双栏场景下的必要细化。
//
// 零行为变更约束:所有 handler 逻辑从 chat-page.tsx 原样搬迁,只改位置 + 把对父层
// state 的写改为回调通知。不引入 useMemo/useCallback(plan §4.5,与 store-view 的
// memo 习惯不同)。
import { useEffect, useState } from "react";
import {
  MessageSquare,
  MoreVertical,
  Pin,
  Plus,
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
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { apiErrorMessage } from "@/api/client";
import type { Conversation, Message } from "@/api/types";
import {
  useAddConversationTag,
  useBatchDeleteConversations,
  useConversations,
  useCustomerProfiles,
  useDeleteConversation,
  useRemoveConversationTag,
  useRenameConversation,
  useSetConversationPinned,
  useSetConversationStarred,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

interface ConversationListPanelProps {
  // ---- 向下:只读 UI 状态(streaming 半边拥有,Panel 只读)----
  // streaming 时禁用列表交互(新建/选择/删除/菜单),与原 chat-page 行为一致。
  streaming: boolean;
  // 当前选中的会话 id(用于 active 高亮 + 删除当前会话时判断是否要清理父层)。
  activeConversationId: string | null;
  // 列表搜索框的初始值。原 chat-page 从 ?search= URL 参数播种 searchInput/
  // searchCommitted(全局搜索框「查看全部」深链);URL 读取由父层 useSearchParams
  // 拥有,这里只接收值,保证深链行为不变。可选,默认 ""(不传即无初始词)。
  initialSearch?: string;
  // ---- 向上:通知回调(Panel 不持有 streaming 半边 state,通过这两个回调通知父层)----
  // 用户点某个会话时通知父层更新 selectedConversationId 等。
  onSelectConversation: (id: string) => void;
  // 「新建对话」按钮 + 删除当前选中会话后清理父层(语义:回到全新会话态)。
  // 复用同一个回调:删除当前会话后,父层的 selectedConversationId/localMessages
  // 都需清空,与「新建」等价(input 也一并清空 —— 会话已删,残留 input 无意义)。
  onStartNew: () => void;
}

/**
 * Pick a display label for a conversation: its title, or a snippet of the
 * first user message, or a fallback. (Backend may leave title null on first
 * turn; the list should still show something legible.)
 *
 * 本地 helper:只被本 Panel 的列表用,随 Panel 一起搬出 chat-page.tsx。
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

export function ConversationListPanel({
  streaming,
  activeConversationId,
  initialSearch = "",
  onSelectConversation,
  onStartNew,
}: ConversationListPanelProps) {
  const toast = useToast();
  const { me } = useAuth();

  // ---------------- conversation list state ----------------
  // 列表筛选:debounce 后的 searchCommitted 才驱动 query(每次按键不打请求)。
  // 从父层传入的 initialSearch(?search= URL 参数)播种,使全局搜索框「查看全部」
  // 深链能把词带进来 —— 行为与原 chat-page 一致(原代码 searchInput/searchCommitted
  // 都从 searchParams.get("search") 初始化)。
  const trimmedInitial = initialSearch.trim();
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [searchCommitted, setSearchCommitted] = useState<string | undefined>(
    trimmedInitial.length > 0 ? trimmedInitial : undefined,
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

  // 多选(批量操作)。仅当会话 id 集合变化(新增/删除)时清空,而非每次后台 refetch
  // 都清 —— 用 id-join(原始字符串)做依赖,避免 pin/star 切换只重排数组就清空选择。
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const conversationIdSet = conversations?.map((c) => c.id).join(",") ?? "";
  useEffect(() => {
    setSelectedIds(new Set());
  }, [conversationIdSet]);

  // 客户档案:列表里「关联客户」归因显示用。super_admin 不服务具体门店客户,
  // 关闭查询(端点允许 super_admin,但 picker 不显示,取了也无意义)。
  const { data: customerProfiles } = useCustomerProfiles(!isSuperAdmin(me));

  // mutations(自调,不经过父层)。
  const deleteConv = useDeleteConversation();
  const renameConv = useRenameConversation();
  const addTagMut = useAddConversationTag();
  const removeTagMut = useRemoveConversationTag();
  const pinMut = useSetConversationPinned();
  const starMut = useSetConversationStarred();
  const batchDeleteMut = useBatchDeleteConversations();

  // rename + add-tag dialog state(一次只开一个,挂在目标 conv 上)。
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [tagTarget, setTagTarget] = useState<Conversation | null>(null);
  const [tagValue, setTagValue] = useState("");

  // customer_id → 显示名,用于列表项的归因显示(找不到则回退 null 不显示)。
  // 注意:chat panel header 也有一份同款(plan D7 说 Ticket 3 才抽共享 helper,
  // 本切片两边各留一份,行为零变化)。
  const customerNameOf = (cid: string | null): string | null => {
    if (!cid) return null;
    const p = customerProfiles?.find((x) => x.customer_id === cid);
    return p?.customer.name ?? null;
  };

  // ---------------- handlers(原样搬迁,只改跨层写为回调通知)----------------
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
      // 若删掉的正是当前选中会话,通知父层清理(语义等同「新建」:回到全新会话态)。
      if (activeConversationId && ids.includes(activeConversationId)) {
        onStartNew();
      }
      toast.success(`已删除 ${res.deleted} 个会话`);
    } catch (err) {
      toast.error("批量删除失败", apiErrorMessage(err));
    }
  };

  const handleDeleteConversation = async (conv: Conversation) => {
    if (streaming) return;
    if (!confirm("确认删除这个会话？此操作不可撤销。")) return;
    try {
      await deleteConv.mutateAsync(conv.id);
      if (activeConversationId === conv.id) {
        onStartNew();
      }
      toast.success("已删除会话");
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
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

  return (
    <>
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
                onClick={onStartNew}
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
                const active = conv.id === activeConversationId;
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
                        onClick={() => onSelectConversation(conv.id)}
                        disabled={streaming}
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
                          {conv.kind === "composite" && (
                            <Badge
                              variant="secondary"
                              className="shrink-0 px-1.5 py-0 text-[10px]"
                            >
                              复合
                            </Badge>
                          )}
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
    </>
  );
}
