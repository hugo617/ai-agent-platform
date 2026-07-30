/**
 * endpoints/ core — placeholder for future shared cross-domain helpers.
 *
 * Extracted from the original endpoints.ts monolith
 * (plan-queries-endpoints-domain-split.md). Pure locality move: zero behaviour
 * change.
 *
 * Unlike queries/core.ts (which holds the qk factory + useApiMutation that
 * every domain consumes), endpoints have no equivalent shared logic — each
 * domain imports its client helpers directly from "../client" and its types
 * from "../types". This file is intentionally minimal (no re-exports) to avoid
 * expanding the @/api/endpoints public surface: the original monolith only
 * *imported* api/apiErrorMessage/etc from ./client, it never re-exported them,
 * and we preserve that boundary. (code-review Standards axis: the earlier
 * `export {...}` here was dead code — no domain file consumed it via ./core,
 * all 30 use "../client" directly — so it was removed.)
 *
 * The ``endpoints.ts`` barrel re-exports every domain file's public surface so
 * ``@/api/endpoints`` callers are unchanged.
 */
export {};
