import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Building2, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";

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
import { canManageUsers } from "@/lib/permission";
import type { Organization, OrganizationTreeNode } from "@/api/types";
import {
  useCreateOrganization,
  useDeleteOrganization,
  useOrganizationTree,
  useUpdateOrganization,
} from "@/hooks/queries";

const fmt = (s: string | null): string =>
  s ? new Date(s).toLocaleString() : "-";

// ---------- create/edit form schema ----------
const formSchema = z.object({
  name: z.string().min(1, "组织名称不能为空").max(200),
  code: z.string().max(100).optional(),
  parent_id: z.string().nullable(),
  status: z.string().optional(),
  sort_order: z.number().int().default(0),
});
type FormValues = z.input<typeof formSchema>;

const EMPTY_FORM: FormValues = {
  name: "",
  code: "",
  parent_id: null,
  status: "active",
  sort_order: 0,
};

/** Flatten the org tree into a depth-annotated list for table rendering. */
function flatten(
  nodes: OrganizationTreeNode[],
  depth = 0
): { node: OrganizationTreeNode; depth: number }[] {
  const out: { node: OrganizationTreeNode; depth: number }[] = [];
  for (const n of nodes) {
    out.push({ node: n, depth });
    if (n.children?.length) out.push(...flatten(n.children, depth + 1));
  }
  return out;
}

/** Flat list of all orgs (for the parent dropdown). */
function collectAll(
  nodes: OrganizationTreeNode[]
): { id: string; name: string; depth: number }[] {
  const out: { id: string; name: string; depth: number }[] = [];
  const walk = (ns: OrganizationTreeNode[], d: number) => {
    for (const n of ns) {
      out.push({ id: n.id, name: n.name, depth: d });
      if (n.children?.length) walk(n.children, d + 1);
    }
  };
  walk(nodes, 0);
  return out;
}

export function OrganizationsPage() {
  const toast = useToast();
  const { me } = useAuth();
  const canManage = canManageUsers(me);

  const { data: tree, isLoading } = useOrganizationTree();
  const createMut = useCreateOrganization();
  const updateMut = useUpdateOrganization();
  const deleteMut = useDeleteOrganization();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Organization | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Organization | null>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  // Track the parent_id Select value separately (Select is controlled).
  const parentId = form.watch("parent_id");
  const statusVal = form.watch("status");

  const flatTree = useMemo(() => flatten(tree ?? []), [tree]);
  const allOrgs = useMemo(() => collectAll(tree ?? []), [tree]);

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_FORM);
    setFormOpen(true);
  };

  const openEdit = (o: Organization) => {
    setEditing(o);
    form.reset({
      name: o.name,
      code: o.code ?? "",
      parent_id: o.parent_id,
      status: o.status,
      sort_order: o.sort_order,
    });
    setFormOpen(true);
  };

  const onSubmit = async (values: FormValues) => {
    try {
      if (editing) {
        // On edit, parent_id is shown read-only; pass through the original.
        await updateMut.mutateAsync({
          id: editing.id,
          payload: {
            name: values.name,
            code: values.code || null,
            status: values.status,
            sort_order: values.sort_order,
          },
        });
        toast.success("已更新组织", values.name);
      } else {
        await createMut.mutateAsync({
          name: values.name,
          code: values.code || undefined,
          parent_id: values.parent_id || null,
          sort_order: values.sort_order,
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">组织</h1>
          <p className="text-muted-foreground">
            管理当前租户的组织架构（树形结构）。支持创建、编辑、删除。
          </p>
        </div>
        {canManage && (
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> 新增组织
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>组织架构</CardTitle>
          <CardDescription>共 {flatTree.length} 个组织节点</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : flatTree.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Building2 className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                暂无组织，点击右上角「新增组织」
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>组织名称</TableHead>
                  <TableHead>编码</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>排序</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flatTree.map(({ node, depth }) => (
                  <TableRow key={node.id}>
                    <TableCell className="font-medium">
                      <span
                        className="inline-flex items-center"
                        style={{ paddingLeft: `${depth * 1.5}rem` }}
                      >
                        {depth > 0 && (
                          <span className="mr-1 text-muted-foreground">└</span>
                        )}
                        <Building2 className="mr-2 h-4 w-4 text-muted-foreground" />
                        {node.name}
                      </span>
                    </TableCell>
                    <TableCell>
                      {node.code ? (
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                          {node.code}
                        </code>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          node.status === "active" ? "success" : "secondary"
                        }
                      >
                        {node.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {node.sort_order}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(node.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {canManage && (
                            <>
                              <DropdownMenuItem onClick={() => openEdit(node)}>
                                <Pencil className="h-4 w-4" /> 编辑
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="text-destructive focus:text-destructive"
                                onClick={() => setDeleteTarget(node)}
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
            <DialogTitle>{editing ? "编辑组织" : "新增组织"}</DialogTitle>
            <DialogDescription>
              {editing
                ? `修改组织「${editing.name}」的信息`
                : "创建一个组织节点"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <Field label="组织名称" error={form.formState.errors.name?.message}>
              <Input {...form.register("name")} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="编码">
                <Input
                  {...form.register("code")}
                  placeholder="如 eng（可选）"
                />
              </Field>
              <Field label="排序">
                <Input
                  type="number"
                  {...form.register("sort_order", { valueAsNumber: true })}
                />
              </Field>
            </div>
            {!editing && (
              <Field label="上级组织">
                <Select
                  value={parentId ?? "__root__"}
                  onValueChange={(v) =>
                    form.setValue(
                      "parent_id",
                      v === "__root__" ? null : v
                    )
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="无（根组织）" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__root__">无（根组织）</SelectItem>
                    {allOrgs
                      // Exclude the node itself (only relevant on edit, but this
                      // branch is create-only).
                      .map((o) => (
                        <SelectItem key={o.id} value={o.id}>
                          {"　".repeat(o.depth)}{o.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </Field>
            )}
            {editing && (
              <Field label="状态">
                <Select
                  value={statusVal ?? "active"}
                  onValueChange={(v) => form.setValue("status", v)}
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
              确定删除组织「{deleteTarget?.name}」？若该组织下有子组织，
              后端会拒绝并提示。
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

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
