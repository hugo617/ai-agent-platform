import { Check, Minus } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

// The permission matrix is derived from the backend's seed defaults.
// Source of truth: app/services/permission_service.PermissionService.seed_tenant_defaults
const OBJECTS = ["agents", "conversations"];
const ACTIONS = ["read", "create", "update", "delete", "chat"];

type Matrix = Record<string, Record<string, boolean>>;

const MATRIX: Record<string, Matrix> = {
  owner: {
    agents: { read: true, create: true, update: true, delete: true, chat: false },
    conversations: { read: true, create: true, update: false, delete: false, chat: true },
  },
  member: {
    agents: { read: true, create: false, update: false, delete: false, chat: false },
    conversations: { read: true, create: true, update: false, delete: false, chat: true },
  },
};

export function PermissionsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">权限矩阵</h1>
        <p className="text-muted-foreground">
          角色 × 资源 × 动作的可视化视图。勾选表示该角色拥有此权限。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>完整权限矩阵</CardTitle>
          <CardDescription>
            数据来自后端 pycasbin 策略（owner / member 默认 seed）
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>资源</TableHead>
                <TableHead>动作</TableHead>
                <TableHead className="text-center">owner</TableHead>
                <TableHead className="text-center">member</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {OBJECTS.map((obj) =>
                ACTIONS.map((act) => {
                  const ownerHas = MATRIX.owner[obj]?.[act] ?? false;
                  const memberHas = MATRIX.member[obj]?.[act] ?? false;
                  return (
                    <TableRow key={`${obj}-${act}`}>
                      <TableCell className="font-medium">
                        {obj === "agents" && "智能体"}
                        {obj === "conversations" && "对话"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{act}</TableCell>
                      <PermCell on={ownerHas} />
                      <PermCell on={memberHas} />
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>图例</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded bg-emerald-500 text-white">
              <Check className="h-3 w-3" />
            </span>
            <span>允许</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded bg-muted text-muted-foreground">
              <Minus className="h-3 w-3" />
            </span>
            <span>拒绝</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PermCell({ on }: { on: boolean }) {
  return (
    <TableCell className="text-center">
      <span
        className={cn(
          "inline-flex h-5 w-5 items-center justify-center rounded text-white",
          on ? "bg-emerald-500" : "bg-muted text-muted-foreground"
        )}
      >
        {on ? <Check className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
      </span>
    </TableCell>
  );
}
