import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQueries } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertTriangle,
  Coins,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Store,
  Tag,
  Trash2,
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
import { StatCard as SummaryCard } from "@/components/ui/stat-card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormField as Field } from "@/components/ui/form-field";
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
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { apiErrorMessage } from "@/api/client";
import { fetchWalletByTenant } from "@/api/endpoints";
import type {
  ModelPricing,
  Tenant,
  Wallet,
} from "@/api/types";
import {
  useAllTenants,
  useCreatePricing,
  useDeletePricing,
  useModelPricing,
  useRecharge,
  useUpdatePricing,
} from "@/hooks/queries";
import { formatTokens as fmtTokens, formatCurrency as fmtPrice } from "@/lib/format";

// ============================================================ tenant wallets
// The billing backend exposes GET /billing/wallet/{tenant_id} (per-tenant) but
// no aggregate "all wallets" endpoint. We fan out one query per tenant and
// assemble the summary table from the results. Tenants without a wallet show
// "—" and offer a recharge that will create the wallet on demand.

export function BillingAdminPage() {
  const tenantsQ = useAllTenants();
  const tenants: Tenant[] = tenantsQ.data ?? [];

  // One wallet query per tenant (super_admin endpoint). useQueries batches
  // them so TanStack Query manages cache/invalidation per-tenant.
  const walletQueries = useQueries({
    queries: tenants.map((t) => ({
      // qk.walletByTenant(t.id) — inlined to avoid a queries.ts cycle.
      queryKey: ["billing", "wallet", t.id] as const,
      queryFn: () => fetchWalletByTenant(t.id),
      enabled: tenants.length > 0,
    })),
  });

  const [rechargeTenant, setRechargeTenant] = useState<Tenant | null>(null);

  const anyWalletFetching = walletQueries.some((q) => q.isFetching);

  const refetchAll = () => {
    void tenantsQ.refetch();
    walletQueries.forEach((q) => void q.refetch());
  };

  // Aggregate totals across all tenants (wallets that exist).
  const wallets: (Wallet | null)[] = walletQueries.map((q) => q.data ?? null);
  const totalBalance = wallets.reduce(
    (sum, w) => sum + (w?.balance ?? 0),
    0,
  );
  const totalRecharged = wallets.reduce(
    (sum, w) => sum + (w?.total_recharged ?? 0),
    0,
  );
  const totalConsumed = wallets.reduce(
    (sum, w) => sum + (w?.total_consumed ?? 0),
    0,
  );

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">计费管理（总部）</h1>
          <p className="text-muted-foreground">
            各门店 Token 钱包汇总、充值操作与模型定价维护。仅超级管理员可见。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={refetchAll}
          disabled={tenantsQ.isFetching || anyWalletFetching}
        >
          <RefreshCw
            className={cn(
              "h-4 w-4",
              (tenantsQ.isFetching || anyWalletFetching) && "animate-spin",
            )}
          />
          刷新
        </Button>
      </div>

      {/* aggregate counters */}
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryCard
          title="全平台余额合计"
          value={fmtTokens(totalBalance)}
          icon={<WalletIcon className="h-4 w-4 text-muted-foreground" />}
        />
        <SummaryCard
          title="全平台累计充值"
          value={fmtTokens(totalRecharged)}
          icon={<Coins className="h-4 w-4 text-emerald-500" />}
        />
        <SummaryCard
          title="全平台累计消耗"
          value={fmtTokens(totalConsumed)}
          icon={<Coins className="h-4 w-4 text-rose-500" />}
        />
      </div>

      {/* tenant wallets */}
      <Card>
        <CardHeader>
          <CardTitle>门店钱包</CardTitle>
          <CardDescription>共 {tenants.length} 家门店</CardDescription>
        </CardHeader>
        <CardContent>
          {tenantsQ.isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : tenants.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Store className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无门店</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>门店</TableHead>
                  <TableHead>余额</TableHead>
                  <TableHead>累计充值</TableHead>
                  <TableHead>累计消耗</TableHead>
                  <TableHead>预警阈值</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenants.map((t, i) => {
                  const w = wallets[i];
                  const isLoading = walletQueries[i]?.isLoading;
                  const isLow =
                    w !== null && w.balance < w.low_balance_threshold;
                  return (
                    <TableRow key={t.id}>
                      <TableCell className="font-medium">
                        <div className="flex flex-col">
                          <span>{t.name}</span>
                          <code className="w-fit rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                            {t.id.slice(0, 8)}
                          </code>
                        </div>
                      </TableCell>
                      <TableCell
                        className={cn(
                          "font-mono tabular-nums",
                          isLoading && "text-muted-foreground",
                          isLow && "font-bold text-destructive",
                        )}
                      >
                        {isLoading ? (
                          "…"
                        ) : w === null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          fmtTokens(w.balance)
                        )}
                      </TableCell>
                      <TableCell className="font-mono tabular-nums text-muted-foreground">
                        {w ? fmtTokens(w.total_recharged) : "—"}
                      </TableCell>
                      <TableCell className="font-mono tabular-nums text-muted-foreground">
                        {w ? fmtTokens(w.total_consumed) : "—"}
                      </TableCell>
                      <TableCell className="font-mono tabular-nums text-muted-foreground">
                        {w ? fmtTokens(w.low_balance_threshold) : "—"}
                      </TableCell>
                      <TableCell>
                        {w === null ? (
                          <Badge variant="secondary">未开通</Badge>
                        ) : isLow ? (
                          <Badge variant="destructive">
                            <AlertTriangle className="mr-1 h-3 w-3" />
                            余额不足
                          </Badge>
                        ) : w.is_active ? (
                          <Badge variant="success">正常</Badge>
                        ) : (
                          <Badge variant="secondary">已停用</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setRechargeTenant(t)}
                        >
                          <Coins className="mr-1.5 h-3.5 w-3.5" />
                          充值
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* pricing CRUD */}
      <PricingSection />

      {/* recharge dialog */}
      <RechargeDialog
        tenant={rechargeTenant}
        onClose={() => setRechargeTenant(null)}
      />
    </div>
  );
}

// ============================================================ recharge dialog

const rechargeSchema = z.object({
  amount: z
    .number({ error: "请输入数字" })
    .int("充值数量需为整数")
    .min(1, "充值数量需大于 0"),
  remark: z.string().max(500).optional(),
});
type RechargeValues = z.input<typeof rechargeSchema>;

function RechargeDialog({
  tenant,
  onClose,
}: {
  tenant: Tenant | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const rechargeMut = useRecharge();

  const form = useForm<RechargeValues>({
    resolver: zodResolver(rechargeSchema),
    defaultValues: { amount: 10000, remark: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    if (!tenant) return;
    try {
      await rechargeMut.mutateAsync({
        tenant_id: tenant.id,
        amount: values.amount,
        remark: values.remark || undefined,
      });
      toast.success(
        "充值成功",
        `${tenant.name} +${fmtTokens(values.amount)} tokens`,
      );
      form.reset({ amount: 10000, remark: "" });
      onClose();
    } catch (err) {
      toast.error("充值失败", apiErrorMessage(err));
    }
  });

  return (
    <Dialog
      open={!!tenant}
      onOpenChange={(o) => {
        if (!o) {
          form.reset({ amount: 10000, remark: "" });
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>充值 · {tenant?.name}</DialogTitle>
          <DialogDescription>
            为该门店的 Token 钱包充值。若门店尚无钱包，系统将自动创建。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>充值数量（Token 整数）</Label>
            <Input
              type="number"
              step="1"
              min="1"
              {...form.register("amount", { valueAsNumber: true })}
            />
            {form.formState.errors.amount && (
              <p className="text-xs text-destructive">
                {form.formState.errors.amount.message}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              提示：1 万 token 约可供数十轮对话，具体取决于模型与上下文长度。
            </p>
          </div>
          <div className="space-y-2">
            <Label>备注（可选）</Label>
            <Input
              {...form.register("remark")}
              placeholder="如：7 月采购"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={rechargeMut.isPending}>
              确认充值
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ pricing CRUD

const pricingSchema = z.object({
  model: z.string().min(1, "模型名不能为空").max(64),
  input_price_per_1k: z
    .number({ error: "请输入数字" })
    .min(0, "单价不能为负"),
  output_price_per_1k: z
    .number({ error: "请输入数字" })
    .min(0, "单价不能为负"),
  currency: z.string().max(8).default("CNY"),
  is_active: z.boolean().default(true),
});
type PricingValues = z.input<typeof pricingSchema>;

const EMPTY_PRICING: PricingValues = {
  model: "",
  input_price_per_1k: 0,
  output_price_per_1k: 0,
  currency: "CNY",
  is_active: true,
};

function PricingSection() {
  const toast = useToast();
  const { data: pricing, isLoading } = useModelPricing();
  const createMut = useCreatePricing();
  const updateMut = useUpdatePricing();
  const deleteMut = useDeletePricing();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ModelPricing | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ModelPricing | null>(null);

  const form = useForm<PricingValues>({
    resolver: zodResolver(pricingSchema),
    defaultValues: EMPTY_PRICING,
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_PRICING);
    setFormOpen(true);
  };

  const openEdit = (p: ModelPricing) => {
    setEditing(p);
    form.reset({
      model: p.model,
      input_price_per_1k: Number(p.input_price_per_1k),
      output_price_per_1k: Number(p.output_price_per_1k),
      currency: p.currency,
      is_active: p.is_active,
    });
    setFormOpen(true);
  };

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const payload = {
        // platform-default pricing (tenant_id null) — the HQ page manages
        // platform policy, not per-store overrides.
        tenant_id: null,
        model: values.model,
        input_price_per_1k: values.input_price_per_1k,
        output_price_per_1k: values.output_price_per_1k,
        currency: values.currency || "CNY",
        is_active: values.is_active,
      };
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新定价", values.model);
      } else {
        await createMut.mutateAsync(payload);
        toast.success("已创建定价", values.model);
      }
      setFormOpen(false);
    } catch (err) {
      toast.error(editing ? "更新失败" : "创建失败", apiErrorMessage(err));
    }
  });

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMut.mutateAsync(deleteTarget.id);
      toast.success("已停用定价", deleteTarget.model);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("停用失败", apiErrorMessage(err));
    }
  };

  const list: ModelPricing[] = pricing ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>模型定价</CardTitle>
          <CardDescription>
            平台级每千 Token 单价。修改会影响后续所有门店的计费。
          </CardDescription>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" /> 新增定价
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            加载中…
          </div>
        ) : list.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <Tag className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              暂无定价，点击右上角「新增定价」
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>模型</TableHead>
                <TableHead>输入单价 / 1k</TableHead>
                <TableHead>输出单价 / 1k</TableHead>
                <TableHead>币种</TableHead>
                <TableHead>范围</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {p.model}
                    </code>
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {fmtPrice(Number(p.input_price_per_1k))}
                  </TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {fmtPrice(Number(p.output_price_per_1k))}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {p.currency}
                  </TableCell>
                  <TableCell>
                    {p.tenant_id === null ? (
                      <Badge variant="default">平台默认</Badge>
                    ) : (
                      <Badge variant="secondary">租户覆盖</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {p.is_active ? (
                      <Badge variant="success">生效</Badge>
                    ) : (
                      <Badge variant="secondary">已停用</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEdit(p)}>
                          <Pencil className="mr-2 h-4 w-4" /> 编辑
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setDeleteTarget(p)}
                        >
                          <Trash2 className="mr-2 h-4 w-4" /> 停用
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* create / edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editing ? "编辑平台定价" : "新增平台定价"}
            </DialogTitle>
            <DialogDescription>
              {editing
                ? `修改模型「${editing.model}」的每千 Token 单价`
                : "为模型配置每千 Token 单价（平台默认，对所有门店生效）"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field
                label="模型名"
                error={form.formState.errors.model?.message}
              >
                <Input
                  {...form.register("model")}
                  placeholder="如 gpt-4o-mini"
                />
              </Field>
              <Field label="币种">
                <Input
                  {...form.register("currency")}
                  placeholder="CNY"
                  disabled
                />
              </Field>
              <Field
                label="输入单价 / 1k Token"
                error={form.formState.errors.input_price_per_1k?.message}
              >
                <Input
                  type="number"
                  step="0.0001"
                  min="0"
                  {...form.register("input_price_per_1k", {
                    valueAsNumber: true,
                  })}
                />
              </Field>
              <Field
                label="输出单价 / 1k Token"
                error={form.formState.errors.output_price_per_1k?.message}
              >
                <Input
                  type="number"
                  step="0.0001"
                  min="0"
                  {...form.register("output_price_per_1k", {
                    valueAsNumber: true,
                  })}
                />
              </Field>
            </div>
            <Field label="状态">
              <Select
                value={form.watch("is_active") ? "true" : "false"}
                onValueChange={(v) =>
                  form.setValue("is_active", v === "true", {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">生效</SelectItem>
                  <SelectItem value="false">停用</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setFormOpen(false)}
              >
                取消
              </Button>
              <Button
                type="submit"
                disabled={createMut.isPending || updateMut.isPending}
              >
                {editing ? "保存" : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* delete (deactivate) confirm */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认停用定价</DialogTitle>
            <DialogDescription>
              确定停用模型「{deleteTarget?.model}」的定价？停用后该模型不再
              参与计费（历史扣费记录仍可解读）。如需恢复，可重新编辑启用。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" /> 停用
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ---------------- shared bits ----------------

// (FormField is imported from @/components/ui/form-field as `Field`;
//  SummaryCard is imported from @/components/ui/stat-card.)
