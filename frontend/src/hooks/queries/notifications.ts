/**
 * queries/notifications — in-app notifications (priority 54).
 *
 * Extracted from queries.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for qk + useApiMutation.
 */
import { qk, useApiMutation } from "./core";
import { useQuery } from "@tanstack/react-query";
import {
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/endpoints";
import type {
  NotificationFilters,
} from "@/api/types";
// ---------- in-app notifications (priority 54) ----------

/** Paginated, filterable notification list (notifications page). */
export function useNotifications(filters?: NotificationFilters) {
  return useQuery({
    queryKey: qk.notifications(filters ?? {}),
    queryFn: () => fetchNotifications(filters),
    placeholderData: (prev) => prev, // keep previous page while fetching next
  });
}

/**
 * Bell-badge unread count. Polls every 30s — light endpoint, bounded cadence
 * (the plan's risk table: avoid tight SSE/WebSocket for now). The full
 * notification list is fetched on demand when the bell opens.
 */
export function useUnreadCount() {
  return useQuery({
    queryKey: qk.unreadCount,
    queryFn: fetchUnreadCount,
    refetchInterval: 30_000,
  });
}

/** Mark one notification read; invalidates unread-count + the open list. */
export function useMarkNotificationRead() {
  return useApiMutation(
    (id: string) => markNotificationRead(id),
    [["notifications"]],
  );
}

/** Mark all visible notifications read; invalidates unread-count + the list. */
export function useMarkAllNotificationsRead() {
  return useApiMutation(
    (_: void) => markAllNotificationsRead(),
    [["notifications"]],
  );
}

