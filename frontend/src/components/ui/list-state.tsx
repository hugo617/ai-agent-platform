import * as React from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiErrorMessage } from "@/api/client";

/**
 * Shared loading / empty / error state for list views.
 *
 * Replaces the per-page ``isLoading ? <加载中> : list.length === 0 ? <empty> :
 * <table>`` ternary JSX copy-pasted across 15+ cards. The error variant (with a
 * retry button) was duplicated verbatim in logs-page and notifications-page;
 * both now flow through this component.
 *
 * Render order: error → loading → empty → children. Pass ``isEmpty`` to flag
 * the empty case (usually ``list.length === 0``), and either ``emptyContent``
 * (custom JSX with an icon + message) or ``emptyText`` (plain string) for the
 * empty body. ``onRetry`` wires the retry button shown on error.
 *
 * Loading variants:
 *   - ``loadingVariant="text"`` (default): centered "加载中…" text.
 *   - ``loadingVariant="spinner"``: same but with a spinning Loader2 icon
 *     (equivalent to the legacy ``showSpinner`` prop, kept for back-compat).
 *   - ``loadingVariant="skeleton"``: renders ``skeletonRows`` pulsing rows that
 *     mimic a table — a short bar (avatar/name) + a wider bar (secondary text)
 *     per row. This is the "no flash of empty layout" pattern: the table's
 *     shape is visible while data loads, so the page doesn't jump on settle.
 *
 * The whole-page empty state (first-run / no-data-ever) is a different concern
 * from this list-area wrapper; that belongs in ``EmptyState`` (大插图 + CTA).
 * ``ListState`` is for the *table region*; ``EmptyState`` is for the *screen*.
 */
export function ListState({
  isLoading,
  isEmpty,
  isError,
  error,
  onRetry,
  emptyContent,
  emptyText = "暂无数据",
  loadingText = "加载中…",
  loadingVariant = "text",
  skeletonRows = 5,
  showSpinner = false,
  children,
}: {
  isLoading: boolean;
  isEmpty: boolean;
  isError?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Custom empty-state JSX (e.g. an icon + message). Takes precedence over emptyText. */
  emptyContent?: React.ReactNode;
  /** Plain-text empty state (used when emptyContent is absent). */
  emptyText?: string;
  loadingText?: string;
  /** How to render the loading state. ``skeleton`` mimics the table shape. */
  loadingVariant?: "text" | "spinner" | "skeleton";
  /** Number of skeleton rows when ``loadingVariant="skeleton"``. */
  skeletonRows?: number;
  /** Legacy: show a spinning Loader2 icon. Prefer ``loadingVariant="spinner"``. */
  showSpinner?: boolean;
  /** Success content — rendered when none of the above states apply. */
  children: React.ReactNode;
}) {
  if (isError) {
    return (
      <div className="py-8 text-center text-sm text-destructive">
        加载失败:{apiErrorMessage(error)}
        {onRetry && (
          <Button
            variant="outline"
            size="sm"
            className="ml-3"
            onClick={onRetry}
          >
            重试
          </Button>
        )}
      </div>
    );
  }
  if (isLoading) {
    if (loadingVariant === "skeleton") {
      // Mimic a table: each row has a short leading bar (name/avatar col) and
      // a wider trailing bar (the rest of the row). Wraps in the same vertical
      // rhythm as a real table so the layout doesn't shift on settle.
      return (
        <div className="space-y-3 py-2">
          {Array.from({ length: skeletonRows }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-1">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 flex-1 max-w-xs" />
              <Skeleton className="ml-auto h-4 w-20" />
            </div>
          ))}
        </div>
      );
    }
    if (loadingVariant === "spinner" || showSpinner) {
      return (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> {loadingText}
        </div>
      );
    }
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {loadingText}
      </div>
    );
  }
  if (isEmpty) {
    return emptyContent ?? (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {emptyText}
      </div>
    );
  }
  return <>{children}</>;
}
