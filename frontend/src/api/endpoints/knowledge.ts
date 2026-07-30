/**
 * endpoints/knowledge — knowledge base / RAG (priority 57).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  DocumentCreate,
  DocumentRead,
  RetrieveResult,
} from "../types";
// ---------- knowledge base / RAG (priority 57) ----------
export async function fetchDocuments(): Promise<DocumentRead[]> {
  const { data } = await api.get<DocumentRead[]>("/knowledge/documents");
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

