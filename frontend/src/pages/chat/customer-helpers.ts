// chat/ customer-helpers.ts —— 会话归因「客户 → 显示名」的共享纯函数。
//
// plan-chat-page-split §4.0 D7 + §4.5:Ticket 3 把原先 chat-page 头部归因 badge 与
// ConversationListPanel 列表归因各留一份的本地 helper 抽成共享纯函数。两边
// (chat-page header + Panel 列表项)都调本函数。
//
// 真纯函数:把 customerProfiles 作为参数传入(不依赖任何 React state/hook),可直接
// 单测。签名 (cid, profiles) => name —— 找不到匹配的 profile 时回退 null(调用方据此
// 决定是否渲染 badge)。
import type { CustomerProfileRead } from "@/api/types";

/**
 * Look up a customer's display name by their customer_id, for attribution
 * badges in the conversation header and list items. Returns `null` when the id
 * is empty or no matching profile is loaded yet (caller hides the badge).
 *
 * @param cid     - conversation.customer_id (may be null/undefined)
 * @param profiles - the useCustomerProfiles result (undefined while loading)
 */
export function customerNameOf(
  cid: string | null | undefined,
  profiles: CustomerProfileRead[] | undefined,
): string | null {
  if (!cid) return null;
  const p = profiles?.find((x) => x.customer_id === cid);
  return p?.customer.name ?? null;
}
