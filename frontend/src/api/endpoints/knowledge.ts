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
  KnowledgeCategoryRead,
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

