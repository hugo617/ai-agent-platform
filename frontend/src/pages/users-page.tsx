import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Pencil, Plus, Trash2, UserCog, Users as UsersIcon } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/components/auth/auth-context";
import {
  useAddMember,
  useMembers,
  useRemoveMember,
  useUpdateMember,
} from "@/hooks/queries";
import { apiErrorMessage } from "@/api/client";
import type { Member } from "@/api/types";

const ROLES = ["owner", "admin", "member"];

const addSchema = z.object({
  user_id: z.string().min(1, "用户 ID 不能为空").max(128),
  role: z.string().default("member"),
  email: z.string().email("邮箱格式不正确").or(z.literal("")).default(""),
  display_name: z.string().default(""),
});

type AddValues = z.input<typeof addSchema>;

export function UsersPage() {
  const { me } = useAuth();
  const { data: members, isLoading } = useMembers();
  const addMut = useAddMember();
  const updateMut = useUpdateMember();
  const removeMut = useRemoveMember();
  const toast = useToast();

  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);

  const addForm = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: { user_id: "", role: "member", email: "", display_name: "" },
  });

  const openAdd = () => {
    addForm.reset({ user_id: "", role: "member", email: "", display_name: "" });
    setAddOpen(true);
  };

  const onAdd = async (values: AddValues) => {
    try {
      await addMut.mutateAsync({
        user_id: values.user_id,
        role: values.role ?? "member",
        email: values.email || null,
        display_name: values.display_name || null,
      });
      toast.success("已添加成员", values.user_id);
      setAddOpen(false);
    } catch (err) {
      toast.error("添加失败", apiErrorMessage(err));
    }
  };

  const openEdit = (m: Member) => setEditing(m);

  const onEditRole = async (role: string) => {
    if (!editing) return;
    try {
      await updateMut.mutateAsync({ userId: editing.user_id, payload: { role } });
      toast.success("已更新角色", `${editing.user_id} → ${role}`);
      setEditing(null);
    } catch (err) {
      toast.error("更新失败", apiErrorMessage(err));
    }
  };

  const handleRemove = async (m: Member) => {
    if (!confirm(`确认从本租户移除成员「${m.user_id}」？`)) return;
    try {
      await removeMut.mutateAsync(m.user_id);
      toast.success("已移除", m.user_id);
    } catch (err) {
      toast.error("移除失败", apiErrorMessage(err));
    }
  };

  const roleBadgeVariant = (role: string) => {
    if (role === "owner") return "success" as const;
    if (role === "admin") return "default" as const;
    return "secondary" as const;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">用户</h1>
          <p className="text-muted-foreground">
            管理当前租户的成员与角色（数据由后端 casbin 实时同步）
          </p>
        </div>
        <Button onClick={openAdd}>
          <Plus className="mr-2 h-4 w-4" /> 添加成员
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>成员列表</CardTitle>
          <CardDescription>
            {members ? `共 ${members.length} 人` : "加载中…"} · 当前角色：{me?.roles?.[0] ?? "-"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !members?.length ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <UsersIcon className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">还没有成员</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>用户 ID</TableHead>
                  <TableHead>邮箱</TableHead>
                  <TableHead>角色</TableHead>
                  <TableHead>加入时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.user_id}>
                    <TableCell className="font-medium">{m.user_id}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {m.email ?? "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={roleBadgeVariant(m.role)}>{m.role}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {m.joined_at
                        ? new Date(m.joined_at).toLocaleString()
                        : "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(m)}
                        title="改角色"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRemove(m)}
                        title="移除"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Add member dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加成员</DialogTitle>
            <DialogDescription>
              把一个已存在的用户（按 ID）加入当前租户并分配角色
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={addForm.handleSubmit(onAdd)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="user_id">用户 ID</Label>
              <Input id="user_id" placeholder="如：alice" {...addForm.register("user_id")} />
              {addForm.formState.errors.user_id && (
                <p className="text-xs text-destructive">
                  {addForm.formState.errors.user_id.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">邮箱（可选）</Label>
              <Input
                id="email"
                type="email"
                placeholder="alice@example.com"
                {...addForm.register("email")}
              />
              {addForm.formState.errors.email && (
                <p className="text-xs text-destructive">
                  {addForm.formState.errors.email.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="display_name">显示名（可选）</Label>
              <Input
                id="display_name"
                placeholder="Alice"
                {...addForm.register("display_name")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">角色</Label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                {...addForm.register("role")}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={addMut.isPending}>
                添加
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit role dialog */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserCog className="h-5 w-5" />
              修改角色：{editing?.user_id}
            </DialogTitle>
            <DialogDescription>选择新的角色</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {ROLES.map((r) => (
              <Button
                key={r}
                variant={editing?.role === r ? "default" : "outline"}
                className="justify-start"
                onClick={() => onEditRole(r)}
                disabled={updateMut.isPending}
              >
                <Badge variant={roleBadgeVariant(r)}>{r}</Badge>
                <span className="ml-2 text-muted-foreground">
                  {r === "owner" && "全部权限"}
                  {r === "admin" && "管理权限（不含计费）"}
                  {r === "member" && "只读 + 对话"}
                </span>
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
