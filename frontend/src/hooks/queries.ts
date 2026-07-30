/**
 * queries.ts — barrel re-export.
 *
 * After the monolith was split into queries/{core,<domain>}.ts
 * (plan-queries-endpoints-domain-split.md), this file re-exports the
 * full public surface so every ``@/hooks/queries`` import path is
 * unchanged. Pure locality move: zero behaviour / zero import change.
 */
export * from "./queries/core";
export * from "./queries/tenants";
export * from "./queries/groups";
export * from "./queries/customers";
export * from "./queries/devices";
export * from "./queries/bookings";
export * from "./queries/booking-config";
export * from "./queries/agents";
export * from "./queries/agent-orchestration";
export * from "./queries/members";
export * from "./queries/users";
export * from "./queries/roles";
export * from "./queries/auth";
export * from "./queries/llm";
export * from "./queries/embedding";
export * from "./queries/knowledge";
export * from "./queries/branding";
export * from "./queries/conversations";
export * from "./queries/api-tokens";
export * from "./queries/billing";
export * from "./queries/dashboard";
export * from "./queries/logs";
export * from "./queries/search";
export * from "./queries/notifications";
export * from "./queries/export";
