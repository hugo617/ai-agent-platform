/**
 * customers/ hq-view — cross-store customer aggregation (super_admin only, read-only).
 *
 * Extracted from the original customers-page.tsx (plan-customers-page-split.md).
 * Pure locality move: zero behaviour change.
 *
 * The list endpoint already returns every store's profiles expanded, so we
 * expand rows inline without a separate detail fetch.
 */
import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Activity, ChevronDown, ChevronRight, Contact } from "lucide-react";

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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ListState } from "@/components/ui/list-state";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { useCustomers } from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import type { CustomerRead } from "@/api/types";
import { GENDER_LABEL, statusBadge } from "./shared";
import { CustomerUsageDialog } from "./customer-usage-dialog";

export function HqView() {
  const { data: customers, isLoading } = useCustomers();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // Token 费用管理系列 3/4: customer whose global AI-usage dialog is open.
  const [usageTarget, setUsageTarget] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Client-side filter seeded from ?search= so the global-search-box "查看全部"
  // deep link carries the term onto this view (the customers endpoint has no
  // server-side search). Mirrors StoreView's filter above.
  const [searchParams] = useSearchParams();
  const search = (searchParams.get("search") ?? "").trim().toLowerCase();
  const list: CustomerRead[] = search
    ? (customers ?? []).filter(
        (c) =>
          c.name.toLowerCase().includes(search) ||
          c.identity_key.toLowerCase().includes(search),
      )
    : (customers ?? []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="客户（总部视图）"
        subtitle="跨店聚合：查看每个客户在所有门店的档案。此视图为只读，写操作请切换到门店视角。"
      />

      <Card>
        <CardHeader>
          <CardTitle>全局客户列表</CardTitle>
          <CardDescription>
            共 {list.length} 位客户（跨全部门店）
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            loadingVariant="skeleton"
            skeletonRows={6}
            emptyContent={
              <EmptyState icon={Contact} title="暂无客户" description="跨全部门店暂无客户档案" />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10" />
                  <TableHead>姓名</TableHead>
                  <TableHead>手机号/证件号</TableHead>
                  <TableHead>性别</TableHead>
                  <TableHead>到店数</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((c) => {
                  const isOpen = expanded.has(c.id);
                  return (
                    <Fragment key={c.id}>
                      <TableRow
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => toggle(c.id)}
                      >
                        <TableCell className="text-muted-foreground">
                          {isOpen ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </TableCell>
                        <TableCell className="font-medium">{c.name}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {c.identity_key}
                        </TableCell>
                        <TableCell>
                          {c.gender ? GENDER_LABEL[c.gender] ?? c.gender : "-"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {c.profile_count} 家店
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {fmt(c.created_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              setUsageTarget({ id: c.id, name: c.name });
                            }}
                          >
                            <Activity className="mr-1.5 h-3.5 w-3.5" />
                            AI 用量
                          </Button>
                        </TableCell>
                      </TableRow>
                      {isOpen && (
                        <TableRow
                          className="bg-muted/30 hover:bg-muted/30"
                        >
                          <TableCell />
                          <TableCell colSpan={6}>
                            <div className="space-y-2 py-2">
                              <p className="text-xs font-medium text-muted-foreground">
                                跨店档案明细（{c.profiles.length} 条）
                              </p>
                              {c.profiles.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                  无活跃档案（可能已被各门店删除）
                                </p>
                              ) : (
                                <div className="space-y-1">
                                  {c.profiles.map((p) => (
                                    <div
                                      key={p.id}
                                      className="flex flex-wrap items-center gap-3 rounded-md border bg-background px-3 py-2 text-sm"
                                    >
                                      <span className="font-medium">
                                        {p.tenant.name ?? p.tenant.id.slice(0, 8)}
                                      </span>
                                      {statusBadge(p.status)}
                                      <span className="text-muted-foreground">
                                        最近到店：{fmt(p.last_visit_at)}
                                      </span>
                                      {p.remark && (
                                        <span className="text-muted-foreground">
                                          备注：{p.remark}
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      {/* Token 费用管理系列 3/4: global AI usage dialog (cross-store). */}
      <CustomerUsageDialog
        customerId={usageTarget?.id ?? null}
        customerName={usageTarget?.name ?? ""}
        storeScoped={false}
        onClose={() => setUsageTarget(null)}
      />
    </div>
  );
}
