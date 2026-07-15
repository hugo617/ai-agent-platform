import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownCircle,
  ArrowUpCircle,
  Coins,
  RefreshCw,
  Wallet as WalletIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StatCard as CounterCard } from "@/components/ui/stat-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { cn } from "@/lib/utils";
import type {
  UsageEventItem,
  WalletTransaction,
  WalletTransactionType,
} from "@/api/types";
import {
  useTransactions,
  useUsage,
  useWallet,
} from "@/hooks/queries";
import {
  formatDateTime as fmt,
  formatRelative as fmtRelative,
  formatTokens as fmtTokens,
  formatCurrency as fmtCost,
} from "@/lib/format";
import { ExportCsvButton } from "@/components/ui/export-csv-button";

const TX_TYPE_LABEL: Record<string, string> = {
  recharge: "充值",
  consume: "消耗",
  refund: "退款",
  adjust: "调整",
};

function txIcon(type: string) {
  if (type === "recharge" || type === "refund")
    return <ArrowUpCircle className="h-4 w-4 text-emerald-500" />;
  if (type === "consume")
    return <ArrowDownCircle className="h-4 w-4 text-rose-500" />;
  return <Activity className="h-4 w-4 text-muted-foreground" />;
}

/**
 * Aggregate usage rows into the last N days of total_tokens, for the trend bar
 * chart. Days with no activity show 0 so the chart stays a continuous timeline.
 * Buckets are ordered oldest → newest (left → right).
 */
function buildDailyTrend(
  items: UsageEventItem[],
  days: number,
): { label: string; value: number }[] {
  const buckets: { label: string; value: number }[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dayMs = 24 * 60 * 60 * 1000;
  const windowStart = today.getTime() - (days - 1) * dayMs;
  for (let i = 0; i < days; i++) {
    const d = new Date(windowStart + i * dayMs);
    buckets.push({
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      value: 0,
    });
  }
  for (const e of items) {
    if (!e.created_at) continue;
    const t = new Date(e.created_at).getTime();
    if (t < windowStart) continue; // older than the window
    const bucketIdx = Math.floor((t - windowStart) / dayMs);
    if (bucketIdx >= 0 && bucketIdx < days) {
      buckets[bucketIdx].value += e.total_tokens ?? 0;
    }
  }
  return buckets;
}

export function BillingPage() {
  const { me } = useAuth();

  const walletQ = useWallet();
  const txQ = useTransactions();
  const usageQ = useUsage();
  const [trendDays, setTrendDays] = useState<7 | 30>(7);

  const wallet = walletQ.data ?? null;
  const transactions: WalletTransaction[] = txQ.data ?? [];
  const usage = usageQ.data;

  const isLow =
    wallet !== null &&
    wallet.balance < wallet.low_balance_threshold;

  const refetchAll = () => {
    void walletQ.refetch();
    void txQ.refetch();
    void usageQ.refetch();
  };

  const anyFetching =
    walletQ.isFetching || txQ.isFetching || usageQ.isFetching;

  const trend = buildDailyTrend(usage?.items ?? [], trendDays);
  const trendMax = Math.max(1, ...trend.map((b) => b.value));

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">费用管理</h1>
          <p className="text-muted-foreground">
            查看本店 Token 余额、消耗趋势、流水明细与用量钻取。
            {!isSuperAdmin(me) && "（只读视图）"}
          </p>
        </div>
        <div className="flex gap-2">
          <ExportCsvButton
            entity="usage"
            size="sm"
            label="导出用量"
            successMessage="已导出用量明细"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={refetchAll}
            disabled={anyFetching}
          >
            <RefreshCw className={cn("h-4 w-4", anyFetching && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      {/* balance card + counters */}
      {walletQ.isLoading ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            加载中…
          </CardContent>
        </Card>
      ) : wallet === null ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <WalletIcon className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              本店尚未开通 Token 钱包，请联系总部开通。
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card
            className={cn(
              isLow && "border-destructive/50 bg-destructive/5",
            )}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                当前余额（Token）
              </CardTitle>
              <WalletIcon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div
                className={cn(
                  "text-2xl font-bold",
                  isLow && "text-destructive",
                )}
              >
                {fmtTokens(wallet.balance)}
              </div>
              {isLow ? (
                <p className="mt-1 flex items-center gap-1 text-xs text-destructive">
                  <AlertTriangle className="h-3 w-3" />
                  余额不足，请联系总部充值
                </p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">
                  预警阈值 {fmtTokens(wallet.low_balance_threshold)}
                </p>
              )}
            </CardContent>
          </Card>

          <CounterCard
            title="累计充值"
            value={fmtTokens(wallet.total_recharged)}
            icon={<ArrowUpCircle className="h-4 w-4 text-emerald-500" />}
          />
          <CounterCard
            title="累计消耗"
            value={fmtTokens(wallet.total_consumed)}
            icon={<ArrowDownCircle className="h-4 w-4 text-rose-500" />}
          />
          <CounterCard
            title="钱包状态"
            value={wallet.is_active ? "正常" : "已停用"}
            icon={<Coins className="h-4 w-4 text-muted-foreground" />}
          />
        </div>
      )}

      {/* low balance banner */}
      {isLow && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            余额（{fmtTokens(wallet!.balance)}）已低于预警阈值（
            {fmtTokens(wallet!.low_balance_threshold)}），对话可能被拦截，请联系总部充值。
          </span>
        </div>
      )}

      {/* consumption trend (pure-CSS bars, no chart lib) */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>消耗趋势</CardTitle>
            <CardDescription>
              近 {trendDays} 天每日 Token 消耗（按用量事件聚合）
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
          {usageQ.isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : trend.every((b) => b.value === 0) ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              近 {trendDays} 天暂无消耗记录
            </div>
          ) : (
            <div className="flex items-end gap-1" style={{ height: 160 }}>
              {trend.map((b, i) => (
                <div
                  key={i}
                  className="flex flex-1 flex-col items-center justify-end gap-1"
                  title={`${b.label}: ${fmtTokens(b.value)} tokens`}
                >
                  <div
                    className="w-full rounded-t bg-primary/70 transition-all hover:bg-primary"
                    style={{
                      height: `${(b.value / trendMax) * 100}%`,
                      minHeight: b.value > 0 ? 4 : 0,
                    }}
                  />
                  {(trendDays === 7 || i % 5 === 0) && (
                    <span className="text-[10px] text-muted-foreground">
                      {b.label}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* usage summary */}
      {usage && (
        <div className="grid gap-4 md:grid-cols-3">
          <CounterCard
            title="Prompt Token（累计）"
            value={fmtTokens(usage.summary.prompt_tokens)}
            icon={<Activity className="h-4 w-4 text-muted-foreground" />}
          />
          <CounterCard
            title="Completion Token（累计）"
            value={fmtTokens(usage.summary.completion_tokens)}
            icon={<Activity className="h-4 w-4 text-muted-foreground" />}
          />
          <CounterCard
            title="Token 总消耗（累计）"
            value={fmtTokens(usage.summary.total_tokens)}
            icon={<Coins className="h-4 w-4 text-muted-foreground" />}
          />
        </div>
      )}

      {/* recent transactions */}
      <Card>
        <CardHeader>
          <CardTitle>最近流水</CardTitle>
          <CardDescription>本店 Token 钱包的充值 / 消耗 / 退款 / 调整记录</CardDescription>
        </CardHeader>
        <CardContent>
          {txQ.isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : transactions.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Coins className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无流水记录</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>类型</TableHead>
                  <TableHead>金额</TableHead>
                  <TableHead>余额</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>备注</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((t) => {
                  const type = t.type as WalletTransactionType;
                  const isIncoming = t.amount >= 0;
                  return (
                    <TableRow key={t.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {txIcon(type)}
                          <span className="font-medium">
                            {TX_TYPE_LABEL[t.type] ?? t.type}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell
                        className={cn(
                          "font-mono tabular-nums",
                          isIncoming ? "text-emerald-600" : "text-rose-600",
                        )}
                      >
                        {isIncoming ? "+" : ""}
                        {fmtTokens(t.amount)}
                      </TableCell>
                      <TableCell className="font-mono tabular-nums text-muted-foreground">
                        {fmtTokens(t.balance_after)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {t.model ? (
                          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                            {t.model}
                          </code>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                      <TableCell className="max-w-[240px] truncate text-muted-foreground">
                        {t.remark ?? "-"}
                      </TableCell>
                      <TableCell
                        className="text-muted-foreground"
                        title={fmt(t.created_at)}
                      >
                        {fmtRelative(t.created_at)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* usage drilldown */}
      <Card>
        <CardHeader>
          <CardTitle>用量明细</CardTitle>
          <CardDescription>
            本店 Token 消耗的逐条记录（按模型 / 对话钻取）
          </CardDescription>
        </CardHeader>
        <CardContent>
          {usageQ.isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : (usage?.items ?? []).length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Activity className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无用量记录</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>模型</TableHead>
                  <TableHead>Prompt</TableHead>
                  <TableHead>Completion</TableHead>
                  <TableHead>合计</TableHead>
                  <TableHead>费用</TableHead>
                  <TableHead>对话</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(usage?.items ?? []).map((e) => (
                  <TableRow key={e.id}>
                    <TableCell>
                      {e.model ? (
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                          {e.model}
                        </code>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums">
                      {fmtTokens(e.prompt_tokens ?? 0)}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums">
                      {fmtTokens(e.completion_tokens ?? 0)}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums font-medium">
                      {fmtTokens(e.total_tokens ?? 0)}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums text-muted-foreground">
                      {fmtCost(e.cost)}
                    </TableCell>
                    <TableCell>
                      {e.conversation_id ? (
                        <Badge variant="secondary">
                          {e.conversation_id.slice(0, 8)}
                        </Badge>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                    <TableCell
                      className="text-muted-foreground"
                      title={fmt(e.created_at)}
                    >
                      {fmtRelative(e.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
