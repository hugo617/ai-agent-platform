/**
 * endpoints/ core — shared client + http helpers for all domain endpoint files.
 *
 * Extracted from the original endpoints.ts monolith
 * (plan-queries-endpoints-domain-split.md). Pure locality move: zero behaviour
 * change. Re-exports the api client helpers so domain files can import them
 * from "./core" (or directly from "../client"). The ``endpoints.ts`` barrel
 * re-exports everything so ``@/api/endpoints`` callers are unchanged.
 */
import { api, apiErrorMessage, getStoredToken, setStoredToken, AUTH_EXPIRED_EVENT } from "../client";

export { api, apiErrorMessage, getStoredToken, setStoredToken, AUTH_EXPIRED_EVENT };
