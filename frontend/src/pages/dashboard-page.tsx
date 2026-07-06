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
import { useAuth } from "@/components/auth/auth-context";
import { useAgents } from "@/hooks/queries";

export function DashboardPage() {
  const { me } = useAuth();
  const { data: agents } = useAgents();

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
          欢迎回来，{me?.email ?? me?.user_id}。这是你的权限管理控制台。
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

      <div className="grid gap-4 lg:grid-cols-2">
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
    </div>
  );
}
