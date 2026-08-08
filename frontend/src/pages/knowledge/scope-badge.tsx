/**
 * knowledge/ scope-badge — scope 来源实心徽章(reader-ui slice 01 G3)。
 *
 * 把 DocumentRead.scope / KnowledgeCategoryRead.scope 的三态映射到实心 Badge
 * variant,让门店 owner 一眼区分知识来源:
 *   platform → destructive(实心红)= 平台下发
 *   group    → warning(实心琉)= 集团下发
 *   store    → success(实心绿)= 本店自建
 *
 * 与状态徽章(dot-success / dot-warning / dot-destructive,见 shared.tsx statusBadge)
 * 语义分层不混淆:scope 用实心块(整块色),状态用 dot(点 + 文字)。用户看到
 * 实心红块 = 平台来源,看到红点 = 索引失败。
 *
 * ⚠️ 偏离用户原话「平台🔴」的字面:destructive 在系统语义 = 失败/危险。本决策
 * 用 destructive 表 platform 是因为它是现有 badge 变体里唯一的红色实心选项,且
 * 通过「实心 vs dot」的视觉分层避开了与状态徽章的语义冲突。对齐 design-system
 * semantic token,**不硬编码色**(见 plan §4.5 G3 footnote)。
 */
import { Badge } from "@/components/ui/badge";
import type { KnowledgeScope } from "@/api/types";

// scope → 实心 variant 映射。集中一处,document-list 卡片 + 任何需要展示来源的
// 地方都从这里取,避免散落硬编码。slice 02 category-tree 落地时如需复用,再从这里
// 导出(不预导出 —— 避免为还不存在的 consumer 提前抽象)。
const SCOPE_VARIANT: Record<
  KnowledgeScope,
  "destructive" | "warning" | "success"
> = {
  platform: "destructive",
  group: "warning",
  store: "success",
};

// scope → 中文短标签(徽章上显示的文字)。导出供 document-form 的 scope Select 复用
// (admin-ui slice 02:同一份 scope→中文映射,避免第二份字典扩散)。
export const SCOPE_LABEL: Record<KnowledgeScope, string> = {
  platform: "平台",
  group: "集团",
  store: "本店",
};

// scope 固定渲染顺序(platform → group → store)。导出供 category-tree /
// category-manager 共用(避免第二份顺序常量扩散 —— admin-ui slice 04 code-review 修复)。
export const SCOPE_ORDER: KnowledgeScope[] = ["platform", "group", "store"];

export function ScopeBadge({ scope }: { scope: KnowledgeScope }) {
  return <Badge variant={SCOPE_VARIANT[scope]}>{SCOPE_LABEL[scope]}</Badge>;
}
