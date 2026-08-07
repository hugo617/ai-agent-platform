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
  createDocument,
  deleteDocument,
  fetchDocuments,
  fetchKnowledgeCategories,
  type DocumentListFilter,
} from "@/api/endpoints";
import type {
  DocumentCreate,
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

