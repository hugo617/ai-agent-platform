/**
 * queries/search — global cross-entity search (priority 51).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  globalSearch,
} from "@/api/endpoints";
import { useEffect, useState } from "react";
// ---------- global cross-entity search (priority 51) ----------

/**
 * Delay mirroring a value until the user stops changing it for `delay` ms.
 *
 * Used by `useGlobalSearch` to avoid firing a cross-entity search on every
 * keystroke. Generic so other live-search inputs can reuse it later.
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/**
 * Cross-entity search hook for the top-bar search box.
 *
 * Debounces the raw query (300ms), then fires GET /search only when the
 * debounced term is at least 2 chars (the backend's minimum). Below that the
 * query is disabled so no request leaves the browser — matching the empty-
 * result guard on the server side.
 */
export function useGlobalSearch(q: string, limitPerType = 5) {
  const term = q.trim();
  const debounced = useDebouncedValue(term, 300);
  const enabled = debounced.length >= 2;
  return useQuery({
    queryKey: qk.globalSearch(debounced, limitPerType),
    queryFn: () => globalSearch(debounced, limitPerType),
    enabled,
    placeholderData: (prev) => prev, // keep the prior dropdown stable while typing
  });
}

