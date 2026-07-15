import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Building2,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  X,
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
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import type { Group } from "@/api/types";
import {
  useAttachTenant,
  useCreateGroup,
  useDeleteGroup,
  useDetachTenant,
  useGroups,
  useAllTenants,
  useUpdateGroup,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

// ---------- create/edit form schema ----------
// tenant_ids are managed outside react-hook-form (Checkbox list), so the schema
// only covers the scalar Group fields.
const formSchema = z.object({
  name: z.string().min(1, "组织名称不能为空").max(200),
  code: z.string().max(100).optional(),
  address: z.string().max(500).optional(),
  description: z.string().optional(),
  status: z.string().optional(),
  sort_order: z.number().int().default(0),
});
type FormValues = z.input<typeof formSchema>;

const EMPTY_FORM: FormValues = {
  name: "",
  code: "",
  address: "",
  description: "",
  status: "active",
  sort_order: 0,
};

export function GroupsPage() {
  const toast = useToast();
  const { me } = useAuth();
  // Group is platform-level: only super_admin may create/edit/delete. Tenant
  // owner/admin still get a read-only view of their own groups.
  const canManage = isSuperAdmin(me);

  const { data: groups, isLoading } = useGroups();
  // Only super_admin can attach stores, so only they need the full tenant
  // list; a read-only (non-super-admin) viewer would otherwise trigger a 403.
  const { data: tenants } = useAllTenants(canManage);
  const createMut = useCreateGroup();
  const updateMut = useUpdateGroup();
  const deleteMut = useDeleteGroup();
  const attachMut = useAttachTenant();
  const detachMut = useDetachTenant();

  // ---- dialogs ----
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Group | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Group | null>(null);

  // tenant_ids chosen at creation time (Checkbox list). Unused in edit mode,
  // where attachment is done via the dedicated attach/detach panel.
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);
  // which tenant is pending attach in the edit dialog's dropdown
  const [attachPick, setAttachPick] = useState("");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_FORM);
    setSelectedTenantIds([]);
    setFormOpen(true);
  };

  const openEdit = (g: Group) => {
    setEditing(g);
    form.reset({
      name: g.name,
      code: g.code ?? "",
      address: g.address ?? "",
      description: g.description ?? "",
      status: g.status,
      sort_order: g.sort_order,
    });
    setAttachPick("");
    setFormOpen(true);
  };

  const toggleCreateTenant = (id: string) => {
    setSelectedTenantIds((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    );
  };

  const handleSubmit = async (values: FormValues) => {
    const payload = {
      name: values.name,
      code: values.code?.trim() || undefined,
      address: values.address?.trim() || undefined,
      description: values.description?.trim() || undefined,
      status: values.status || "active",
      sort_order: values.sort_order,
    };
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新组织", editing.name);
      } else {
        await createMut.mutateAsync({
          ...payload,
          tenant_ids: selectedTenantIds,
        });
        toast.success("已创建组织", values.name);
      }
      setFormOpen(false);
    } catch (err) {
      toast.error(editing ? "更新失败" : "创建失败", apiErrorMessage(err));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMut.mutateAsync(deleteTarget.id);
      toast.success("已删除组织", deleteTarget.name);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  const handleAttach = async () => {
    if (!editing || !attachPick) return;
    try {
      await attachMut.mutateAsync({
        groupId: editing.id,
        tenantId: attachPick,
      });
      toast.success("已挂载门店");
      setAttachPick("");
    } catch (err) {
      toast.error("挂载失败", apiErrorMessage(err));
    }
  };

  const handleDetach = async (tenantId: string, tenantName?: string | null) => {
    if (!editing) return;
    try {
      await detachMut.mutateAsync({
        groupId: editing.id,
        tenantId,
      });
      toast.success("已卸载门店", tenantName ?? tenantId);
    } catch (err) {
      toast.error("卸载失败", apiErrorMessage(err));
    }
  };

  const list = groups ?? [];

  // tenants not yet attached to the editing group (drives the attach dropdown)
  const attachableTenants = useMemo(() => {
    if (!editing) return [];
    const attached = new Set(editing.tenant_ids);
    return (tenants ?? []).filter((t) => !attached.has(t.id));
  }, [editing, tenants]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">组织</h1>
          <p className="text-muted-foreground">
            管理跨租户的经营主体，并将门店挂载到组织下。
          </p>
        </div>
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> 新建组织
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>组织列表</CardTitle>
          <CardDescription>
            共 {list.length} 个组织
            {!canManage && "（只读视图）"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : list.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Building2 className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {canManage
                  ? "暂无组织，点击右上角「新建组织」"
                  : "您还未归属任何组织，请联系总部"}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>组织名称</TableHead>
                  <TableHead>编码</TableHead>
                  <TableHead>地址</TableHead>
                  <TableHead>关联门店</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>更新时间</TableHead>
                  {canManage && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((g) => (
                  <TableRow key={g.id}>
                    <TableCell className="font-medium">{g.name}</TableCell>
                    <TableCell>
                      {g.code ? (
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                          {g.code}
                        </code>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="max-w-[240px] truncate text-muted-foreground">
                      {g.address ?? "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {g.tenant_ids.length} 家
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={g.status === "active" ? "success" : "default"}
                      >
                        {g.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(g.updated_at)}
                    </TableCell>
                    {canManage && (
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => openEdit(g)}>
                              <Pencil className="mr-2 h-4 w-4" /> 编辑
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteTarget(g)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> 删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* create / edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑组织" : "新建组织"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "修改组织基础信息，并在下方挂载/卸载门店。"
                : "创建一个跨租户的经营主体，可选择初始门店。"}
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            <Field label="组织名称 *">
              <Input
                {...form.register("name")}
                placeholder="如：XX 连锁集团"
              />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.name.message}
                </p>
              )}
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field label="编码（可选）">
                <Input
                  {...form.register("code")}
                  placeholder="如：xx-group"
                />
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
                    <SelectItem value="active">active</SelectItem>
                    <SelectItem value="inactive">inactive</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>

            <Field label="地址（可选）">
              <Input {...form.register("address")} placeholder="总部地址" />
            </Field>

            <Field label="描述（可选）">
              <Input {...form.register("description")} />
            </Field>

            <Field label="排序权重">
              <Input
                type="number"
                {...form.register("sort_order", { valueAsNumber: true })}
              />
            </Field>

            {/* ---- tenant attachment ---- */}
            {!editing ? (
              <Field label="关联门店（创建时挂载，可后续增删）">
                {(tenants ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    暂无可选门店
                  </p>
                ) : (
                  <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
                    {(tenants ?? []).map((t) => (
                      <label
                        key={t.id}
                        className="flex cursor-pointer items-center gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          checked={selectedTenantIds.includes(t.id)}
                          onChange={() => toggleCreateTenant(t.id)}
                          className="h-4 w-4"
                        />
                        <span>{t.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </Field>
            ) : (
              <Field label={`关联门店（${editing.tenant_ids.length} 家）`}>
                <div className="flex flex-wrap gap-2">
                  {editing.tenants.length === 0 ? (
                    <span className="text-sm text-muted-foreground">
                      暂未挂载门店
                    </span>
                  ) : (
                    editing.tenants.map((t) => (
                      <Badge
                        key={t.id}
                        variant="secondary"
                        className="gap-1 pr-1"
                      >
                        {t.name ?? t.id.slice(0, 8)}
                        <button
                          type="button"
                          onClick={() => handleDetach(t.id, t.name)}
                          disabled={detachMut.isPending}
                          className="ml-0.5 rounded-full hover:bg-muted"
                          aria-label={`卸载 ${t.name ?? t.id}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))
                  )}
                </div>
                {attachableTenants.length > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    <Select value={attachPick} onValueChange={setAttachPick}>
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder="+ 添加门店" />
                      </SelectTrigger>
                      <SelectContent>
                        {attachableTenants.map((t) => (
                          <SelectItem key={t.id} value={t.id}>
                            {t.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleAttach}
                      disabled={!attachPick || attachMut.isPending}
                    >
                      挂载
                    </Button>
                  </div>
                )}
              </Field>
            )}

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
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定删除组织「{deleteTarget?.name}」？此操作将解除其与全部门店的关联，且不可恢复。
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
              <Trash2 className="mr-2 h-4 w-4" /> 删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------- shared field ----------------
// (FormField is imported from @/components/ui/form-field as `Field`.)
