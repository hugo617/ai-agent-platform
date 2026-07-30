/**
 * endpoints.ts — barrel re-export.
 *
 * After the monolith was split into endpoints/{core,<domain>}.ts
 * (plan-queries-endpoints-domain-split.md), this file re-exports the
 * full public surface so every ``@/api/endpoints`` import path is
 * unchanged. Pure locality move: zero behaviour / zero import change.
 */
export * from "./endpoints/core";
export * from "./endpoints/file-upload";
export * from "./endpoints/auth";
export * from "./endpoints/dev";
export * from "./endpoints/tenants";
export * from "./endpoints/groups";
export * from "./endpoints/customers";
export * from "./endpoints/devices";
export * from "./endpoints/bookings";
export * from "./endpoints/booking-config";
export * from "./endpoints/billing";
export * from "./endpoints/agents";
export * from "./endpoints/agent-orchestration";
export * from "./endpoints/members";
export * from "./endpoints/users";
export * from "./endpoints/logs";
export * from "./endpoints/roles";
export * from "./endpoints/permissions";
export * from "./endpoints/llm";
export * from "./endpoints/embedding-settings";
export * from "./endpoints/knowledge";
export * from "./endpoints/branding";
export * from "./endpoints/api-tokens";
export * from "./endpoints/auth-2";
export * from "./endpoints/conversations-+-chat";
export * from "./endpoints/dashboard";
export * from "./endpoints/search";
export * from "./endpoints/composite-chat";
export * from "./endpoints/notifications";
export * from "./endpoints/export";
