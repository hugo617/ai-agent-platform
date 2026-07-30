/**
 * chat/ chat-page.tsx — barrel re-export.
 *
 * Exists so the lazy import in App.tsx (`import("@/pages/chat/chat-page")`)
 * keeps working after the 1038-line monolith was split into the chat/ folder
 * (plan-chat-page-split.md). The actual entry is index.tsx; this file just
 * re-exports the public surface so the routing layer doesn't have to know
 * about the folder structure.
 *
 * Why both ``index.tsx`` and ``chat-page.tsx``: ``index.tsx`` is the
 * conventional folder-entry name (matches the "one module per folder" intent);
 * ``chat-page.tsx`` is the named file App.tsx's lazy loader points at, kept to
 * preserve the existing "page file name = route name" convention without
 * touching the router. Mirrors bookings/bookings-page.tsx.
 */
export { ChatPage } from "./index";
