import { Fragment, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Contact,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
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
import { ListState } from "@/components/ui/list-state";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission, isSuperAdmin } from "@/lib/permission";
import type {
  CustomerProfileCreate,
  CustomerProfileRead,
  CustomerProfileUpdate,
  CustomerRead,
} from "@/api/types";
import {
  useCreateCustomerProfile,
  useCustomerProfiles,
  useCustomerUsage,
  useCustomers,
  useDeleteCustomerProfile,
  useUpdateCustomerProfile,
} from "@/hooks/queries";
import { formatDateTime as fmt, formatTokens } from "@/lib/format";
import { ExportCsvButton } from "@/components/ui/export-csv-button";

const GENDERS = ["male", "female", "other"] as const;
const GENDER_LABEL: Record<string, string> = {
  male: "男",
  female: "女",
  other: "其他",
};
const STATUSES = ["active", "inactive", "vip", "blacklist"] as const;

function statusBadge(status: string) {
  if (status === "vip") return <Badge variant="default">VIP</Badge>;
  if (status === "inactive") return <Badge variant="secondary">未激活</Badge>;
  if (status === "blacklist") return <Badge variant="destructive">黑名单</Badge>;
  return <Badge variant="success">活跃</Badge>;
}

// ---------- create/edit form schema ----------
const formSchema = z.object({
  identity_key: z.string().min(1, "手机号/证件号不能为空").max(100),
  name: z.string().min(1, "姓名不能为空").max(100),
  gender: z.string().optional(),
  birthday: z.string().optional(),
  remark: z.string().optional(),
  tags_json: z.string().optional(), // JSON string; parsed on submit
  status: z.string(),
});
type FormValues = z.input<typeof formSchema>;

const EMPTY_FORM: FormValues = {
  identity_key: "",
  name: "",
  gender: "",
  birthday: "",
  remark: "",
  tags_json: "",
  status: "active",
};

export function CustomersPage() {
  const { me } = useAuth();

  // super_admin sees the HQ aggregate view by default; everyone else sees
  // their own store's profiles. The backend enforces the boundary (HQ
  // endpoints are require_super_admin), so a non-super_admin calling
  // useCustomers would get 403 — we split the query by role to match.
  return isSuperAdmin(me) ? <HqView /> : <StoreView />;
}

// ============================================================ store view
// List/create/edit/delete THIS tenant's customer profiles. Cross-store
// identity reuse (same identity_key) is handled transparently by the backend:
// it returns 201 with the existing Customer embedded.
function StoreView() {
  const toast = useToast();
  const { me } = useAuth();

  const { data: profiles, isLoading } = useCustomerProfiles();
  const createMut = useCreateCustomerProfile();
  const updateMut = useUpdateCustomerProfile();
  const deleteMut = useDeleteCustomerProfile();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CustomerProfileRead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CustomerProfileRead | null>(
    null,
  );
  // Token 费用管理系列 3/4: the profile whose AI-usage dialog is open.
  const [usageTarget, setUsageTarget] = useState<CustomerProfileRead | null>(
    null,
  );

  // Button-level guards are driven by the caller's effective api permissions
  // (aggregated in /me.permissions). super_admin bypasses via hasPermission.
  const canCreate = hasPermission(me, "customers", "create");
  const canDelete = hasPermission(me, "customers", "delete");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_FORM);
    setFormOpen(true);
  };

  const openEdit = (p: CustomerProfileRead) => {
    setEditing(p);
    form.reset({
      identity_key: p.customer.identity_key,
      name: p.customer.name,
      gender: p.customer.gender ?? "",
      birthday: p.customer.birthday ?? "",
      remark: p.remark ?? "",
      tags_json:
        p.tags && Object.keys(p.tags).length > 0
          ? JSON.stringify(p.tags, null, 2)
          : "",
      status: p.status,
    });
    setFormOpen(true);
  };

  const buildPayload = (values: FormValues) => {
    let tags: Record<string, unknown> | undefined;
    const raw = values.tags_json?.trim();
    if (raw) {
      try {
        tags = JSON.parse(raw);
      } catch {
        toast.error("标签 JSON 格式错误");
        return null;
      }
    }
    return { ...values, tags };
  };

  const onSubmit = async (values: FormValues) => {
    if (editing) {
      const tags = buildPayload(values);
      if (tags === null) return;
      const payload: CustomerProfileUpdate = {
        name: values.name,
        gender: values.gender || undefined,
        birthday: values.birthday || undefined,
        remark: values.remark || undefined,
        tags,
        status: values.status,
      };
      try {
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新客户档案", editing.customer.name);
        setFormOpen(false);
      } catch (err) {
        toast.error("更新失败", apiErrorMessage(err));
      }
    } else {
      const tags = buildPayload(values);
      if (tags === null) return;
      const payload: CustomerProfileCreate = {
        identity_key: values.identity_key,
        name: values.name,
        gender: values.gender || undefined,
        birthday: values.birthday || undefined,
        remark: values.remark || undefined,
        tags,
        status: values.status,
      };
      try {
        await createMut.mutateAsync(payload);
        toast.success("已创建客户", values.name);
        setFormOpen(false);
      } catch (err) {
        toast.error("创建失败", apiErrorMessage(err));
      }
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMut.mutateAsync(deleteTarget.id);
      toast.success("已删除档案", deleteTarget.customer.name);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  // Client-side filter seeded from ?search= so the global-search-box "查看全部"
  // deep link carries the term onto this page (the profiles endpoint has no
  // server-side search). Matches against name + identity_key + remark + status.
  const [searchParams] = useSearchParams();
  const search = (searchParams.get("search") ?? "").trim().toLowerCase();
  const list = search
    ? (profiles ?? []).filter(
        (p) =>
          p.customer.name.toLowerCase().includes(search) ||
          p.customer.identity_key.toLowerCase().includes(search) ||
          (p.remark ?? "").toLowerCase().includes(search) ||
          p.status.toLowerCase().includes(search),
      )
    : (profiles ?? []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="客户"
        subtitle="管理本店客户档案。同一客户（按手机号/证件号识别）跨店复用全局身份。"
        actions={
          <>
            {canCreate && (
              <Button onClick={openCreate}>
                <Plus className="mr-2 h-4 w-4" /> 新增客户
              </Button>
            )}
            <ExportCsvButton entity="customers" successMessage="已导出客户列表" />
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>客户列表</CardTitle>
          <CardDescription>
            共 {list.length} 位客户
            {!canCreate && "（只读视图）"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            loadingVariant="skeleton"
            skeletonRows={6}
            emptyContent={
              <EmptyState
                icon={Contact}
                title="暂无客户"
                description={
                  canCreate ? "点击右上角「新增客户」" : "本店暂无客户档案"
                }
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>姓名</TableHead>
                  <TableHead>手机号/证件号</TableHead>
                  <TableHead>性别</TableHead>
                  <TableHead>生日</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>最近到店</TableHead>
                  <TableHead>备注</TableHead>
                  {canCreate && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">
                      {p.customer.name}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {p.customer.identity_key}
                    </TableCell>
                    <TableCell>
                      {p.customer.gender
                        ? GENDER_LABEL[p.customer.gender] ??
                          p.customer.gender
                        : "-"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {p.customer.birthday ?? "-"}
                    </TableCell>
                    <TableCell>{statusBadge(p.status)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(p.last_visit_at)}
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-muted-foreground">
                      {p.remark ?? "-"}
                    </TableCell>
                    {canCreate && (
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
                            <DropdownMenuItem onClick={() => setUsageTarget(p)}>
                              <Activity className="mr-2 h-4 w-4" /> AI 用量
                            </DropdownMenuItem>
                            {canDelete && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  className="text-destructive focus:text-destructive"
                                  onClick={() => setDeleteTarget(p)}
                                >
                                  <Trash2 className="mr-2 h-4 w-4" /> 删除档案
                                </DropdownMenuItem>
                              </>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      {/* create / edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑客户档案" : "新增客户"}</DialogTitle>
            <DialogDescription>
              {editing
                ? `修改 ${editing.customer.name} 的信息（全局身份字段将同步到所有门店）`
                : "创建本店客户档案。若手机号/证件号已存在，将自动复用全局身份。"}
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="space-y-4"
          >
            <div className="grid grid-cols-2 gap-4">
              <Field
                label="手机号/证件号 *"
                error={form.formState.errors.identity_key?.message}
              >
                <Input
                  {...form.register("identity_key")}
                  placeholder="如：138xxxx"
                  disabled={!!editing}
                />
              </Field>
              <Field
                label="姓名 *"
                error={form.formState.errors.name?.message}
              >
                <Input {...form.register("name")} />
              </Field>
              <Field label="性别">
                <Select
                  value={form.watch("gender") || "_none"}
                  onValueChange={(v) =>
                    form.setValue(
                      "gender",
                      v === "_none" ? "" : v,
                      { shouldDirty: true },
                    )
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择性别" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">未设置</SelectItem>
                    {GENDERS.map((g) => (
                      <SelectItem key={g} value={g}>
                        {GENDER_LABEL[g]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="生日">
                <Input type="date" {...form.register("birthday")} />
              </Field>
              <Field label="状态">
                <Select
                  value={form.watch("status")}
                  onValueChange={(v) =>
                    form.setValue("status", v, { shouldDirty: true })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <Field label="备注">
              <Input {...form.register("remark")} placeholder="本店私有备注" />
            </Field>
            <Field
              label="标签（JSON）"
              hint="如 {&quot;level&quot;: &quot;vip&quot;}，留空则不修改"
            >
              <textarea
                {...form.register("tags_json")}
                placeholder='{"level": "vip", "source": "walk-in"}'
                className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                rows={3}
              />
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

      {/* delete confirm dialog */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除档案</DialogTitle>
            <DialogDescription>
              确定删除客户「{deleteTarget?.customer.name}」在本店的档案？
              该操作为软删除，全局客户身份将保留（其它门店可能仍在使用）。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" /> 删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Token 费用管理系列 3/4: AI usage attribution dialog. */}
      <CustomerUsageDialog
        customerId={usageTarget?.customer_id ?? null}
        customerName={usageTarget?.customer.name ?? ""}
        storeScoped
        onClose={() => setUsageTarget(null)}
      />
    </div>
  );
}

// ---------------- AI usage dialog (Token 费用管理系列 3/4) ----------------
// Shows a customer's aggregate AI service consumption (chats + tokens + cost)
// and a "为客户咨询" deep link that opens a new attributed chat. Takes the
// GLOBAL customer id (Customer.id), not the profile id — the backend returns
// store-scoped or global totals based on the caller's role.
function CustomerUsageDialog({
  customerId,
  customerName,
  storeScoped,
  onClose,
}: {
  customerId: string | null;
  customerName: string;
  storeScoped: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const { data: usage, isLoading } = useCustomerUsage(customerId);

  const openNewChatForCustomer = () => {
    if (!customerId) return;
    onClose();
    navigate(`/chat?customer_id=${encodeURIComponent(customerId)}`);
  };

  return (
    <Dialog open={!!customerId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>AI 服务 · {customerName}</DialogTitle>
          <DialogDescription>
            {storeScoped
              ? "本店为该客户提供 AI 服务的用量统计"
              : "跨全部门店为该客户提供 AI 服务的用量统计"}
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            加载中…
          </div>
        ) : usage && usage.total_tokens > 0 ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="AI 对话次数"
                value={String(usage.conversation_count)}
                icon={<MessageSquare className="h-4 w-4" />}
              />
              <Metric
                label="Token 总消耗"
                value={formatTokens(usage.total_tokens)}
                icon={<Activity className="h-4 w-4" />}
              />
              <Metric
                label="输入 Token"
                value={formatTokens(usage.prompt_tokens)}
              />
              <Metric
                label="输出 Token"
                value={formatTokens(usage.completion_tokens)}
              />
            </div>
            {usage.total_cost !== null && (
              <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
                累计费用：
                <span className="font-medium">
                  ¥{usage.total_cost.toFixed(4)}
                </span>
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              最近 AI 咨询：{fmt(usage.last_active_at)}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <Activity className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              该客户暂无 AI 服务记录
            </p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
          <Button onClick={openNewChatForCustomer}>
            <MessageSquare className="mr-2 h-4 w-4" /> 为客户咨询
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Metric({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

// ================================================================ HQ view
// Cross-store aggregation (super_admin only, read-only). The list endpoint
// already returns every store's profiles expanded, so we expand rows inline
// without a separate detail fetch.
function HqView() {
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

// ---------------- shared field ----------------
// (FormField is imported from @/components/ui/form-field as `Field`.)

