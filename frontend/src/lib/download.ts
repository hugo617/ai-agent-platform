/**
 * Browser download helper for blob responses (CSV export).
 *
 * Creates a temporary `<a>` element with an object URL, clicks it, then revokes
 * the URL so the blob doesn't leak memory. Extracted into a lib so every export
 * button reuses the same trigger + cleanup; inlined ad-hoc anchors tend to
 * forget the revoke and leave the blob pinned in memory.
 */

/**
 * Trigger a browser download of `blob` named `filename`.
 *
 * The object URL is revoked on the next tick via `setTimeout(..., 0)` so the
 * download has a chance to start before the URL is invalidated. This matches
 * the common pattern recommended by MDN; revoking synchronously can race with
 * some browsers' download initiators.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  // Revoke on the next tick so the browser has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
