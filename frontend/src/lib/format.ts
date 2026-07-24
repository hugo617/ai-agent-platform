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

// ------------------------------------------------------------- datetime-local
//
// Native ``<input type="datetime-local">`` uses the "local, no tz" wire format
// ``YYYY-MM-DDTHH:mm`` (no seconds, no ``Z`` suffix). Two conversion helpers
// bridge that to/from the ISO-8601 strings the API stores. Kept here (not in
// the bookings page) so the next datetime input reuses them instead of
// re-deriving the slice logic.
//
// Why not a real datetime picker? The plan (device-booking slice 06) explicitly
// chose native datetime-local over a calendar widget ("无既有范式... 用原生
// <input type=datetime-local>,别过度设计"). Local time is the right model for
// a store's booking window — the appointment is "14:00 today", not "06:00 UTC".

/**
 * ISO timestamp / Date → the ``YYYY-MM-DDTHH:mm`` value a ``datetime-local``
 * input renders. Empty string for null/undefined (the input's "no value" state).
 *
 * Slices seconds + timezone off — the appointment is a local wall-clock time.
 */
export function toDatetimeLocalValue(s?: string | null): string {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "";
  // Pad each component to 2 digits; toLocaleString would work but rebuilding
  // from getFullYear/Month/Date/Hours/Minutes keeps it tz-stable (no implicit
  // UTC shift) and matches the input's expected wire format exactly.
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * ``YYYY-MM-DDTHH:mm`` (datetime-local) → ISO-8601 string for the API.
 *
 * The native value has no timezone, so we treat it as local time and emit a
 * naive ISO (``YYYY-MM-DDTHH:mm:ss``, no offset). The backend stores naive
 * datetimes (the SQLAlchemy column is ``DateTime``, not ``DateTime(timezone-
 * true)``), so a naive ISO round-trips cleanly on both SQLite and Postgres.
 */
export function fromDatetimeLocalValue(v: string): string {
  // ``new Date("YYYY-MM-DDTHH:mm")`` parses as local but then ``toISOString``
  // shifts to UTC. We want to keep the wall-clock time, so append seconds and
  // emit the string directly (no Date round-trip).
  return v.length >= 16 ? `${v}:00` : v;
}
