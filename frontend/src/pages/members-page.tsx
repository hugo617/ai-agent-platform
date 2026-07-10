import { useState } from "react";
import { MoreHorizontal, Trash2, UserPlus, Users } from "lucide-react";

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
import type { Member } from "@/api/types";
import {
  useAddMember,
  useMembers,
  useRemoveMember,
  useUpdateMember,
} from "@/hooks/queries";

const fmt = (s: string | null): string =>
  s ? new Date(s).toLocaleString() : "-";

const ROLES = ["owner", "admin", "member"];

const ROLE_VARIANT: Record<string, "default" | "success" | "secondary"> = {
  owner: "default",
  admin: "success",
  member: "secondary",
};

export function MembersPage() {
  const toast = useToast();
  const { me } = useAuth();
  const canManage = canManageUsers(me);

  const { data: members, isLoading } = useMembers();
  const addMut = useAddMember();
  const updateMut = useUpdateMember();
  const removeMut = useRemoveMember();

  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);

  // add-member form state (simple local state; few fields)
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("member");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");

  const resetForm = () => {
    setUserId("");
    setRole("member");
    setEmail("");
    setDisplayName("");
  };

  const openAdd = () => {
    resetForm();
    setAddOpen(true);
  };

  const handleAdd = async () => {
    if (!userId.trim()) {
      toast.error("请填写用户 ID");
      return;
    }
    try {
      await addMut.mutateAsync({
        user_id: userId.trim(),
        role,
        email: email.trim() || null,
        display_name: displayName.trim() || null,
      });
      toast.success("已添加成员", userId.trim());
      setAddOpen(false);
    } catch (err) {
      toast.error("添加失败", apiErrorMessage(err));
    }
  };

  const handleChangeRole = async (m: Member, newRole: string) => {
    if (newRole === m.role) return;
    try {
      await updateMut.mutateAsync({ userId: m.user_id, payload: { role: newRole } });
      toast.success("已修改角色", `${m.email ?? m.user_id} → ${newRole}`);
    } catch (err) {
      toast.error("修改失败", apiErrorMessage(err));
    }
  };

  const handleRemove = async () => {
    if (!removeTarget) return;
    try {
      await removeMut.mutateAsync(removeTarget.user_id);
      toast.success("已移除成员", removeTarget.email ?? removeTarget.user_id);
      setRemoveTarget(null);
    } catch (err) {
      toast.error("移除失败", apiErrorMessage(err));
    }
  };

  const list = members ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">成员</h1>
          <p className="text-muted-foreground">
            管理当前租户的成员、角色与访问权限。
          </p>
        </div>
        {canManage && (
          <Button onClick={openAdd}>
            <UserPlus className="mr-2 h-4 w-4" /> 添加成员
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>成员列表</CardTitle>
          <CardDescription>共 {list.length} 名成员</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : list.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Users className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                暂无成员，点击右上角「添加成员」
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>用户 ID</TableHead>
                  <TableHead>邮箱</TableHead>
                  <TableHead>显示名</TableHead>
                  <TableHead>角色</TableHead>
                  <TableHead>加入时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((m) => (
                  <TableRow key={m.user_id}>
                    <TableCell>
                      <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                        {m.user_id.slice(0, 12)}
                      </code>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {m.email ?? "-"}
                    </TableCell>
                    <TableCell>{m.display_name ?? "-"}</TableCell>
                    <TableCell>
                      <Badge variant={ROLE_VARIANT[m.role] ?? "secondary"}>
                        {m.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(m.joined_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {/* Change role submenu items */}
                          {canManage &&
                            ROLES.filter((r) => r !== m.role).map((r) => (
                              <DropdownMenuItem
                                key={r}
                                onClick={() => handleChangeRole(m, r)}
                              >
                                改为 {r}
                              </DropdownMenuItem>
                            ))}
                          {canManage && <DropdownMenuSeparator />}
                          {canManage && (
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setRemoveTarget(m)}
                            >
                              <Trash2 className="h-4 w-4" /> 移除成员
                            </DropdownMenuItem>
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

      {/* add member dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>添加成员</DialogTitle>
            <DialogDescription>
              将一个已注册的用户加入当前租户并分配角色。需要填写用户的 ID。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Field label="用户 ID">
              <Input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="已注册用户的 ID"
              />
            </Field>
            <Field label="角色">
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="邮箱（可选）">
                <Input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field label="显示名（可选）">
                <Input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </Field>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              取消
            </Button>
            <Button onClick={handleAdd} disabled={addMut.isPending}>
              添加
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* remove confirm dialog */}
      <Dialog
        open={!!removeTarget}
        onOpenChange={(o) => !o && setRemoveTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认移除</DialogTitle>
            <DialogDescription>
              确定将「{removeTarget?.email ?? removeTarget?.user_id}」移出当前租户？
              该用户将无法再访问此租户的资源。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoveTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleRemove}
              disabled={removeMut.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" /> 移除
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
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
