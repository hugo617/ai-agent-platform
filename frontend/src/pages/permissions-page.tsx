import { useMemo, useState } from "react";
import { Check, Loader2, Lock, Minus, RefreshCw, Shield } from "lucide-react";

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
import { hasPermission } from "@/lib/permission";
import type { DataScope, PermissionItem, Role } from "@/api/types";
import {
  useGrantRolePermission,
  usePermissionMatrix,
  useRevokeRolePermission,
  useUpdateRole,
} from "@/hooks/queries";
import { cn } from "@/lib/utils";

// data_scope 四档中文显示 + 简短说明(plan §Step5)。与后端 DATA_SCOPE_PATTERN
// (app/schemas/rbac.py)对齐;label 由前端给出(后端只存枚举字符串)。
const DATA_SCOPE_OPTIONS: { value: DataScope; label: string; hint: string }[] = [
  { value: "all", label: "全部", hint: "平台级,无过滤(仅超管/总部)" },
  { value: "tenant", label: "本租户", hint: "本门店全部数据(默认)" },
  { value: "group", label: "本组织", hint: "所属组织下各门店" },
  { value: "self", label: "仅自己", hint: "仅本人创建的数据" },
];

export function PermissionsPage() {
  const { me } = useAuth();
  const isSuperAdmin = me?.platform_role === "super_admin";
  // Editing the matrix requires roles:update (the same perm the backend's
  // grant/revoke endpoints check). super_admin bypasses via hasPermission.
  const canManage = hasPermission(me, "roles", "update");
  const toast = useToast();

  const { data, isLoading, refetch, isFetching } = usePermissionMatrix();
  const grantMut = useGrantRolePermission();
  const revokeMut = useRevokeRolePermission();
  const updateRoleMut = useUpdateRole();

  // Tracks the cell currently being toggled ("roleId:permCode") so we can show
  // a spinner and block double-clicks.
  const [pendingCell, setPendingCell] = useState<string | null>(null);
  // Tracks the role whose data_scope is being saved ("roleId") — same reason.
  const [pendingScope, setPendingScope] = useState<string | null>(null);

  // Group permissions into two sections — menu (UX visibility) on top, api
  // (backend authorization) below — and within each by obj. Labels and ordering
  // come from the backend catalogue (GET /permissions/matrix returns perms
  // ordered by code, each carrying its own obj_label/act_label/type), so the
  // frontend keeps no hardcoded label/sort table.
  const sections = useMemo(() => {
    const perms = data?.permissions ?? [];
    const buildGroups = (items: PermissionItem[]) => {
      const byObj = new Map<string, PermissionItem[]>();
      const labelByObj = new Map<string, string>();
      for (const p of items) {
        const list = byObj.get(p.obj) ?? [];
        list.push(p);
        byObj.set(p.obj, list);
        if (!labelByObj.has(p.obj)) labelByObj.set(p.obj, p.obj_label);
      }
      return [...byObj.keys()].map((obj) => ({
        obj,
        label: labelByObj.get(obj) ?? obj,
        items: byObj.get(obj) ?? [],
      }));
    };
    return [
      { type: "menu", title: "菜单权限", subtitle: "决定角色能否看到对应菜单/页面", groups: buildGroups(perms.filter((p) => p.type === "menu")) },
      { type: "api", title: "操作权限", subtitle: "决定角色能否调用对应后端接口(硬安全边界)", groups: buildGroups(perms.filter((p) => p.type !== "menu")) },
    ];
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

  async function changeScope(role: Role, next: DataScope) {
    if (next === role.data_scope) return;
    if (pendingScope) return;
    setPendingScope(role.id);
    try {
      await updateRoleMut.mutateAsync({
        id: role.id,
        payload: { data_scope: next },
      });
      const opt = DATA_SCOPE_OPTIONS.find((o) => o.value === next);
      toast.success(`${role.name} 数据范围改为「${opt?.label ?? next}」`);
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setPendingScope(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">权限矩阵</h1>
          <p className="text-muted-foreground">
            统一管理三类权限:菜单可见性、操作授权、数据范围。勾选表示该角色拥有此权限。
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

      {/* 超管锁定行:平台级全权信息展示,不可配置(plan §Step3)。后端 super_admin
          通过 permission_service.check 的 bypass 拥有全部权限,不进矩阵 roles,
          这里只是让超管权限「可见可理解」。非超管登录不显示(超管是平台概念)。 */}
      {isSuperAdmin && (
        <Card className="border-amber-500/40 bg-amber-50/50 dark:bg-amber-950/20">
          <CardContent className="flex items-center gap-3 py-4">
            <Shield className="h-5 w-5 text-amber-600 dark:text-amber-500" />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold">超级管理员</span>
                <Lock className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">
                拥有全部权限(平台级,后端 bypass)。此行仅作信息展示,不可配置。
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!canManage && (
        <p className="text-sm text-muted-foreground">
          当前为只读视图(需要 owner / admin 权限才能编辑)。
        </p>
      )}

      {isLoading ? (
        <p className="py-8 text-center text-muted-foreground">加载中…</p>
      ) : roles.length === 0 ? (
        <p className="py-8 text-center text-muted-foreground">暂无角色数据。</p>
      ) : (
        <div className="space-y-6">
          {sections.map((section) =>
            section.groups.length === 0 ? null : (
              <Card key={section.type}>
                <CardHeader>
                  <CardTitle className="text-base">{section.title}</CardTitle>
                  <CardDescription>{section.subtitle}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="sticky left-0 bg-background">
                            资源 / 动作
                          </TableHead>
                          {roles.map((r) => (
                            <TableHead key={r.id} className="text-center min-w-32">
                              <div className="flex flex-col items-center gap-1">
                                <span>{r.name}</span>
                                {r.is_system && (
                                  <Badge
                                    variant="secondary"
                                    className="text-[10px]"
                                  >
                                    系统
                                  </Badge>
                                )}
                              </div>
                            </TableHead>
                          ))}
                        </TableRow>
                        {/* 数据范围行:每角色一个 data_scope 下拉(plan §Step5)。
                            独立成一行(跨两区共用),放在表头之下、权限行之上,
                            让管理员一眼看到每角色的数据范围。仅 api 区显示(menu
                            区与数据范围无关),避免重复。 */}
                        {section.type === "api" && (
                          <TableRow>
                            <TableHead className="sticky left-0 bg-background">
                              <span className="font-semibold text-foreground">
                                数据范围
                              </span>
                            </TableHead>
                            {roles.map((role) => (
                              <TableCell key={role.id} className="text-center">
                                <DataScopeSelect
                                  value={role.data_scope}
                                  disabled={!canManage}
                                  busy={pendingScope === role.id}
                                  onChange={(next) => changeScope(role, next)}
                                />
                              </TableCell>
                            ))}
                          </TableRow>
                        )}
                      </TableHeader>
                      <TableBody>
                        {section.groups.map((group) =>
                          group.items.map((perm, idx) => (
                            <TableRow key={perm.code}>
                              <TableCell
                                className={cn(
                                  "sticky left-0 bg-background font-medium",
                                  idx === 0 && "border-t-2",
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
                                  data?.matrix[role.code]?.[perm.code] ??
                                  false;
                                const cellKey = `${role.id}:${perm.code}`;
                                const busy = pendingCell === cellKey;
                                return (
                                  <PermCell
                                    key={role.id}
                                    granted={granted}
                                    busy={busy}
                                    editable={canManage}
                                    onClick={() =>
                                      toggle(role, perm, granted)
                                    }
                                  />
                                );
                              })}
                            </TableRow>
                          )),
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            ),
          )}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">图例</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
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
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 text-amber-600 dark:text-amber-500" />
            <span>锁定(超管平台级,不可配置)</span>
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
        aria-label={granted ? "允许(点击撤销)" : "拒绝(点击授予)"}
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

function DataScopeSelect({
  value,
  disabled,
  busy,
  onChange,
}: {
  value: DataScope;
  disabled: boolean;
  busy: boolean;
  onChange: (next: DataScope) => void;
}) {
  return (
    <Select
      value={value}
      disabled={disabled || busy}
      onValueChange={(v) => onChange(v as DataScope)}
    >
      <SelectTrigger className="h-8 w-28 text-xs">
        {busy ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <SelectValue />
        )}
      </SelectTrigger>
      <SelectContent>
        {DATA_SCOPE_OPTIONS.map((opt) => (
          <SelectItem
            key={opt.value}
            value={opt.value}
            className={opt.value === value ? "font-semibold" : undefined}
          >
            <div className="flex flex-col">
              <span>{opt.label}</span>
              <span className="text-[10px] text-muted-foreground">
                {opt.hint}
              </span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
