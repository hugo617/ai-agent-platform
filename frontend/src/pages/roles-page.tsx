import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  MoreHorizontal,
  Pencil,
  Plus,
  Shield,
  ShieldCheck,
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
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission } from "@/lib/permission";
import type { Role, RolePermissionGrant } from "@/api/types";
import {
  useCreateRole,
  useDeleteRole,
  useGrantRolePermission,
  useRevokeRolePermission,
  useRoles,
  useRolePermissions,
  useUpdateRole,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

// ---------- create/edit form schema ----------
const formSchema = z.object({
  name: z.string().min(1, "角色名称不能为空").max(50),
  code: z.string().min(1, "角色编码不能为空").max(100),
  description: z.string().optional(),
  sort_order: z.number().int().default(0),
});
type FormValues = z.input<typeof formSchema>;

const EMPTY_FORM: FormValues = {
  name: "",
  code: "",
  description: "",
  sort_order: 0,
};

export function RolesPage() {
  const toast = useToast();
  const { me } = useAuth();
  // Creating/editing roles requires roles:create; super_admin bypasses.
  const canManage = hasPermission(me, "roles", "create");

  const { data: roles, isLoading } = useRoles();
  const createMut = useCreateRole();
  const updateMut = useUpdateRole();
  const deleteMut = useDeleteRole();

  // ---- dialogs ----
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Role | null>(null);
  const [permTarget, setPermTarget] = useState<Role | null>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_FORM);
    setFormOpen(true);
  };

  const openEdit = (r: Role) => {
    setEditing(r);
    form.reset({
      name: r.name,
      code: r.code,
      description: r.description ?? "",
      sort_order: r.sort_order,
    });
    setFormOpen(true);
  };

  const onSubmit = async (values: FormValues) => {
    try {
      if (editing) {
        // code is immutable after create; only name/description/sort_order updatable
        await updateMut.mutateAsync({
          id: editing.id,
          payload: {
            name: values.name,
            description: values.description || undefined,
            sort_order: values.sort_order,
          },
        });
        toast.success("已更新角色", values.name);
      } else {
        await createMut.mutateAsync({
          name: values.name,
          code: values.code,
          description: values.description || undefined,
          sort_order: values.sort_order,
        });
        toast.success("已创建角色", values.name);
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
      toast.success("已删除角色", deleteTarget.name);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  const list = roles ?? [];

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">角色</h1>
          <p className="text-muted-foreground">
            管理当前租户的角色定义与权限分配。角色由后端 pycasbin RBAC 模型驱动。
          </p>
        </div>
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> 新增角色
          </Button>
        )}
      </div>

      {/* list */}
      <Card>
        <CardHeader>
          <CardTitle>角色列表</CardTitle>
          <CardDescription>共 {list.length} 个角色</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : list.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Shield className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                暂无角色，点击右上角「新增角色」
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>角色名称</TableHead>
                  <TableHead>编码</TableHead>
                  <TableHead>说明</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>排序</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell>
                      <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                        {r.code}
                      </code>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground">
                      {r.description ?? "-"}
                    </TableCell>
                    <TableCell>
                      {r.is_system ? (
                        <Badge variant="default">
                          <ShieldCheck className="mr-1 h-3 w-3" />
                          系统
                        </Badge>
                      ) : (
                        <Badge variant="secondary">自定义</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {r.sort_order}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(r.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => setPermTarget(r)}>
                            <Shield className="h-4 w-4" /> 权限分配
                          </DropdownMenuItem>
                          {canManage && (
                            <>
                              <DropdownMenuItem onClick={() => openEdit(r)}>
                                <Pencil className="h-4 w-4" /> 编辑
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="text-destructive focus:text-destructive"
                                disabled={r.is_system}
                                onClick={() => setDeleteTarget(r)}
                              >
                                <Trash2 className="h-4 w-4" /> 删除
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
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
            <DialogTitle>{editing ? "编辑角色" : "新增角色"}</DialogTitle>
            <DialogDescription>
              {editing
                ? `修改角色「${editing.name}」的信息`
                : "创建一个自定义角色"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="角色名称" error={form.formState.errors.name?.message}>
                <Input {...form.register("name")} />
              </Field>
              <Field
                label="角色编码"
                error={form.formState.errors.code?.message}
              >
                <Input
                  {...form.register("code")}
                  disabled={!!editing}
                  placeholder={editing ? "编码创建后不可修改" : "如 editor"}
                />
              </Field>
              <Field label="说明">
                <Input {...form.register("description")} />
              </Field>
              <Field label="排序">
                <Input
                  type="number"
                  {...form.register("sort_order", { valueAsNumber: true })}
                />
              </Field>
            </div>
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
              确定删除角色「{deleteTarget?.name}」？该操作为软删除。
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

      {/* permission assignment dialog */}
      <PermissionDialog role={permTarget} onClose={() => setPermTarget(null)} />
    </div>
  );
}

// ---------------- permission assignment panel ----------------

function PermissionDialog({
  role,
  onClose,
}: {
  role: Role | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const { data: perms, isLoading } = useRolePermissions(role?.id ?? null);
  const grantMut = useGrantRolePermission();
  const revokeMut = useRevokeRolePermission();

  const [obj, setObj] = useState("");
  const [act, setAct] = useState("");

  const handleGrant = async () => {
    if (!role) return;
    const payload: RolePermissionGrant = {
      obj: obj.trim(),
      act: act.trim(),
    };
    if (!payload.obj || !payload.act) {
      toast.error("请填写完整的权限对象和操作");
      return;
    }
    try {
      await grantMut.mutateAsync({ roleId: role.id, payload });
      toast.success("已授予权限", `${payload.obj}:${payload.act}`);
      setObj("");
      setAct("");
    } catch (err) {
      toast.error("授权失败", apiErrorMessage(err));
    }
  };

  const handleRevoke = async (permissionId: string, label: string) => {
    if (!role) return;
    try {
      await revokeMut.mutateAsync({ roleId: role.id, permissionId });
      toast.success("已撤销权限", label);
    } catch (err) {
      toast.error("撤销失败", apiErrorMessage(err));
    }
  };

  return (
    <Dialog open={!!role} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>权限分配 · {role?.name}</DialogTitle>
          <DialogDescription>
            为该角色授予或撤销 (对象:操作) 权限。变更会实时同步到 casbin。
          </DialogDescription>
        </DialogHeader>

        {/* grant form */}
        <div className="flex items-end gap-2">
          <Field label="对象 (obj)">
            <Input
              value={obj}
              onChange={(e) => setObj(e.target.value)}
              placeholder="如 documents"
            />
          </Field>
          <Field label="操作 (act)">
            <Select value={act} onValueChange={setAct}>
              <SelectTrigger>
                <SelectValue placeholder="选择操作" />
              </SelectTrigger>
              <SelectContent>
                {["read", "create", "update", "delete"].map((a) => (
                  <SelectItem key={a} value={a}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Button onClick={handleGrant} disabled={grantMut.isPending}>
            <Plus className="mr-2 h-4 w-4" /> 授予
          </Button>
        </div>

        {/* current permissions */}
        <div className="space-y-2">
          <Label>当前权限</Label>
          {isLoading ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : (perms ?? []).length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              暂无权限，使用上方表单授予
            </div>
          ) : (
            <div className="space-y-1.5">
              {(perms ?? []).map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">
                      {p.obj}:{p.act}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      授予于 {fmt(p.valid_from)}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    disabled={revokeMut.isPending}
                    onClick={() =>
                      handleRevoke(p.permission_id, `${p.obj}:${p.act}`)
                    }
                  >
                    <Trash2 className="mr-1 h-3.5 w-3.5" /> 撤销
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------- shared field ----------------

// (FormField is imported from @/components/ui/form-field as `Field`.)
