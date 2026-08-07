/**
 * knowledge/ shared.tsx — 共享显示原语(reader-ui slice 01)。
 *
 * 从旧 ``knowledge-page.tsx`` 抽出 ``statusBadge``(零逻辑变化,纯 locality
 * move)—— 新 DocumentList 卡片与未来的 CRUD 迁移(切片 03)都从这里取,避免
 * statusBadge 在多处重复声明。镜像 ``devices/shared.tsx`` 的「显示原语集中一处」
 * 范式。
 *
 * 与 ``scope-badge.tsx`` 的分层(plan §4.5 G3):
 *   - statusBadge → dot variant(点 + 文字):indexed/pending/failed 索引流水线状态
 *   - ScopeBadge  → 实心 variant(整块色):platform/group/store 来源
 * 两套语义不混淆 —— 用户看到实心红块 = 平台来源,看到红点 = 索引失败。
 */
import { Badge } from "@/components/ui/badge";

/** Badge for the embedding-pipeline status shown in the list. Uses the dot
 *  variants so the status reads at a glance: green dot = indexed, amber dot =
 *  pending, red dot = failed. Mirrors the pre-slice-01 helper from
 *  knowledge-page.tsx (zero behaviour change — pure locality move). */
export function statusBadge(status: string) {
  if (status === "indexed")
    return <Badge variant="dot-success">已索引</Badge>;
  if (status === "failed")
    return <Badge variant="dot-destructive">索引失败</Badge>;
  return <Badge variant="dot-warning">待处理</Badge>;
}
