import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bell,
  Coins,
  Info,
  ScrollText,
  UserCog,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { Notification } from "@/api/types";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from "@/hooks/queries";

/**
 * Notification type → (icon, accent color). Mirrors the backend ``type``
 * vocabulary in app/models/notification.py. The icon is the visual cue in the
 * bell dropdown; the accent color highlights unread rows.
 */
const TYPE_META: Record<
  string,
  { icon: React.ComponentType<{ className?: string }>; accent: string }
> = {
  balance_warning: { icon: AlertTriangle, accent: "text-amber-600" },
  recharge: { icon: Coins, accent: "text-emerald-600" },
  role_change: { icon: UserCog, accent: "text-blue-600" },
  usage_report: { icon: ScrollText, accent: "text-purple-600" },
  system: { icon: Info, accent: "text-muted-foreground" },
};

function TypeIcon({ type, className }: { type: string; className?: string }) {
  const meta = TYPE_META[type] ?? TYPE_META.system;
  const Icon = meta.icon;
  return <Icon className={cn("h-4 w-4", meta.accent, className)} />;
}

/** Relative time label ("刚刚" / "3 分钟前" / "2 小时前" / fall back to date). */
function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = Math.max(0, now - then);
  const min = 60 * 1000;
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
 * Top-bar notification bell (priority 54).
 *
 * - Polls unread-count every 30s (light endpoint).
 * - On open, fetches the recent (unread-first) notifications and shows a
 *   dropdown with per-row type icon, title, relative time, and a mark-read
 *   action. Unread rows are visually highlighted.
 * - Clicking a row navigates to its ``link`` (if any) and marks it read.
 * - "全部标记已读" marks every visible notification read in one call.
 */
export function NotificationBell() {
  const navigate = useNavigate();
  const { data: unread } = useUnreadCount();
  // Fetch the recent list (open on demand). Keep it to the latest 8 for the
  // dropdown; the full paginated list lives on /notifications.
  const { data } = useNotifications({ limit: 8, unread_only: false });
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const count = unread?.count ?? 0;
  const items: Notification[] = data?.items ?? [];

  const handleClick = (item: Notification) => {
    if (!item.is_read) {
      markRead.mutate(item.id);
    }
    if (item.link) {
      navigate(item.link);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          {count > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-destructive-foreground">
              {count > 99 ? "99+" : count}
            </span>
          )}
          <span className="sr-only">通知</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between px-3 py-2">
          <DropdownMenuLabel className="p-0 text-sm font-semibold">
            通知
          </DropdownMenuLabel>
          {count > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={markAllRead.isPending}
              onClick={() => markAllRead.mutate()}
            >
              全部标记已读
            </Button>
          )}
        </div>
        <DropdownMenuSeparator className="m-0" />
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              暂无通知
            </div>
          ) : (
            items.map((item) => (
              <DropdownMenuItem
                key={item.id}
                className="flex cursor-pointer items-start gap-2 px-3 py-2.5 focus:bg-accent"
                onClick={() => handleClick(item)}
              >
                <TypeIcon type={item.type} className="mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {!item.is_read && (
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-destructive" />
                    )}
                    <p
                      className={cn(
                        "truncate text-sm",
                        !item.is_read && "font-medium",
                      )}
                    >
                      {item.title}
                    </p>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                    {item.content}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground/70">
                    {relativeTime(item.created_at)}
                  </p>
                </div>
              </DropdownMenuItem>
            ))
          )}
        </div>
        <DropdownMenuSeparator className="m-0" />
        <DropdownMenuItem
          className="cursor-pointer justify-center px-3 py-2 text-sm text-muted-foreground"
          onClick={() => navigate("/notifications")}
        >
          查看全部通知
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
