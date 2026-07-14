import { Fragment, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Download,
  Loader2,
  RefreshCw,
  ScrollText,
} from "lucide-react";

import { apiErrorMessage } from "@/api/client";
import { fetchTenants } from "@/api/endpoints";
import type { LogFilters, SystemLog, Tenant } from "@/api/types";
import { useAuth } from "@/components/auth/auth-context";
import { useLogs, useExportCsv } from "@/hooks/queries";
import { useQuery } from "@tanstack/react-query";
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
import { useToast } from "@/components/ui/toast";

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

const fmt = (s: string | null | undefined): string =>
  s ? new Date(s).toLocaleString() : "-";

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
  const isSuperAdmin = me?.platform_role === "super_admin";
  const toast = useToast();
  const exportMut = useExportCsv();

  // Filters held in state; the query key includes them so a change refetches.
  const [action, setAction] = useState<string>("all");
  const [resourceType, setResourceType] = useState<string>("all");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [tenantFilter, setTenantFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // HQ-only tenant list for the optional tenant filter dropdown.
  const { data: tenants } = useQuery({
    queryKey: ["tenants", "all"],
    queryFn: fetchTenants,
    enabled: isSuperAdmin,
  });

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
  const handleExport = async () => {
    const filename = `logs_${new Date().toISOString().slice(0, 10)}.csv`;
    try {
      await exportMut.mutateAsync({
        entity: "logs",
        filename,
        params: {
          date_from: filters.date_from,
          date_to: filters.date_to,
          tenant_id: filters.tenant_id,
        },
      });
      toast.success("已导出审计日志");
    } catch (err) {
      toast.error("导出失败", apiErrorMessage(err));
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <ScrollText className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">审计日志</h1>
            <p className="text-sm text-muted-foreground">
              {isSuperAdmin ? "全平台操作记录(可按门店筛选)" : "本门店操作记录"}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={exportMut.isPending}
          >
            {exportMut.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            导出 CSV
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
                    {(tenants as Tenant[] | undefined ?? []).map((t) => (
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
          {isError ? (
            <div className="py-8 text-center text-sm text-destructive">
              加载失败:{apiErrorMessage(error)}
              <Button variant="outline" size="sm" className="ml-3" onClick={() => refetch()}>
                重试
              </Button>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" /> 加载中…
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              没有符合条件的审计记录
            </div>
          ) : (
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
                  {data.items.map((log: SystemLog) => {
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
          )}
        </CardContent>
      </Card>
    </div>
  );
}
