import { Fragment, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  ScrollText,
} from "lucide-react";

import type { LogFilters, SystemLog } from "@/api/types";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin as isSuperAdminRole } from "@/lib/permission";
import { useLogs, useAllTenants } from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import { ExportCsvButton } from "@/components/ui/export-csv-button";
import { ListState } from "@/components/ui/list-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Pagination } from "@/components/ui/pagination";
import { PageHeader } from "@/components/layout/page-header";

const PAGE_SIZE = 20;

/** Friendly Chinese labels for common actions. */
const ACTION_LABEL: Record<string, string> = {
  create: "创建",
  update: "编辑",
  delete: "删除",
  login: "登录",
  logout: "登出",
  grant: "授权",
  revoke: "撤销",
};

const LEVEL_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  info: "secondary",
  warning: "default",
  error: "destructive",
};

/** Pretty-print a JSONB snapshot (before/after/details) inside a <pre>. */
function JsonBlock({ value }: { value: unknown }) {
  if (!value || (typeof value === "object" && Object.keys(value as object).length === 0)) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <pre className="mt-1 max-h-48 overflow-auto rounded bg-muted p-2 text-xs leading-relaxed">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function LogsPage() {
  const { me } = useAuth();
  const isSuperAdmin = isSuperAdminRole(me);

  // Filters held in state; the query key includes them so a change refetches.
  const [action, setAction] = useState<string>("all");
  const [resourceType, setResourceType] = useState<string>("all");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [tenantFilter, setTenantFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // HQ-only tenant list for the optional tenant filter dropdown. Uses
  // useAllTenants (GET /tenants/all, super_admin platform-wide list) so the
  // dropdown shows every store — NOT useQuery+fetchTenants, which hits
  // GET /tenants/ (user-scoped) and would both under-fill the dropdown AND
  // poison the shared ["tenants","all"] cache that other pages rely on.
  const { data: tenants } = useAllTenants(isSuperAdmin);

  const filters: LogFilters = {
    action: action !== "all" ? action : undefined,
    resource_type: resourceType !== "all" ? resourceType : undefined,
    date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
    date_to: dateTo ? new Date(dateTo + "T23:59:59").toISOString() : undefined,
    tenant_id: isSuperAdmin && tenantFilter !== "all" ? tenantFilter : undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

  const { data, isLoading, isError, error, refetch, isFetching } = useLogs(filters);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items: SystemLog[] = data?.items ?? [];

  const toggleRow = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Export mirrors the active filter set (action / resource / date / tenant)
  // so the CSV matches what the user sees on screen. The backend re-applies
  // the scope: store users can't escape their tenant; super_admin may narrow.

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <ScrollText className="h-6 w-6 text-primary" />
            审计日志
          </span>
        }
        subtitle={
          isSuperAdmin ? "全平台操作记录(可按门店筛选)" : "本门店操作记录"
        }
        actions={
          <div className="flex gap-2">
            <ExportCsvButton
              entity="logs"
              size="sm"
              successMessage="已导出审计日志"
              params={{
                date_from: filters.date_from,
                date_to: filters.date_to,
                tenant_id: filters.tenant_id,
              }}
            />
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
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>过滤</CardTitle>
          <CardDescription>按操作类型、资源、时间范围筛选审计记录</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">操作类型</span>
              <Select value={action} onValueChange={(v) => { setAction(v); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="create">创建</SelectItem>
                  <SelectItem value="update">编辑</SelectItem>
                  <SelectItem value="delete">删除</SelectItem>
                  <SelectItem value="login">登录</SelectItem>
                  <SelectItem value="logout">登出</SelectItem>
                  <SelectItem value="grant">授权</SelectItem>
                  <SelectItem value="revoke">撤销</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">资源类型</span>
              <Select value={resourceType} onValueChange={(v) => { setResourceType(v); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="users">用户</SelectItem>
                  <SelectItem value="agents">智能体</SelectItem>
                  <SelectItem value="customers">客户</SelectItem>
                  <SelectItem value="roles">角色</SelectItem>
                  <SelectItem value="conversations">对话</SelectItem>
                  <SelectItem value="api_tokens">API 令牌</SelectItem>
                  <SelectItem value="wallet">钱包</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">起始日期</span>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">结束日期</span>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
              />
            </div>
            {isSuperAdmin && (
              <div className="space-y-1.5 md:col-span-2">
                <span className="text-xs text-muted-foreground">门店(仅总部)</span>
                <Select value={tenantFilter} onValueChange={(v) => { setTenantFilter(v); setPage(1); }}>
                  <SelectTrigger>
                    <SelectValue placeholder="全平台" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全平台</SelectItem>
                    {(tenants ?? []).map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>操作记录</CardTitle>
            <CardDescription>共 {total} 条 · 第 {page} / {totalPages} 页</CardDescription>
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
            emptyText="没有符合条件的审计记录"
          >
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>时间</TableHead>
                    <TableHead>级别</TableHead>
                    <TableHead>操作</TableHead>
                    <TableHead>资源</TableHead>
                    <TableHead>操作人</TableHead>
                    {isSuperAdmin && <TableHead>门店</TableHead>}
                    <TableHead>摘要</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((log: SystemLog) => {
                    const open = expanded.has(log.id);
                    const hasDetail =
                      log.old_values ||
                      log.new_values ||
                      (log.details_json &&
                        Object.keys(log.details_json).length > 0);
                    return (
                      <Fragment key={log.id}>
                        <TableRow
                          className={hasDetail ? "cursor-pointer hover:bg-muted/50" : undefined}
                          onClick={() => hasDetail && toggleRow(log.id)}
                        >
                          <TableCell className="p-2">
                            {hasDetail ? (
                              open ? (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-muted-foreground" />
                              )
                            ) : null}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                            {fmt(log.created_at)}
                          </TableCell>
                          <TableCell>
                            <Badge variant={LEVEL_VARIANT[log.level] ?? "secondary"}>
                              {log.level}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm">
                            {ACTION_LABEL[log.action] ?? log.action}
                          </TableCell>
                          <TableCell className="text-sm">
                            {log.resource_type ? (
                              <span className="font-mono text-xs">
                                {log.resource_type}
                                {log.resource_id ? `:${log.resource_id.slice(0, 8)}` : ""}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {log.user_id ? log.user_id.slice(0, 8) : "—"}
                          </TableCell>
                          {isSuperAdmin && (
                            <TableCell className="font-mono text-xs text-muted-foreground">
                              {log.tenant_id ? log.tenant_id.slice(0, 8) : "平台"}
                            </TableCell>
                          )}
                          <TableCell className="max-w-md truncate text-sm" title={log.message}>
                            {log.message}
                          </TableCell>
                        </TableRow>
                        {open && hasDetail && (
                          <TableRow className="bg-muted/30 hover:bg-muted/30">
                            <TableCell colSpan={isSuperAdmin ? 8 : 7} className="p-4">
                              {(log.old_values || log.new_values) && (
                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                  <div>
                                    <span className="text-xs font-medium text-muted-foreground">变更前</span>
                                    <JsonBlock value={log.old_values} />
                                  </div>
                                  <div>
                                    <span className="text-xs font-medium text-muted-foreground">变更后</span>
                                    <JsonBlock value={log.new_values} />
                                  </div>
                                </div>
                              )}
                              {log.details_json && Object.keys(log.details_json).length > 0 && (
                                <div className="mt-2">
                                  <span className="text-xs font-medium text-muted-foreground">附加详情</span>
                                  <JsonBlock value={log.details_json} />
                                </div>
                              )}
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })}
                </TableBody>
              </Table>
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
