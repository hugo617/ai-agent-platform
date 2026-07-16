import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { MoreHorizontal, Pencil, Plus, Store } from "lucide-react";

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
import { ListState } from "@/components/ui/list-state";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import type { Tenant } from "@/api/types";
import { useAllTenants, useCreateTenant, useUpdateTenant } from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

// ---------- create / edit form schema ----------
// Creation only sends `name` (the backend's TenantCreate accepts name only);
// status / description / address are set via PUT after creation, or edited on
// an existing tenant. The form covers all four so one dialog serves both modes.
const formSchema = z.object({
  name: z.string().min(1, "门店名称不能为空").max(200),
  status: z.string().optional(),
  description: z.string().max(500).optional(),
  address: z.string().max(500).optional(),
});
type FormValues = z.input<typeof formSchema>;

const EMPTY_FORM: FormValues = {
  name: "",
  status: "active",
  description: "",
  address: "",
};

export function TenantsPage() {
  const toast = useToast();
  const { data: tenants, isLoading } = useAllTenants();
  const createMut = useCreateTenant();
  const updateMut = useUpdateTenant();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Tenant | null>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_FORM);
    setFormOpen(true);
  };

  const openEdit = (t: Tenant) => {
    setEditing(t);
    form.reset({
      name: t.name,
      status: t.status ?? "active",
      description: t.description ?? "",
      address: t.address ?? "",
    });
    setFormOpen(true);
  };

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      if (editing) {
        // Partial update: only send fields that actually changed, so an empty
        // description/address is sent as "" only when the user cleared it.
        const payload: Record<string, string> = {};
        if (values.name !== editing.name) payload.name = values.name;
        if ((values.status ?? "active") !== (editing.status ?? "active"))
          payload.status = values.status ?? "active";
        if ((values.description ?? "") !== (editing.description ?? ""))
          payload.description = values.description ?? "";
        if ((values.address ?? "") !== (editing.address ?? ""))
          payload.address = values.address ?? "";
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新门店", values.name);
      } else {
        // Create only accepts name; the other fields, if filled, are applied
        // via a follow-up PUT so the backend's TenantCreate shape is honoured.
        const created = await createMut.mutateAsync(values.name.trim());
        const extra: Record<string, string> = {};
        if (values.status && values.status !== "active")
          extra.status = values.status;
        if (values.description?.trim()) extra.description = values.description.trim();
        if (values.address?.trim()) extra.address = values.address.trim();
        if (Object.keys(extra).length > 0) {
          await updateMut.mutateAsync({ id: created.id, payload: extra });
        }
        toast.success("已创建门店", values.name);
      }
      setFormOpen(false);
    } catch (err) {
      toast.error(editing ? "更新失败" : "创建失败", apiErrorMessage(err));
    }
  });

  const list = tenants ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="门店管理"
        subtitle="平台级门店（租户）列表，可查看、创建、编辑所有门店。"
        actions={
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> 新建门店
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>门店列表</CardTitle>
          <CardDescription>共 {list.length} 家门店</CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            loadingVariant="skeleton"
            skeletonRows={5}
            emptyContent={
              <EmptyState
                icon={Store}
                title="暂无门店"
                description="点击右上角「新建门店」创建第一个"
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>门店名称</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>地址</TableHead>
                  <TableHead>成员数</TableHead>
                  <TableHead>描述</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-medium">
                      <div className="flex flex-col">
                        <span>{t.name}</span>
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground w-fit">
                          {t.id.slice(0, 8)}
                        </code>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          (t.status ?? "active") === "active" ? "success" : "default"
                        }
                      >
                        {t.status ?? "active"}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-muted-foreground">
                      {t.address || "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {t.member_count ?? 0} 人
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-muted-foreground">
                      {t.description || "-"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(t.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openEdit(t)}>
                            <Pencil className="mr-2 h-4 w-4" /> 编辑
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
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
            <DialogTitle>{editing ? "编辑门店" : "新建门店"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "修改门店的基础信息。"
                : "创建一个新的门店（租户）。创建后可在组织页挂载到经营主体下。"}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>门店名称</Label>
              <Input
                {...form.register("name")}
                placeholder="如：朝阳理疗中心"
              />
              {form.formState.errors.name && (
                <p className="text-sm text-destructive">
                  {form.formState.errors.name.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label>状态</Label>
              <Select
                defaultValue={form.getValues("status") ?? "active"}
                onValueChange={(v) => form.setValue("status", v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="active" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">active（营业中）</SelectItem>
                  <SelectItem value="inactive">inactive（停业）</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>地址</Label>
              <Input
                {...form.register("address")}
                placeholder="如：北京市朝阳区某某路 1 号"
              />
            </div>

            <div className="space-y-2">
              <Label>描述</Label>
              <Input
                {...form.register("description")}
                placeholder="门店简介（可选）"
              />
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
    </div>
  );
}
