import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Crown, UserCog } from "lucide-react";

// Default roles seeded by the backend (permission_service.seed_tenant_defaults).
// In a later phase this list will be fetched from a /roles endpoint.
const ROLES = [
  {
    name: "owner",
    description: "租户所有者，拥有全部权限",
    icon: Crown,
    permissions: [
      "agents:read",
      "agents:create",
      "agents:update",
      "agents:delete",
      "conversations:read",
      "conversations:create",
      "conversations:chat",
    ],
  },
  {
    name: "member",
    description: "普通成员，只读 + 对话",
    icon: UserCog,
    permissions: [
      "agents:read",
      "conversations:read",
      "conversations:create",
      "conversations:chat",
    ],
  },
];

export function RolesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">角色</h1>
        <p className="text-muted-foreground">
          当前租户的角色定义。角色由后端 pycasbin RBAC 模型驱动。
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {ROLES.map((role) => (
          <Card key={role.name}>
            <CardHeader>
              <div className="flex items-center gap-3">
                <role.icon className="h-5 w-5 text-primary" />
                <div>
                  <CardTitle className="text-lg">{role.name}</CardTitle>
                  <CardDescription>{role.description}</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {role.permissions.map((p) => (
                  <Badge key={p} variant="secondary">
                    {p}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>说明</CardTitle>
          <CardDescription>MVP 阶段的角色策略来源</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>概念</TableHead>
                <TableHead>在后端的位置</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium">角色 → 权限映射</TableCell>
                <TableCell className="text-muted-foreground">
                  <code>app/services/permission_service.py</code>
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">权限模型定义</TableCell>
                <TableCell className="text-muted-foreground">
                  <code>casbin_model.conf</code>（RBAC + domain）
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">策略存储</TableCell>
                <TableCell className="text-muted-foreground">
                  PostgreSQL <code>casbin_rule</code> 表
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
