/**
 * endpoints/knowledge — knowledge base / RAG (priority 57).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 *
 * knowledge-tiered reader-ui slice 01 G6 — ``fetchDocuments`` gains an optional
 * ``{scope?, category_id?}`` filter (passed as query string) and a new
 * ``fetchKnowledgeCategories`` for the category-tree. The current backend
 * ``GET /knowledge/documents`` filters by role context and ignores unknown
 * query params, so the filter is forward-paving: the type layer + query
 * construction are landed now so slice 02's category-tree click → list filter
 * is a pure state change (the msw integration test in
 * __tests__/knowledge-api.test.tsx locks the request-construction contract).
 */
import {
  api,
} from "../client";
import type {
  DocumentCreate,
  DocumentRead,
  DistributeRequest,
  KnowledgeCategoryCreate,
  KnowledgeCategoryRead,
  KnowledgeCategoryUpdate,
  KnowledgeDistributionRead,
  KnowledgeScope,
  RetrieveResult,
} from "../types";
// ---------- knowledge base / RAG (priority 57) ----------
// Optional list filter (knowledge-tiered reader-ui slice 01). Both fields
// optional — ``scope`` selects one tier (platform/group/store), ``category_id``
// narrows to one category within that tier. Omitted = return everything the
// caller's role can see (the backend applies its own role-based filter).
export interface DocumentListFilter {
  scope?: KnowledgeScope;
  category_id?: string;
}

export async function fetchDocuments(
  filter?: DocumentListFilter,
): Promise<DocumentRead[]> {
  // Pass only the set fields as query params — axios drops ``undefined``
  // values, so an empty filter produces a bare GET (matches the pre-slice-01
  // call shape exactly, no behaviour change for existing useDocuments() callers).
  const { data } = await api.get<DocumentRead[]>("/knowledge/documents", {
    params: {
      scope: filter?.scope,
      category_id: filter?.category_id,
    },
  });
  return data;
}

// knowledge-tiered reader-ui slice 01 G6 — categories for the left-pane tree.
// Read is open to any authenticated user with knowledge:read; the backend
// returns the categories visible to the caller's role (platform + own group +
// own store), so the tree renders whatever the caller is allowed to see.
export async function fetchKnowledgeCategories(): Promise<
  KnowledgeCategoryRead[]
> {
  const { data } = await api.get<KnowledgeCategoryRead[]>(
    "/knowledge/categories",
  );
  return data;
}

export async function createDocument(
  payload: DocumentCreate
): Promise<DocumentRead> {
  const { data } = await api.post<DocumentRead>("/knowledge/documents", payload);
  return data;
}

export async function deleteDocument(id: string): Promise<void> {
  await api.delete(`/knowledge/documents/${id}`);
}

export async function retrieveKnowledge(
  query: string,
  topK = 4
): Promise<RetrieveResult> {
  const { data } = await api.post<RetrieveResult>("/knowledge/retrieve", {
    query,
    top_k: topK,
  });
  return data;
}

// ---------- distributions (admin-ui slice 02 / backend slice 03) ----------
// knowledge-tiered admin-ui:下发/撤回/list 三端点。backend feature 切片03 已交付
// POST(下发)+ DELETE(撤回);本 feature 切片01 补了 GET list(看已下发 + 撤回入口)。
// distribute payload 是 XOR(target_tenant_ids 与 target_group_id 二选一),后端
// service 层 BizError→400 兜底,前端 distribute-dialog 也做 XOR 构造。

/** POST /knowledge/documents/{docId}/distribute — 下发到指定门店或整个集团。 */
export async function distributeDocument(
  docId: string,
  payload: DistributeRequest,
): Promise<KnowledgeDistributionRead[]> {
  const { data } = await api.post<KnowledgeDistributionRead[]>(
    `/knowledge/documents/${docId}/distribute`,
    payload,
  );
  return data;
}

/** DELETE /knowledge/distributions/{distId} — 撤回一条下发(软删,is_active=false)。 */
export async function revokeDistribution(distId: string): Promise<void> {
  await api.delete(`/knowledge/distributions/${distId}`);
}

/** GET /knowledge/documents/{docId}/distributions — 列出某文档的所有下发关系
 *  (含已撤回 is_active=false,供「管理下发」视图区分生效/已撤回)。 */
export async function listDistributions(
  docId: string,
): Promise<KnowledgeDistributionRead[]> {
  const { data } = await api.get<KnowledgeDistributionRead[]>(
    `/knowledge/documents/${docId}/distributions`,
  );
  return data;
}

// ---------- categories CRUD (admin-ui slice 04,先落 endpoint) ----------
// backend feature 切片01 已交付 GET/POST/PUT/DELETE /knowledge/categories。
// GET 已在 fetchKnowledgeCategories 落地(reader-ui slice 01);这里补 write 三端点。

/** POST /knowledge/categories — 新建本级 Category(scope 按 role 校验在后端)。 */
export async function createCategory(
  payload: KnowledgeCategoryCreate,
): Promise<KnowledgeCategoryRead> {
  const { data } = await api.post<KnowledgeCategoryRead>(
    "/knowledge/categories",
    payload,
  );
  return data;
}

/** PUT /knowledge/categories/{id} — 改 name/sort_order(scope 不可改)。 */
export async function updateCategory(
  id: string,
  payload: KnowledgeCategoryUpdate,
): Promise<KnowledgeCategoryRead> {
  const { data } = await api.put<KnowledgeCategoryRead>(
    `/knowledge/categories/${id}`,
    payload,
  );
  return data;
}

/** DELETE /knowledge/categories/{id} — 软删 Category(name 释放可复用)。 */
export async function deleteCategory(id: string): Promise<void> {
  await api.delete(`/knowledge/categories/${id}`);
}

