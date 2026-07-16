import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Bot,
  Building2,
  Contact,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import {
  useAgentStatistics,
  useConversationStatistics,
  useCreateTenant,
  useCustomerStatistics,
  useDashboardOverview,
  useDashboardTrends,
  useTenants,
  useUserStatistics,
} from "@/hooks/queries";

export function DashboardPage() {
  const { me } = useAuth();

  // The store and HQ views split by role, mirroring customers-page.tsx: the HQ
  // overview endpoint is require_super_admin, so a non-super_admin calling it
  // would 403. useDashboardOverview(enabled) gates the request to match.
  return isSuperAdmin(me) ? <HqView /> : <StoreView />;
}

// ============================================================ store view
// Per-tenant stat cards (users / agents / conversations / customers) + a 7-day
// activity trend (pure-CSS bars, same approach as billing-page.tsx). Real data
// from the /statistics endpoints + /dashboard/trends.
function StoreView() {
  const toast = useToast();
  const { me } = useAuth();
  const { data: tenants } = useTenants();
  const createTenantMut = useCreateTenant();

  const userStatsQ = useUserStatistics();
  const agentStatsQ = useAgentStatistics();
  const convStatsQ = useConversationStatistics();
  const custStatsQ = useCustomerStatistics();
  const [trendDays, setTrendDays] = useState<7 | 30>(7);
  const trendsQ = useDashboardTrends(trendDays);

  const [tenantDialogOpen, setTenantDialogOpen] = useState(false);
  const [tenantName, setTenantName] = useState("");

  // The active tenant name (me.tenant_id) from the user's tenant list. Falls
  // back to the truncated id when the name isn't loaded yet.
  const activeTenant = (tenants ?? []).find((t) => t.id === me?.tenant_id);
  const tenantLabel = activeTenant?.name ?? me?.tenant_id?.slice(0, 8) ?? "-";

  const handleCreateTenant = async () => {
    if (!tenantName.trim()) {
      toast.error("请填写租户名称");
      return;
    }
    try {
      await createTenantMut.mutateAsync(tenantName.trim());
      toast.success("已创建租户", tenantName.trim());
      setTenantName("");
      setTenantDialogOpen(false);
    } catch (err) {
      toast.error("创建失败", apiErrorMessage(err));
    }
  };

  const stats = [
    {
      label: "用户",
      value: userStatsQ.data?.total,
      icon: Users,
      q: userStatsQ,
    },
    {
      label: "智能体",
      value: agentStatsQ.data?.total,
      icon: Bot,
      q: agentStatsQ,
    },
    {
      label: "对话",
      value: convStatsQ.data?.total,
      sub: convStatsQ.data
        ? `近 7 天 ${convStatsQ.data.last_7d}`
        : undefined,
      icon: MessageSquare,
      q: convStatsQ,
    },
    {
      label: "客户",
      value: custStatsQ.data?.total,
      sub: custStatsQ.data
        ? `活跃 ${custStatsQ.data.active}`
        : undefined,
      icon: Contact,
      q: custStatsQ,
    },
  ];

  const trend = trendsQ.data?.points ?? [];
  const convMax = Math.max(1, ...trend.map((p) => p.conversations));

  return (
    <div className="space-y-6">
      <PageHeader
        title={`门店概览 · ${tenantLabel}`}
        subtitle={`欢迎回来，${me?.email ?? me?.user_id}。这是你门店的实时数据看板。`}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void userStatsQ.refetch();
              void agentStatsQ.refetch();
              void convStatsQ.refetch();
              void custStatsQ.refetch();
              void trendsQ.refetch();
            }}
          >
            <RefreshCw
              className={cn(
                "h-4 w-4",
                (userStatsQ.isFetching ||
                  agentStatsQ.isFetching ||
                  trendsQ.isFetching) &&
                  "animate-spin",
              )}
            />
            刷新
          </Button>
        }
      />

      {/* stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {s.label}
              </CardTitle>
              <s.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {s.q.isLoading ? (
                <div className="text-2xl font-bold text-muted-foreground">…</div>
              ) : (
                <>
                  <div className="text-2xl font-bold">{s.value ?? 0}</div>
                  {s.sub && (
                    <p className="mt-1 text-xs text-muted-foreground">{s.sub}</p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* activity trend (pure-CSS bars, no chart lib) */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>活跃趋势</CardTitle>
            <CardDescription>
              近 {trendDays} 天每日对话创建数（按 created_at 聚合）
            </CardDescription>
          </div>
          <div className="flex gap-1">
            {[7, 30].map((d) => (
              <Button
                key={d}
                variant={trendDays === d ? "default" : "outline"}
                size="sm"
                onClick={() => setTrendDays(d as 7 | 30)}
              >
                {d} 天
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {trendsQ.isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : trend.every((p) => p.conversations === 0 && p.messages === 0) ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              近 {trendDays} 天暂无对话记录
            </div>
          ) : (
            <div className="flex items-end gap-1" style={{ height: 160 }}>
              {trend.map((p, i) => (
                <div
                  key={i}
                  className="flex flex-1 flex-col items-center justify-end gap-1"
                  title={`${p.date}: ${p.conversations} 对话 / ${p.messages} 消息`}
                >
                  <div
                    className="w-full rounded-t bg-primary/70 transition-all hover:bg-primary"
                    style={{
                      height: `${(p.conversations / convMax) * 100}%`,
                      minHeight: p.conversations > 0 ? 4 : 0,
                    }}
                  />
                  {(trendDays === 7 || i % 5 === 0) && (
                    <span className="text-[10px] text-muted-foreground">
                      {p.date.slice(5)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* quick actions + create tenant (kept from the placeholder page) */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>你的权限</CardTitle>
            <CardDescription>当前角色拥有的操作权限</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {me?.roles?.map((role) => (
              <Badge key={role} variant="success">
                {role}
              </Badge>
            )) ?? (
              <span className="text-sm text-muted-foreground">加载中…</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>快速操作</CardTitle>
            <CardDescription>常用入口</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            <Link to="/agents" className="text-primary hover:underline">
              → 管理智能体
            </Link>
            <Link to="/chat" className="text-primary hover:underline">
              → 开始对话
            </Link>
            <Link to="/customers" className="text-primary hover:underline">
              → 客户管理
            </Link>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-full"
              onClick={() => setTenantDialogOpen(true)}
              // POST /tenants/ is super_admin-only; hide for tenant users.
              hidden={me?.platform_role !== "super_admin"}
            >
              创建租户
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* create tenant dialog */}
      <Dialog open={tenantDialogOpen} onOpenChange={setTenantDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>创建租户</DialogTitle>
            <DialogDescription>
              创建一个新的租户。创建后你将成为该租户的 owner。
              （注意：当前登录会话仍绑定原租户，需重新登录切换。）
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>租户名称</Label>
            <Input
              value={tenantName}
              onChange={(e) => setTenantName(e.target.value)}
              placeholder="如：我的新团队"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTenantDialogOpen(false)}>
              取消
            </Button>
            <Button
              onClick={handleCreateTenant}
              disabled={createTenantMut.isPending}
            >
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ================================================================ HQ view
// super_admin-only: platform totals (tenants / users / conversations / agents /
// customers) + per-tenant conversation activity Top N (pure-CSS bars).
function HqView() {
  const toast = useToast();
  const { me } = useAuth();
  const overviewQ = useDashboardOverview(true);

  const totals = overviewQ.data?.totals;
  const topTenants = overviewQ.data?.top_tenants ?? [];
  const topMax = Math.max(1, ...topTenants.map((t) => t.conversations));

  const stats = [
    {
      label: "租户",
      value: totals?.tenants,
      icon: Building2,
    },
    {
      label: "用户",
      value: totals?.users,
      icon: Users,
    },
    {
      label: "智能体",
      value: totals?.agents,
      icon: Bot,
    },
    {
      label: "对话",
      value: totals?.conversations,
      icon: MessageSquare,
    },
    {
      label: "客户",
      value: totals?.customers,
      icon: Contact,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-primary" />
            平台总览
          </span>
        }
        subtitle={`跨全部门店汇总。${me?.email ?? me?.user_id}（super_admin 视图）`}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void overviewQ.refetch().catch((e) => {
                toast.error("刷新失败", apiErrorMessage(e));
              });
            }}
          >
            <RefreshCw
              className={cn(
                "h-4 w-4",
                overviewQ.isFetching && "animate-spin",
              )}
            />
            刷新
          </Button>
        }
      />

      {/* platform totals */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {s.label}
              </CardTitle>
              <s.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {overviewQ.isLoading ? (
                <div className="text-2xl font-bold text-muted-foreground">…</div>
              ) : (
                <div className="text-2xl font-bold">{s.value ?? 0}</div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* per-tenant activity Top N (pure-CSS bars) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            各门店活跃度 Top 10
          </CardTitle>
          <CardDescription>
            按近 30 天对话创建数排名的门店（跨租户聚合）
          </CardDescription>
        </CardHeader>
        <CardContent>
          {overviewQ.isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : topTenants.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              暂无门店活跃数据
            </div>
          ) : (
            <div className="space-y-2">
              {topTenants.map((t, i) => (
                <div key={t.tenant_id} className="flex items-center gap-3">
                  <span className="w-6 shrink-0 text-right text-xs font-medium text-muted-foreground">
                    {i + 1}
                  </span>
                  <div className="flex w-40 shrink-0 items-center gap-2 truncate">
                    <span className="truncate text-sm font-medium">
                      {t.tenant_name || t.tenant_id.slice(0, 8)}
                    </span>
                  </div>
                  <div className="relative h-6 flex-1 overflow-hidden rounded bg-muted">
                    <div
                      className="h-full rounded bg-primary/70 transition-all"
                      style={{
                        width: `${(t.conversations / topMax) * 100}%`,
                      }}
                    />
                  </div>
                  <span className="w-16 shrink-0 text-right text-sm font-mono tabular-nums text-muted-foreground">
                    {t.conversations}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
