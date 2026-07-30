/**
 * customers/ customers-page.tsx — barrel re-export.
 *
 * Exists so the lazy import in App.tsx (`import("@/pages/customers-page")`)
 * keeps working after the 834-line monolith was split into the customers/
 * folder (plan-customers-page-split.md). The actual entry is index.tsx; this
 * file just re-exports the public surface so the routing layer doesn't have to
 * know about the folder structure. Mirrors the bookings-page.tsx / chat-page.tsx
 * / devices-page.tsx barrel convention.
 */
export { CustomersPage } from "./customers/index";
