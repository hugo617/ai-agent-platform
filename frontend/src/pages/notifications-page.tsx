import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  Coins,
  Info,
  Loader2,
  RefreshCw,
  ScrollText,
  UserCog,
} from "lucide-react";

import type { Notification } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Pagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import { ListState } from "@/components/ui/list-state";

const PAGE_SIZE = 20;

/** Type → (Chinese label, icon, badge accent). Mirrors backend type vocabulary. */
const TYPE_META: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }>; accent: string }
> = {
  balance_warning: { label: "余额预警", icon: AlertTriangle, accent: "bg-amber-100 text-amber-800" },
  recharge: { label: "充值到账", icon: Coins, accent: "bg-emerald-100 text-emerald-800" },
  role_change: { label: "角色变更", icon: UserCog, accent: "bg-blue-100 text-blue-800" },
  usage_report: { label: "用量报告", icon: ScrollText, accent: "bg-purple-100 text-purple-800" },
  system: { label: "系统通知", icon: Info, accent: "bg-muted text-muted-foreground" },
};

function TypeBadge({ type }: { type: string }) {
  const meta = TYPE_META[type] ?? { label: type, icon: Info, accent: "bg-muted text-muted-foreground" };
  const Icon = meta.icon;
  return (
    <Badge variant="secondary" className={cn("gap-1", meta.accent)}>
      <Icon className="h-3 w-3" />
      {meta.label}
    </Badge>
  );
}

export function NotificationsPage() {
  const navigate = useNavigate();
  const [unreadOnly, setUnreadOnly] = useState<string>("all");
  const [page, setPage] = useState(1);

  const filters = {
    unread_only: unreadOnly === "unread",
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };
  const { data, isLoading, isError, error, refetch, isFetching } =
    useNotifications(filters);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
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
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Bell className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">通知中心</h1>
            <p className="text-sm text-muted-foreground">
              查看您收到的小站消息(余额预警、充值、角色变更等)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={markAllRead.isPending}
            onClick={() => markAllRead.mutate()}
          >
            <CheckCheck className="mr-2 h-4 w-4" />
            全部已读
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={isFetching}
            onClick={() => refetch()}
          >
            {isFetching ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            刷新
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>消息列表</CardTitle>
            <CardDescription>
              共 {total} 条 · 第 {page} / {totalPages} 页
            </CardDescription>
          </div>
          <div className="w-32">
            <Select
              value={unreadOnly}
              onValueChange={(v) => {
                setUnreadOnly(v);
                setPage(1);
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="unread">仅未读</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <ListState
            isError={isError}
            error={error}
            onRetry={refetch}
            isLoading={isLoading}
            showSpinner
            isEmpty={items.length === 0}
            emptyText={unreadOnly === "unread" ? "没有未读通知" : "暂无通知"}
          >
            <>
              <ul className="divide-y">
                {items.map((item) => {
                  const meta = TYPE_META[item.type] ?? TYPE_META.system;
                  const Icon = meta.icon;
                  return (
                    <li
                      key={item.id}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 py-3 transition-colors hover:bg-muted/40",
                        !item.is_read && "bg-primary/[0.03]",
                      )}
                      onClick={() => handleClick(item)}
                    >
                      <div className="mt-0.5 shrink-0">
                        <Icon className="h-5 w-5 text-muted-foreground" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <TypeBadge type={item.type} />
                          {!item.is_read && (
                            <span className="text-[11px] font-medium text-destructive">
                              未读
                            </span>
                          )}
                          <span className="text-xs text-muted-foreground">
                            {fmt(item.created_at)}
                          </span>
                        </div>
                        <p
                          className={cn(
                            "mt-1 text-sm",
                            !item.is_read && "font-medium",
                          )}
                        >
                          {item.title}
                        </p>
                        <p className="mt-0.5 text-sm text-muted-foreground">
                          {item.content}
                        </p>
                      </div>
                      {!item.is_read && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="shrink-0 text-xs"
                          disabled={markRead.isPending}
                          onClick={(e) => {
                            e.stopPropagation();
                            markRead.mutate(item.id);
                          }}
                        >
                          标为已读
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
              <div className="mt-4 flex items-center justify-end">
                <Pagination
                  page={page}
                  totalPages={totalPages}
                  onPageChange={setPage}
                />
              </div>
            </>
          </ListState>
        </CardContent>
      </Card>
    </div>
  );
}
