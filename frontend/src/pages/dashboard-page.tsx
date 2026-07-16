import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Bot,
  Building2,
  Contact,
  MessageSquare,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
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
import { NumberTicker } from "@/components/ui/number-ticker";
import { AreaChartMini, BarChartMini } from "@/components/ui/chart";
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
// activity trend rendered with recharts (Stage 3 upgrade from the old pure-CSS
// bars) + a Bento Grid of quick actions. Real data from /statistics + /dashboard/trends.
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

  // The "primary" metric (conversations) gets the glow ring + the chart, so it
  // reads as the hero of the dashboard. The other three are supporting stats.
  const stats = [
    {
      label: "用户",
      value: userStatsQ.data?.total ?? 0,
      icon: Users,
      q: userStatsQ,
    },
    {
      label: "智能体",
      value: agentStatsQ.data?.total ?? 0,
      icon: Bot,
      q: agentStatsQ,
    },
    {
      label: "对话",
      value: convStatsQ.data?.total ?? 0,
      sub: convStatsQ.data
        ? `近 7 天 ${convStatsQ.data.last_7d}`
        : undefined,
      icon: MessageSquare,
      q: convStatsQ,
    },
    {
      label: "客户",
      value: custStatsQ.data?.total ?? 0,
      sub: custStatsQ.data ? `活跃 ${custStatsQ.data.active}` : undefined,
      icon: Contact,
      q: custStatsQ,
    },
  ];

  // Flatten the trend points into the AreaChartMini shape ({label, value}). We
  // plot conversation volume as the single series — that's the "活跃度" signal.
  const trend = trendsQ.data?.points ?? [];
  const trendEmpty =
    trend.length > 0 && trend.every((p) => p.conversations === 0 && p.messages === 0);
  const areaData = trend.map((p) => ({ label: p.date.slice(5), value: p.conversations }));

  // Bento Grid quick actions. Each tile is a themed entry point — kept
  // restrained (no Aceternity background beams): a big icon + label + a one-
  // line hint. The "创建租户" tile is super_admin-only.
  const quickActions = [
    {
      to: "/agents",
      icon: Bot,
      title: "管理智能体",
      hint: "配置 prompt、模型与编排",
      accent: "text-blue-500",
    },
    {
      to: "/chat",
      icon: MessageSquare,
      title: "开始对话",
      hint: "测试智能体的实际表现",
      accent: "text-emerald-500",
    },
    {
      to: "/customers",
      icon: Contact,
      title: "客户管理",
      hint: "维护客户档案与标签",
      accent: "text-amber-500",
    },
    {
      to: "/knowledge",
      icon: Sparkles,
      title: "知识库",
      hint: "为对话补充专属知识",
      accent: "text-purple-500",
    },
  ];

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

      {/* stat cards — Number Ticker animates each value into place. */}
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
                  <div className="text-2xl font-bold">
                    <NumberTicker value={s.value} />
                  </div>
                  {s.sub && (
                    <p className="mt-1 text-xs text-muted-foreground">{s.sub}</p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* activity trend — recharts AreaChart replaces the old CSS bars. */}
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
          ) : trendEmpty || areaData.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              近 {trendDays} 天暂无对话记录
            </div>
          ) : (
            <AreaChartMini data={areaData} height={200} />
          )}
        </CardContent>
      </Card>

      {/* Bento Grid quick actions + role/permissions summary.
          Layout: a 3-column bento on lg. The "快速操作" tile spans 2 columns
          and holds the 4 quick-action entries; the role tile spans 1. */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card variant="glow" className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              快速操作
            </CardTitle>
            <CardDescription>常用入口</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {quickActions.map((a) => (
              <Link
                key={a.to}
                to={a.to}
                className="group flex items-start gap-3 rounded-lg border bg-card/50 p-4 transition-colors hover:bg-accent"
              >
                <div
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted",
                    a.accent,
                  )}
                >
                  <a.icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium">{a.title}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {a.hint}
                  </div>
                </div>
              </Link>
            ))}
            {me?.platform_role === "super_admin" && (
              <Button
                variant="outline"
                className="flex h-auto items-start justify-start gap-3 p-4"
                onClick={() => setTenantDialogOpen(true)}
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-primary">
                  <Plus className="h-5 w-5" />
                </div>
                <div className="text-left">
                  <div className="text-sm font-medium">创建租户</div>
                  <div className="text-xs text-muted-foreground">
                    新建一个独立的租户空间
                  </div>
                </div>
              </Button>
            )}
          </CardContent>
        </Card>

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
// customers) + per-tenant conversation activity Top N rendered with recharts
// (Stage 3 upgrade from the old pure-CSS bars).
function HqView() {
  const toast = useToast();
  const { me } = useAuth();
  const overviewQ = useDashboardOverview(true);

  const totals = overviewQ.data?.totals;
  const topTenants = overviewQ.data?.top_tenants ?? [];

  const stats = [
    { label: "租户", value: totals?.tenants ?? 0, icon: Building2 },
    { label: "用户", value: totals?.users ?? 0, icon: Users },
    { label: "智能体", value: totals?.agents ?? 0, icon: Bot },
    { label: "对话", value: totals?.conversations ?? 0, icon: MessageSquare },
    { label: "客户", value: totals?.customers ?? 0, icon: Contact },
  ];

  // Map Top N tenants to the horizontal bar chart shape. We truncate the tenant
  // name so the category axis doesn't crowd; the full name still shows in the
  //tooltip via the recharts default.
  const topData = topTenants.map((t) => ({
    label: (t.tenant_name || t.tenant_id.slice(0, 8)).slice(0, 12),
    value: t.conversations,
  }));

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

      {/* platform totals — Number Ticker for the same animated feel. */}
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
                <div className="text-2xl font-bold">
                  <NumberTicker value={s.value} />
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* per-tenant activity Top N — horizontal BarChart replaces CSS bars. */}
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
          ) : topData.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              暂无门店活跃数据
            </div>
          ) : (
            <BarChartMini data={topData} height={320} horizontal />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
