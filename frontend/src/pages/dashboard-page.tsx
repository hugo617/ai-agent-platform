import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, ShieldCheck, Users, Zap } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { useAgents, useCreateTenant, useTenants } from "@/hooks/queries";

export function DashboardPage() {
  const toast = useToast();
  const { me } = useAuth();
  const { data: agents } = useAgents();
  const { data: tenants, isError: tenantsError } = useTenants();
  const createTenantMut = useCreateTenant();

  const [tenantDialogOpen, setTenantDialogOpen] = useState(false);
  const [tenantName, setTenantName] = useState("");

  const handleCreateTenant = async () => {
    if (!tenantName.trim()) {
      toast.error("请填写租户名称");
      return;
    }
    try {
      await createTenantMut.mutateAsync(tenantName.trim());
      toast.success("已创建租户", tenantName.trim());
      setTenantName("");
      setTenantDialogOpen(false);
    } catch (err) {
      toast.error("创建失败", apiErrorMessage(err));
    }
  };

  const stats = [
    { label: "当前角色", value: me?.roles?.[0] ?? "-", icon: ShieldCheck },
    { label: "智能体数量", value: agents?.length ?? 0, icon: Bot },
    { label: "租户 ID", value: me?.tenant_id?.slice(0, 8) ?? "-", icon: Users },
    { label: "API 状态", value: "在线", icon: Zap },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">概览</h1>
        <p className="text-muted-foreground">
          欢迎回来，{me?.email ?? me?.user_id}。这是你的智能体云平台控制台。
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {s.label}
              </CardTitle>
              <s.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>你的权限</CardTitle>
            <CardDescription>当前角色拥有的操作权限</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {me?.roles?.map((role) => (
              <Badge key={role} variant="success">
                {role}
              </Badge>
            )) ?? <span className="text-sm text-muted-foreground">加载中…</span>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>我的租户</CardTitle>
            <CardDescription>你所属的租户列表</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {tenantsError ? (
              <p className="text-sm text-muted-foreground">
                暂无租户数据。
              </p>
            ) : (
              (tenants ?? []).map((t) => (
                <div key={t.id} className="flex items-center justify-between text-sm">
                  <span className="font-medium">{t.name}</span>
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                    {t.id.slice(0, 8)}
                  </code>
                </div>
              ))
            )}
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-full"
              onClick={() => setTenantDialogOpen(true)}
            >
              创建租户
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>快速操作</CardTitle>
            <CardDescription>常用入口</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            <Link to="/agents" className="text-primary hover:underline">
              → 管理智能体
            </Link>
            <Link to="/roles" className="text-primary hover:underline">
              → 配置角色
            </Link>
            <Link to="/permissions" className="text-primary hover:underline">
              → 查看权限矩阵
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* create tenant dialog */}
      <Dialog open={tenantDialogOpen} onOpenChange={setTenantDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>创建租户</DialogTitle>
            <DialogDescription>
              创建一个新的租户。创建后你将成为该租户的 owner。
              （注意：当前登录会话仍绑定原租户，需重新登录切换。）
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>租户名称</Label>
            <Input
              value={tenantName}
              onChange={(e) => setTenantName(e.target.value)}
              placeholder="如：我的新团队"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTenantDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleCreateTenant} disabled={createTenantMut.isPending}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
