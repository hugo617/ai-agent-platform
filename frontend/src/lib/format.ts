/**
 * Shared formatting helpers.
 *
 * Extracted to kill the per-page ``const fmt = (s) => s ? new
 * Date(s).toLocaleString() : "-"`` duplication that was copy-pasted across 12+
 * pages, and the two near-identical relative-time helpers (billing-page's
 * ``fmtRelative`` and notification-bell's ``relativeTime``).
 *
 * Locale is pinned to ``zh-CN`` because this product is Chinese-only; if i18n
 * lands later, pass a locale through these signatures.
 */

/**
 * Format an ISO timestamp as a localized date+time string.
 *
 * Returns ``"-"`` for null/undefined/empty so list pages can pass nullable
 * columns straight through without a ternary.
 */
export function formatDateTime(s?: string | null): string {
  return s ? new Date(s).toLocaleString("zh-CN") : "-";
}

/** Format an ISO timestamp as a localized calendar date (no time). */
export function formatDate(s?: string | null): string {
  return s ? new Date(s).toLocaleDateString("zh-CN") : "-";
}

/**
 * Relative time label like "刚刚" / "3 分钟前" / "2 小时前" / "5 天前".
 *
 * Beyond 7 days, falls back to the calendar date (matching the old
 * notification-bell behaviour). Returns ``"-"`` for null/undefined/empty.
 */
export function formatRelative(iso?: string | null): string {
  if (!iso) return "-";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const min = 60_000;
  const hour = 60 * min;
  const day = 24 * hour;
  if (diff < min) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / min)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`;
  // Beyond a week, show the calendar date.
  return new Date(iso).toLocaleDateString("zh-CN");
}

/**
 * Format an integer token count with a thousands separator.
 *
 * e.g. ``1234567`` → ``"1,234,567"``.
 */
export function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * Format a cost (Decimal snapshot) with a ¥ prefix and 4 decimals.
 *
 * e.g. ``0.5`` → ``"¥0.5000"``. Returns ``"-"`` for null/undefined so nullable
 * cost columns render consistently.
 */
export function formatCurrency(n: number | null | undefined): string {
  return n === null || n === undefined ? "-" : `¥${n.toFixed(4)}`;
}
