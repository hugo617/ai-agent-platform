/**
 * customers/ store-view — within-tenant customer profile CRUD.
 *
 * Extracted from the original customers-page.tsx (plan-customers-page-split.md).
 * Pure locality move: zero behaviour change.
 *
 * Cross-store identity reuse (same identity_key) is handled transparently by
 * the backend: it returns 201 with the existing Customer embedded.
 */
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { Activity, Contact, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";

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
import { hasPermission } from "@/lib/permission";
import { ExportCsvButton } from "@/components/ui/export-csv-button";
import type {
  CustomerProfileCreate,
  CustomerProfileRead,
  CustomerProfileUpdate,
} from "@/api/types";
import {
  useCreateCustomerProfile,
  useCustomerProfiles,
  useDeleteCustomerProfile,
  useUpdateCustomerProfile,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import {
  EMPTY_FORM,
  GENDERS,
  GENDER_LABEL,
  STATUSES,
  formSchema,
  parseTagsJson,
  statusBadge,
} from "./shared";
import type { FormValues } from "./shared";
import { CustomerUsageDialog } from "./customer-usage-dialog";

export function StoreView() {
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
    const { tags, error } = parseTagsJson(values.tags_json);
    if (error) {
      toast.error(error);
      return null;
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
        tags: tags.tags,
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
        tags: tags.tags,
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
