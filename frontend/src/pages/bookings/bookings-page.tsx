/**
 * bookings/ bookings-page.tsx — barrel re-export.
 *
 * Exists so the lazy import in App.tsx (`import("@/pages/bookings/bookings-page")`)
 * keeps working after the 1373-line monolith was split into the bookings/
 * folder (plan-bookings-page-split.md). The actual entry is index.tsx; this
 * file just re-exports the public surface so the routing layer doesn't have to
 * know about the folder structure.
 *
 * Why both ``index.tsx`` and ``bookings-page.tsx``: ``index.tsx`` is the
 * conventional folder-entry name (matches the "one module per folder" intent);
 * ``bookings-page.tsx`` is the named file App.tsx's lazy loader points at, kept
 * to preserve the existing "page file name = route name" convention without
 * touching the router.
 */
export { BookingsPage } from "./index";
