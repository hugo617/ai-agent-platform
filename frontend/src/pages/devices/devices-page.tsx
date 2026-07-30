/**
 * devices/ devices-page.tsx — barrel re-export.
 *
 * Exists so the lazy import in App.tsx (`import("@/pages/devices/devices-page")`)
 * keeps working after the 1083-line monolith was split into the devices/
 * folder (plan-devices-page-split.md). The actual entry is index.tsx; this
 * file just re-exports the public surface so the routing layer doesn't have
 * to know about the folder structure.
 *
 * Why both ``index.tsx`` and ``devices-page.tsx``: ``index.tsx`` is the
 * conventional folder-entry name (matches the "one module per folder" intent);
 * ``devices-page.tsx`` is the named file App.tsx's lazy loader points at, kept
 * to preserve the existing "page file name = route name" convention without
 * touching the router. Mirrors ``bookings/bookings-page.tsx`` (D5).
 */
export { DevicesPage } from "./index";
