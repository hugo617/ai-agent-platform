/**
 * queries/knowledge — knowledge base / RAG (priority 57).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  createDocument,
  deleteDocument,
  fetchDocuments,
} from "@/api/endpoints";
import type {
  DocumentCreate,
} from "@/api/types";
// ---------- knowledge base / RAG (priority 57) ----------
export function useDocuments() {
  return useQuery({
    queryKey: qk.documents,
    queryFn: fetchDocuments,
  });
}

export function useCreateDocument() {
  return useApiMutation(
    (payload: DocumentCreate) => createDocument(payload),
    [qk.documents],
  );
}

export function useDeleteDocument() {
  return useApiMutation((id: string) => deleteDocument(id), [qk.documents]);
}

