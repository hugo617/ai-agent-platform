/**
 * knowledge/ category-manager — 分类管理 CRUD(admin-ui slice 04 F6)。
 *
 * 管理 tab 的「分类管理」子 tab 主体。渲染 useKnowledgeCategories() 返回的 Category
 * 列表,按 scope 分三组(platform/group/store)各一个 Card 区块,用 ScopeBadge 标识
 * 来源(对齐 reader-ui category-tree 的来源视觉)。每行 Category 有 DropdownMenu
 * (编辑/删除)。
 *
 * 三个操作(新建/编辑/删除)各一个 Dialog,均在组件内条件挂载:
 *   - 新建:scope Select(getAvailableScopes 过滤 —— 角色→可建 scope 映射,对齐后端
 *     _resolve_create_target)+ name + sort_order;scope 联动:platform → 两者 null;
 *     group → group_id 默认 me.group_id(隐藏);store → tenant_id 默认 me.tenant_id
 *     (隐藏)。提交调 useCreateCategory。
 *   - 编辑:只改 name + sort_order(scope/group_id/tenant_id 不可改,对齐后端
 *     KnowledgeCategoryUpdate schema;re-tier = 删除+重建)。提交调 useUpdateCategory。
 *   - 删除:二次确认 Dialog(普通 Dialog,无 alert-dialog.tsx —— 镜像 distribution-list
 *     的撤回确认范式)。提交调 useDeleteCategory(软删,name 释放可复用)。
 *
 * member 守卫:member 在 index.tsx 层已被 hasPermission(me,"knowledge","create") 挡在
 * 管理 tab 之外,进不到本组件。但 getAvailableScopes(me) 对 member 返回 [],即使进到
 * 这里也无「新建分类」按钮(防御性,helper 守卫)。行操作 DropdownMenu 只对有
 * knowledge:create 权限的角色渲染(member 无,但 member 进不来,守卫是双保险)。
 */
import { useEffect, useMemo, useState } from "react";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";

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
import { ListState } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { getAvailableScopes, hasPermission } from "@/lib/permission";
import {
  useCreateCategory,
  useDeleteCategory,
  useKnowledgeCategories,
  useUpdateCategory,
} from "@/hooks/queries";
import type {
  KnowledgeCategoryCreate,
  KnowledgeCategoryRead,
  KnowledgeCategoryUpdate,
  KnowledgeScope,
} from "@/api/types";
import { ScopeBadge, SCOPE_LABEL, SCOPE_ORDER } from "./scope-badge";

// SCOPE_ORDER 现从 scope-badge 共享(与 category-tree 同一份顺序常量,避免重复)。

export function CategoryManager() {
  const { me } = useAuth();
  const { data, isLoading, isError, error, refetch } = useKnowledgeCategories();
  // list 用 data 作 useMemo 依赖(data 引用稳定时不重算;`data ?? []` 每次渲染
  // 新数组,作依赖会触发 oxlint react/exhaustive-deps 误报)。
  const list = useMemo(() => data ?? [], [data]);

  const availableScopes = useMemo(() => getAvailableScopes(me), [me]);
  // 写权限守卫:有 knowledge:create 才显示「新建分类」+ 行操作菜单(member 进不来,
  // 这里是 helper 层双保险)。
  const canWrite = hasPermission(me, "knowledge", "create");

  // 按 scope 分组(platform/group/store),保留 SCOPE_ORDER 顺序;区块内按 sort_order
  // 升序(对齐 reader-ui category-tree,让 admin 管理排序时行序与「排序 N」一致)。
  const grouped = useMemo(() => {
    const m = new Map<KnowledgeScope, KnowledgeCategoryRead[]>();
    for (const s of SCOPE_ORDER) m.set(s, []);
    for (const c of list) {
      m.get(c.scope)?.push(c);
    }
    for (const s of SCOPE_ORDER) {
      m.get(s)?.sort((a, b) => a.sort_order - b.sort_order);
    }
    return m;
  }, [list]);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<KnowledgeCategoryRead | null>(
    null,
  );
  const [deleteTarget, setDeleteTarget] =
    useState<KnowledgeCategoryRead | null>(null);

  return (
    <div className="space-y-4">
      {canWrite && availableScopes.length > 0 && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" /> 新建分类
          </Button>
        </div>
      )}

      {/* 每个 scope 一个 Card 区块(无分类的区块显示空态)。 */}
      {SCOPE_ORDER.map((scope) => {
        const items = grouped.get(scope) ?? [];
        return (
          <Card key={scope}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ScopeBadge scope={scope} />
                {SCOPE_LABEL[scope]}层级分类
              </CardTitle>
              <CardDescription>
                共 {items.length} 个分类。
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ListState
                isLoading={isLoading}
                isEmpty={items.length === 0}
                isError={isError}
                error={error}
                onRetry={() => refetch()}
                loadingVariant="skeleton"
                skeletonRows={2}
                emptyContent={
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    暂无{SCOPE_LABEL[scope]}层级分类
                  </p>
                }
              >
                <div className="space-y-2">
                  {items.map((c) => (
                    <div
                      key={c.id}
                      className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
                    >
                      <div className="min-w-0 flex-1">
                        <span className="truncate font-medium">{c.name}</span>
                        <span className="ml-3 text-xs text-muted-foreground">
                          排序 {c.sort_order}
                        </span>
                      </div>
                      {canWrite && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label="分类操作"
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => setEditTarget(c)}
                            >
                              <Pencil className="mr-2 h-4 w-4" /> 编辑
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => setDeleteTarget(c)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> 删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  ))}
                </div>
              </ListState>
            </CardContent>
          </Card>
        );
      })}

      <CategoryCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        availableScopes={availableScopes}
      />

      {/* 编辑/删除 Dialog 条件挂载(目标为空时卸载)。 */}
      {editTarget && (
        <CategoryEditDialog
          category={editTarget}
          open
          onOpenChange={(o) => !o && setEditTarget(null)}
        />
      )}
      {deleteTarget && (
        <CategoryDeleteDialog
          category={deleteTarget}
          open
          onOpenChange={(o) => !o && setDeleteTarget(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 新建 Dialog:scope Select(角色过滤)+ name + sort_order;scope 联动隐藏 group/tenant。
// ---------------------------------------------------------------------------

interface CategoryCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  availableScopes: KnowledgeScope[];
}

function CategoryCreateDialog({
  open,
  onOpenChange,
  availableScopes,
}: CategoryCreateDialogProps) {
  const { me } = useAuth();
  const toast = useToast();
  const createMut = useCreateCategory();

  const [name, setName] = useState("");
  const [scope, setScope] = useState<KnowledgeScope | "">("");
  // sort_order 默认 0(未指定排序时后端按创建序展示)。
  const [sortOrder, setSortOrder] = useState("0");

  // 打开时播种默认 scope(第一个可用);关闭时重置。
  useEffect(() => {
    if (open) {
      setScope(availableScopes[0] ?? "");
      setName("");
      setSortOrder("0");
    }
  }, [open, availableScopes]);

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("请填写分类名称");
      return;
    }
    if (!scope) {
      toast.error("请选择分类层级");
      return;
    }

    // scope 联动构造:platform → 两者都不带(后端 scope=platform 推导 null/null);
    // group → group_id 默认 me.group_id(隐藏,group_admin 必有);store → tenant_id
    // 默认 me.tenant_id(隐藏,owner/group_admin 必有)。
    const payload: KnowledgeCategoryCreate = {
      name: trimmedName,
      scope,
      sort_order: Number(sortOrder) || 0,
    };
    if (scope === "group" && me?.group_id) payload.group_id = me.group_id;
    if (scope === "store" && me?.tenant_id) payload.tenant_id = me.tenant_id;

    try {
      await createMut.mutateAsync(payload);
      toast.success("已新建分类", trimmedName);
      onOpenChange(false);
    } catch (err) {
      toast.error("新建失败", apiErrorMessage(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建分类</DialogTitle>
          <DialogDescription>
            选择层级后录入分类名称。平台分类全平台可见,集团分类本集团可见,本店分类仅本店可见。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>分类层级</Label>
            <Select
              value={scope}
              onValueChange={(v) => setScope(v as KnowledgeScope)}
            >
              <SelectTrigger>
                <SelectValue placeholder="选择层级(platform/group/store)" />
              </SelectTrigger>
              <SelectContent>
                {availableScopes.map((s) => (
                  <SelectItem key={s} value={s}>
                    {SCOPE_LABEL[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>分类名称</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如 话术 / 产品说明 / FAQ"
            />
          </div>

          <div className="space-y-2">
            <Label>排序</Label>
            <Input
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              placeholder="数字越小越靠前"
            />
          </div>

          {/* scope 联动提示:group/store 会自动绑定当前集团/门店(隐藏字段)。 */}
          {scope === "group" && (
            <p className="text-xs text-muted-foreground">
              将绑定到当前集团。
            </p>
          )}
          {scope === "store" && (
            <p className="text-xs text-muted-foreground">
              将绑定到当前门店。
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={createMut.isPending}>
            {createMut.isPending ? "新建中…" : "确认新建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 编辑 Dialog:只改 name + sort_order(scope/ownership 不可改,对齐 KnowledgeCategoryUpdate)。
// ---------------------------------------------------------------------------

interface CategoryEditDialogProps {
  category: KnowledgeCategoryRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CategoryEditDialog({
  category,
  open,
  onOpenChange,
}: CategoryEditDialogProps) {
  const toast = useToast();
  const updateMut = useUpdateCategory();

  const [name, setName] = useState(category.name);
  const [sortOrder, setSortOrder] = useState(String(category.sort_order));

  // 打开时用当前 category 播种(切换 target 时重播种)。
  useEffect(() => {
    if (open) {
      setName(category.name);
      setSortOrder(String(category.sort_order));
    }
  }, [open, category]);

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("请填写分类名称");
      return;
    }
    // 只带 name + sort_order(对齐 KnowledgeCategoryUpdate;scope/group_id/tenant_id 不传)。
    const payload: KnowledgeCategoryUpdate = {
      name: trimmedName,
      sort_order: Number(sortOrder) || 0,
    };

    try {
      await updateMut.mutateAsync({ id: category.id, payload });
      toast.success("已更新分类", trimmedName);
      onOpenChange(false);
    } catch (err) {
      toast.error("更新失败", apiErrorMessage(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑分类</DialogTitle>
          <DialogDescription>
            只能改名称和排序。层级与归属创建后不可改(如需变更层级请新建后删除旧的)。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {/* 层级只读展示(scope 不可改)。 */}
          <div className="space-y-2">
            <Label>分类层级(不可改)</Label>
            <div className="flex items-center gap-2">
              <ScopeBadge scope={category.scope} />
              <span className="text-sm text-muted-foreground">
                {SCOPE_LABEL[category.scope]}层级
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <Label>分类名称</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="分类名称"
            />
          </div>

          <div className="space-y-2">
            <Label>排序</Label>
            <Input
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              placeholder="数字越小越靠前"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={updateMut.isPending}>
            {updateMut.isPending ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 删除 Dialog:二次确认(普通 Dialog 范式,镜像 distribution-list 撤回确认)。
// ---------------------------------------------------------------------------

interface CategoryDeleteDialogProps {
  category: KnowledgeCategoryRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CategoryDeleteDialog({
  category,
  open,
  onOpenChange,
}: CategoryDeleteDialogProps) {
  const toast = useToast();
  const deleteMut = useDeleteCategory();

  const handleDelete = async () => {
    try {
      await deleteMut.mutateAsync(category.id);
      toast.success("已删除分类", category.name);
      onOpenChange(false);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认删除分类</DialogTitle>
          <DialogDescription>
            确定删除分类「{category.name}」?删除后该分类名可重新使用(软删,
            已归档到此分类的文档不受影响)。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMut.isPending}
          >
            {deleteMut.isPending ? "删除中…" : "确认删除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
