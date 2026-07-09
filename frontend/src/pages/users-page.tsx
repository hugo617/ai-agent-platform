import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  KeyRound,
  Lock,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  Unlock,
  UserCheck,
  UserPlus,
  Users as UsersIcon,
  UserX,
} from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Pagination } from "@/components/ui/pagination";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import type { UserFilters, UserFull, UserStatistics, UserStatus } from "@/api/types";
import {
  useChangeUserStatus,
  useCreateUser,
  useDeleteUser,
  useResetUserPassword,
  useRoleLabels,
  useUpdateUser,
  useUserStatistics,
  useUsers,
} from "@/hooks/queries";

const STATUSES: { value: UserStatus; label: string }[] = [
  { value: "active", label: "活跃" },
  { value: "inactive", label: "未激活" },
  { value: "locked", label: "已锁定" },
];

const statusBadge = (status: UserStatus) => {
  if (status === "active") return <Badge variant="success">活跃</Badge>;
  if (status === "locked") return <Badge variant="destructive">已锁定</Badge>;
  return <Badge variant="secondary">未激活</Badge>;
};

const roleBadgeVariant = (code: string) => {
  if (code === "owner") return "success" as const;
  if (code === "admin") return "default" as const;
  return "secondary" as const;
};

const fmt = (s: string | null): string =>
  s ? new Date(s).toLocaleString() : "-";

// ---------- form schema ----------
const formSchema = z.object({
  username: z.string().min(2, "用户名至少 2 个字符").max(50),
  email: z.string().email("邮箱格式不正确"),
  password: z.string().optional(),
  real_name: z.string().optional(),
  phone: z.string().optional(),
  role: z.string(),
  status: z.enum(["active", "inactive", "locked"]),
});
type FormValues = z.input<typeof formSchema>;

const EMPTY_FORM = {
  username: "",
  email: "",
  password: "",
  real_name: "",
  phone: "",
  role: "member" as const,
  status: "active" as const,
} satisfies FormValues;

export function UsersPage() {
  const toast = useToast();
  const { me } = useAuth();
  const isSuperAdmin = me?.platform_role === "super_admin";

  // ---- filters / pagination state ----
  const [filters, setFilters] = useState<UserFilters>({
    page: 1,
    limit: 10,
    search: "",
    status: "all",
    role: "all",
    sort_by: "created_at",
    sort_order: "desc",
  });

  // debounce-free live search via a separate input state
  const [searchInput, setSearchInput] = useState(filters.search ?? "");

  const { data, isLoading } = useUsers(filters);
  const { data: stats } = useUserStatistics();
  const { data: roleLabels } = useRoleLabels();

  const createMut = useCreateUser();
  const updateMut = useUpdateUser();
  const deleteMut = useDeleteUser();
  const statusMut = useChangeUserStatus();
  const resetPwMut = useResetUserPassword();

  // ---- dialogs ----
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<UserFull | null>(null);
  const [resetTarget, setResetTarget] = useState<UserFull | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserFull | null>(null);
  const [newPassword, setNewPassword] = useState("");

  // ---- row selection (batch ops) ----
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const users = data?.items ?? [];
  const allSelected = users.length > 0 && users.every((u) => selected.has(u.id));
  const toggleAll = (checked: boolean | "indeterminate") => {
    setSelected(checked === true ? new Set(users.map((u) => u.id)) : new Set());
  };
  const toggleOne = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  // Clear row selection whenever the visible result set changes (filters,
  // search, page, OR sort) so the "已选 N 项" count never references users that
  // aren't on screen. Omitting sort here left stale ids checked after a re-sort,
  // which would target the wrong users in any future batch action.
  useEffect(() => {
    setSelected(new Set());
  }, [
    filters.search,
    filters.status,
    filters.role,
    filters.page,
    filters.sort_by,
    filters.sort_order,
  ]);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(EMPTY_FORM);
    setFormOpen(true);
  };

  const openEdit = (u: UserFull) => {
    setEditing(u);
    form.reset({
      username: u.username ?? "",
      email: u.email ?? "",
      password: "",
      real_name: u.real_name ?? "",
      phone: u.phone ?? "",
      role: u.role?.code ?? "member",
      status: u.status,
    });
    setFormOpen(true);
  };

  const onSubmit = async (values: FormValues) => {
    try {
      if (editing) {
        // Password changes go through the dedicated /reset-password endpoint
        // (UserUpdate has no password field), so strip it here.
        const { password: _pw, ...rest } = values;
        await updateMut.mutateAsync({
          id: editing.id,
          payload: rest,
        });
        toast.success("已更新", editing.username ?? editing.id);
      } else {
        if (!values.password || values.password.length < 6) {
          toast.error("密码至少 6 位");
          return;
        }
        await createMut.mutateAsync({
          username: values.username,
          email: values.email,
          password: values.password,
          real_name: values.real_name || undefined,
          phone: values.phone || undefined,
          role: values.role,
          status: values.status,
          organization_ids: [],
        });
        toast.success("已创建用户", values.username);
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
      toast.success("已删除", deleteTarget.username ?? deleteTarget.id);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  const handleStatus = async (u: UserFull, status: UserStatus) => {
    try {
      await statusMut.mutateAsync({ id: u.id, status });
      toast.success("状态已更新", `${u.username} → ${status}`);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };

  const handleResetPassword = async () => {
    if (!resetTarget) return;
    if (newPassword.length < 6) {
      toast.error("密码至少 6 位");
      return;
    }
    try {
      await resetPwMut.mutateAsync({ id: resetTarget.id, password: newPassword });
      toast.success("密码已重置", resetTarget.username ?? resetTarget.id);
      setResetTarget(null);
      setNewPassword("");
    } catch (err) {
      toast.error("重置失败", apiErrorMessage(err));
    }
  };

  const applySearch = () =>
    setFilters((f) => ({ ...f, search: searchInput.trim() || undefined, page: 1 }));

  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="space-y-6">
      <PageHeader stats={stats} onCreate={openCreate} isSuperAdmin={isSuperAdmin} />

      <Filters
        searchInput={searchInput}
        onSearchChange={setSearchInput}
        onSearchSubmit={applySearch}
        filters={filters}
        setFilters={setFilters}
        roleOptions={roleLabels ?? []}
      />

      <Card>
        <CardHeader>
          <CardTitle>用户列表</CardTitle>
          <CardDescription>
            共 {total} 人 · 第 {filters.page} / {totalPages} 页
            {selected.size > 0 && ` · 已选 ${selected.size} 项`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">加载中…</div>
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <UsersIcon className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无用户，点击右上角「新增用户」</p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
                    </TableHead>
                    <TableHead>用户</TableHead>
                    <TableHead>邮箱</TableHead>
                    <TableHead>角色</TableHead>
                    {isSuperAdmin && <TableHead>所属租户</TableHead>}
                    <TableHead>状态</TableHead>
                    <TableHead>最后登录</TableHead>
                    <TableHead>创建时间</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell>
                        <Checkbox
                          checked={selected.has(u.id)}
                          onCheckedChange={() => toggleOne(u.id)}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Avatar name={u.real_name || u.username} src={u.avatar} size="sm" />
                          <div className="flex flex-col">
                            <span className="font-medium">{u.username ?? u.id}</span>
                            {u.real_name && (
                              <span className="text-xs text-muted-foreground">{u.real_name}</span>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{u.email ?? "-"}</TableCell>
                      <TableCell>
                        {u.role ? (
                          <Badge variant={roleBadgeVariant(u.role.code)}>{u.role.name}</Badge>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                      {isSuperAdmin && (
                        <TableCell className="text-muted-foreground">
                          {u.tenant_name ?? <span className="italic">无租户</span>}
                        </TableCell>
                      )}
                      <TableCell>{statusBadge(u.status)}</TableCell>
                      <TableCell className="text-muted-foreground">{fmt(u.last_login_at)}</TableCell>
                      <TableCell className="text-muted-foreground">{fmt(u.created_at)}</TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => openEdit(u)}>
                              <Pencil className="h-4 w-4" /> 编辑
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setResetTarget(u)}>
                              <KeyRound className="h-4 w-4" /> 重置密码
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            {u.status === "locked" ? (
                              <DropdownMenuItem onClick={() => handleStatus(u, "active")}>
                                <Unlock className="h-4 w-4" /> 解锁
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem onClick={() => handleStatus(u, "locked")}>
                                <Lock className="h-4 w-4" /> 锁定
                              </DropdownMenuItem>
                            )}
                            {u.status === "active" ? (
                              <DropdownMenuItem onClick={() => handleStatus(u, "inactive")}>
                                <UserX className="h-4 w-4" /> 停用
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem onClick={() => handleStatus(u, "active")}>
                                <UserCheck className="h-4 w-4" /> 启用
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteTarget(u)}
                            >
                              <Trash2 className="h-4 w-4" /> 删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="mt-4 flex items-center justify-end">
                <Pagination
                  page={filters.page ?? 1}
                  totalPages={totalPages}
                  onPageChange={(p) => setFilters((f) => ({ ...f, page: p }))}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Create / edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑用户" : "新增用户"}</DialogTitle>
            <DialogDescription>
              {editing
                ? `修改 ${editing.username ?? editing.id} 的信息`
                : "创建一个本地账号并加入当前租户"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="用户名" error={form.formState.errors.username?.message}>
                <Input {...form.register("username")} />
              </Field>
              <Field label="邮箱" error={form.formState.errors.email?.message}>
                <Input type="email" {...form.register("email")} />
              </Field>
              {!editing && (
                <Field
                  label="密码"
                  error={form.formState.errors.password?.message}
                >
                  <Input type="password" {...form.register("password")} />
                </Field>
              )}
              <Field label="真实姓名">
                <Input {...form.register("real_name")} />
              </Field>
              <Field label="手机号">
                <Input {...form.register("phone")} />
              </Field>
              <Field label="角色">
                <Select
                  value={form.watch("role")}
                  onValueChange={(v) => form.setValue("role", v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择角色" />
                  </SelectTrigger>
                  <SelectContent>
                    {(roleLabels ?? []).map((r) => (
                      <SelectItem key={r.code} value={r.code}>
                        {r.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="状态">
                <Select
                  value={form.watch("status")}
                  onValueChange={(v) => form.setValue("status", v as UserStatus)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => (
                      <SelectItem key={s.value} value={s.value}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={createMut.isPending || updateMut.isPending}>
                {editing ? "保存" : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reset password dialog */}
      <Dialog
        open={!!resetTarget}
        onOpenChange={(o) => {
          if (!o) {
            setResetTarget(null);
            setNewPassword("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重置密码</DialogTitle>
            <DialogDescription>
              为 {resetTarget?.username ?? resetTarget?.id} 设置新密码
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="new_password">新密码</Label>
            <Input
              id="new_password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="至少 6 位"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetTarget(null)}>
              取消
            </Button>
            <Button onClick={handleResetPassword} disabled={resetPwMut.isPending}>
              <RotateCcw className="mr-2 h-4 w-4" /> 重置
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定删除用户「{deleteTarget?.username ?? deleteTarget?.id}」？该操作为软删除，
              可在数据库恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteMut.isPending}>
              <Trash2 className="mr-2 h-4 w-4" /> 删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------- sub-components ----------------

function PageHeader({
  stats,
  onCreate,
  isSuperAdmin = false,
}: {
  stats: UserStatistics | undefined;
  onCreate: () => void;
  isSuperAdmin?: boolean;
}) {
  const cards = [
    { label: "用户总数", value: stats?.total ?? 0, icon: UsersIcon, color: "text-blue-500" },
    { label: "活跃", value: stats?.active ?? 0, icon: UserCheck, color: "text-emerald-500" },
    { label: "锁定", value: stats?.locked ?? 0, icon: Lock, color: "text-rose-500" },
    { label: "本月新增", value: stats?.new_this_month ?? 0, icon: UserPlus, color: "text-amber-500" },
  ];
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">用户</h1>
          <p className="text-muted-foreground">
            {isSuperAdmin ? "管理全平台用户账号、角色与状态" : "管理当前租户的用户账号、角色与状态"}
          </p>
        </div>
        <Button onClick={onCreate}>
          <Plus className="mr-2 h-4 w-4" /> 新增用户
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {cards.map((c) => (
          <Card key={c.label}>
            <CardContent className="flex items-center gap-3 p-4">
              <c.icon className={`h-8 w-8 ${c.color}`} />
              <div>
                <div className="text-2xl font-bold">{c.value}</div>
                <div className="text-xs text-muted-foreground">{c.label}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Filters({
  searchInput,
  onSearchChange,
  onSearchSubmit,
  filters,
  setFilters,
  roleOptions,
}: {
  searchInput: string;
  onSearchChange: (v: string) => void;
  onSearchSubmit: () => void;
  filters: UserFilters;
  setFilters: React.Dispatch<React.SetStateAction<UserFilters>>;
  roleOptions: { id: string; name: string; code: string }[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSearchSubmit();
        }}
        className="flex w-full max-w-sm items-center gap-2"
      >
        <Input
          placeholder="搜索用户名 / 邮箱 / 手机 / 真实姓名"
          value={searchInput}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <Button type="submit" variant="secondary">
          搜索
        </Button>
      </form>
      <Select
        value={filters.status ?? "all"}
        onValueChange={(v) =>
          setFilters((f) => ({ ...f, status: v as UserStatus | "all", page: 1 }))
        }
      >
        <SelectTrigger className="w-32">
          <SelectValue placeholder="状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部状态</SelectItem>
          {STATUSES.map((s) => (
            <SelectItem key={s.value} value={s.value}>
              {s.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.role ?? "all"}
        onValueChange={(v) => setFilters((f) => ({ ...f, role: v, page: 1 }))}
      >
        <SelectTrigger className="w-32">
          <SelectValue placeholder="角色" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部角色</SelectItem>
          {roleOptions.map((r) => (
            <SelectItem key={r.code} value={r.code}>
              {r.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.sort_order ?? "desc"}
        onValueChange={(v) =>
          setFilters((f) => ({ ...f, sort_order: v as "asc" | "desc" }))
        }
      >
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="desc">最新优先</SelectItem>
          <SelectItem value="asc">最早优先</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

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
