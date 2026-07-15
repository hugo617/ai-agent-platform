import * as React from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  /** Show a spinning Loader2 icon before the loading text (logs/notifications style). */
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
    if (showSpinner) {
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
    return emptyContent ? (
      <>{emptyContent}</>
    ) : (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {emptyText}
      </div>
    );
  }
  return <>{children}</>;
}
