/**
 * queries/knowledge — knowledge base / RAG (priority 57).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 *
 * knowledge-tiered reader-ui slice 01 G6 — ``useDocuments`` accepts the
 * optional {scope, category_id} filter and forwards it to fetchDocuments;
 * the query key encodes the filter so each distinct filter caches
 * independently. New ``useKnowledgeCategories`` powers the left-pane
 * category-tree (slice 02).
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  createCategory,
  createDocument,
  deleteCategory,
  deleteDocument,
  distributeDocument,
  fetchDocuments,
  fetchKnowledgeCategories,
  listDistributions,
  revokeDistribution,
  updateCategory,
  type DocumentListFilter,
} from "@/api/endpoints";
import type {
  DistributeRequest,
  DocumentCreate,
  KnowledgeCategoryCreate,
  KnowledgeCategoryUpdate,
} from "@/api/types";
// ---------- knowledge base / RAG (priority 57) ----------
// knowledge-tiered reader-ui slice 01 G6: filter forwarded to fetchDocuments;
// query key encodes the filter so each distinct (scope, category_id) cell
// caches independently (mirrors qk.conversations' filter-encoding pattern).
export function useDocuments(filter?: DocumentListFilter) {
  return useQuery({
    queryKey: qk.documents(filter),
    queryFn: () => fetchDocuments(filter),
  });
}

// knowledge-tiered reader-ui slice 01 G6 — categories for the left-pane tree.
export function useKnowledgeCategories() {
  return useQuery({
    queryKey: qk.knowledgeCategories,
    queryFn: fetchKnowledgeCategories,
  });
}

export function useCreateDocument() {
  return useApiMutation(
    (payload: DocumentCreate) => createDocument(payload),
    [qk.documents()],
  );
}

export function useDeleteDocument() {
  return useApiMutation((id: string) => deleteDocument(id), [qk.documents()]);
}

// ---------- distributions (admin-ui slice 02 / backend slice 03) ----------
// knowledge-tiered admin-ui:下发/撤回/list hooks。useDistributions 按 docId 缓存;
// 下发/撤回成功后失效该 doc 的 distribution 列表 + 文档列表(下发不新增文档,但撤回
// 影响门店侧可见性,保守失效 documents 一并刷新)。

/** 列出某文档的所有下发关系(含已撤回 is_active=false)。供「管理下发」视图。 */
export function useDistributions(docId: string) {
  return useQuery({
    queryKey: qk.documentDistributions(docId),
    queryFn: () => listDistributions(docId),
  });
}

/** 下发文档到指定门店(target_tenant_ids)或整个集团(target_group_id),XOR。 */
export function useDistributeDocument(docId: string) {
  return useApiMutation(
    (payload: DistributeRequest) => distributeDocument(docId, payload),
    [qk.documentDistributions(docId)],
  );
}

/** 撤回一条下发(软删 is_active=false)。失效该 doc 的 distribution 列表。 */
export function useRevokeDistribution(docId: string) {
  return useApiMutation(
    (distId: string) => revokeDistribution(distId),
    [qk.documentDistributions(docId)],
  );
}

// ---------- categories CRUD (admin-ui slice 04,先落 hook) ----------
// knowledge-tiered admin-ui:Category write hooks。成功后失效 categories 列表。

/** 新建本级 Category(scope 按 role 校验在后端 service 层)。 */
export function useCreateCategory() {
  return useApiMutation(
    (payload: KnowledgeCategoryCreate) => createCategory(payload),
    [qk.knowledgeCategories],
  );
}

/** 改 Category 的 name/sort_order(scope 不可改,对齐后端 KnowledgeCategoryUpdate)。 */
export function useUpdateCategory() {
  return useApiMutation(
    ({ id, payload }: { id: string; payload: KnowledgeCategoryUpdate }) =>
      updateCategory(id, payload),
    [qk.knowledgeCategories],
  );
}

/** 软删 Category(name 释放可复用)。 */
export function useDeleteCategory() {
  return useApiMutation(
    (id: string) => deleteCategory(id),
    [qk.knowledgeCategories],
  );
}

