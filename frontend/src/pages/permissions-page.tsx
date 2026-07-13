import { useMemo, useState } from "react";
import { Check, Loader2, Minus, RefreshCw } from "lucide-react";

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
import type { PermissionItem, Role } from "@/api/types";
import {
  useGrantRolePermission,
  usePermissionMatrix,
  useRevokeRolePermission,
} from "@/hooks/queries";
import { cn } from "@/lib/utils";

export function PermissionsPage() {
  const { me } = useAuth();
  const canManage = canManageUsers(me);
  const toast = useToast();

  const { data, isLoading, refetch, isFetching } = usePermissionMatrix();
  const grantMut = useGrantRolePermission();
  const revokeMut = useRevokeRolePermission();

  // Tracks the cell currently being toggled ("roleId:permCode") so we can show
  // a spinner and block double-clicks.
  const [pendingCell, setPendingCell] = useState<string | null>(null);

  // Group permissions by obj. Labels and ordering both come from the backend
  // catalogue (GET /permissions/matrix returns permissions ordered by code, and
  // each item carries its own obj_label/act_label), so the frontend keeps no
  // hardcoded label/sort table — the drift that existed here is gone.
  const grouped = useMemo(() => {
    const perms = data?.permissions ?? [];
    const byObj = new Map<string, PermissionItem[]>();
    const labelByObj = new Map<string, string>();
    for (const p of perms) {
      const list = byObj.get(p.obj) ?? [];
      list.push(p);
      byObj.set(p.obj, list);
      if (!labelByObj.has(p.obj)) labelByObj.set(p.obj, p.obj_label);
    }
    // Preserve catalogue order (already sorted by code on the backend); only
    // group, don't re-sort within a group.
    return [...byObj.keys()].map((obj) => ({
      obj,
      label: labelByObj.get(obj) ?? obj,
      items: byObj.get(obj) ?? [],
    }));
  }, [data?.permissions]);

  const roles: Role[] = data?.roles ?? [];

  async function toggle(role: Role, perm: PermissionItem, granted: boolean) {
    const cellKey = `${role.id}:${perm.code}`;
    if (pendingCell) return;
    setPendingCell(cellKey);
    try {
      if (granted) {
        await revokeMut.mutateAsync({
          roleId: role.id,
          permissionId: perm.id,
        });
        toast.success(`已撤销 ${role.name} 的 ${perm.code} 权限`);
      } else {
        await grantMut.mutateAsync({
          roleId: role.id,
          payload: { obj: perm.obj, act: perm.act },
        });
        toast.success(`已授予 ${role.name} 的 ${perm.code} 权限`);
      }
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setPendingCell(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">权限矩阵</h1>
          <p className="text-muted-foreground">
            角色 × 资源 × 动作的可视化视图。勾选表示该角色拥有此权限。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>完整权限矩阵</CardTitle>
          <CardDescription>
            数据来自后端 SCD2 当前态（GET /permissions/matrix）。点格子可授予/撤销权限，实时生效。
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!canManage && (
            <p className="mb-4 text-sm text-muted-foreground">
              当前为只读视图（需要 owner / admin 权限才能编辑）。
            </p>
          )}

          {isLoading ? (
            <p className="py-8 text-center text-muted-foreground">加载中…</p>
          ) : roles.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">
              暂无角色数据。
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="sticky left-0 bg-background">
                      资源 / 动作
                    </TableHead>
                    {roles.map((r) => (
                      <TableHead key={r.id} className="text-center">
                        <div className="flex flex-col items-center gap-1">
                          <span>{r.name}</span>
                          {r.is_system && (
                            <Badge variant="secondary" className="text-[10px]">
                              系统
                            </Badge>
                          )}
                        </div>
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {grouped.map((group) =>
                    group.items.map((perm, idx) => (
                      <TableRow key={perm.code}>
                        <TableCell
                          className={cn(
                            "sticky left-0 bg-background font-medium",
                            idx === 0 && "border-t-2"
                          )}
                        >
                          {idx === 0 && (
                            <span className="mr-2 font-semibold text-foreground">
                              {group.label}
                            </span>
                          )}
                          <span className="text-muted-foreground">
                            {perm.act_label}
                          </span>
                        </TableCell>
                        {roles.map((role) => {
                          const granted =
                            data?.matrix[role.code]?.[perm.code] ?? false;
                          const cellKey = `${role.id}:${perm.code}`;
                          const busy = pendingCell === cellKey;
                          return (
                            <PermCell
                              key={role.id}
                              granted={granted}
                              busy={busy}
                              editable={canManage}
                              onClick={() => toggle(role, perm, granted)}
                            />
                          );
                        })}
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}
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
          {canManage && (
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded bg-primary/10 text-primary">
                <Check className="h-3 w-3" />
              </span>
              <span>点击格子可切换</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PermCell({
  granted,
  busy,
  editable,
  onClick,
}: {
  granted: boolean;
  busy: boolean;
  editable: boolean;
  onClick: () => void;
}) {
  return (
    <TableCell className="text-center">
      <button
        type="button"
        disabled={!editable || busy}
        onClick={onClick}
        aria-label={granted ? "允许（点击撤销）" : "拒绝（点击授予）"}
        className={cn(
          "inline-flex h-6 w-6 items-center justify-center rounded text-white transition-colors",
          granted ? "bg-emerald-500" : "bg-muted text-muted-foreground",
          editable &&
            !busy &&
            "cursor-pointer hover:ring-2 hover:ring-primary/40",
          !editable && "cursor-default"
        )}
      >
        {busy ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : granted ? (
          <Check className="h-3 w-3" />
        ) : (
          <Minus className="h-3 w-3" />
        )}
      </button>
    </TableCell>
  );
}
