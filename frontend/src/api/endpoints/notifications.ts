/**
 * endpoints/notifications — in-app notifications (priority 54).
 *
 * Extracted from endpoints.ts monolith (plan-queries-endpoints-domain-split.md).
 * Locality move; see ./core.ts for the shared client.
 */
import {
  api,
} from "../client";
import type {
  Notification,
  NotificationFilters,
  NotificationListResponse,
  UnreadCountResponse,
} from "../types";
// ---------- in-app notifications (priority 54) ----------

/** GET /notifications — paginated notification list (own + tenant-wide). */
export async function fetchNotifications(
  filters?: NotificationFilters,
): Promise<NotificationListResponse> {
  const { data } = await api.get<NotificationListResponse>("/notifications/", {
    params: {
      unread_only: filters?.unread_only,
      limit: filters?.limit,
      offset: filters?.offset,
    },
  });
  return data;
}

/** GET /notifications/unread-count — lightweight bell badge poll. */
export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  const { data } = await api.get<UnreadCountResponse>("/notifications/unread-count");
  return data;
}

/** PUT /notifications/{id}/read — mark one notification read. */
export async function markNotificationRead(id: string): Promise<Notification> {
  const { data } = await api.put<Notification>(`/notifications/${id}/read`);
  return data;
}

/** PUT /notifications/read-all — mark every visible unread notification read. */
export async function markAllNotificationsRead(): Promise<UnreadCountResponse> {
  const { data } = await api.put<UnreadCountResponse>("/notifications/read-all");
  return data;
}

