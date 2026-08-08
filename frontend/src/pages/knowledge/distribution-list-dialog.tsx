/**
 * knowledge/ distribution-list-dialog — 管理下发(已下发列表 + 撤回,
 * admin-ui slice 03 F5)。
 *
 * 渲染 GET /knowledge/documents/{docId}/distributions 的结果(含已撤回
 * is_active=false),每行:门店名 + 下发时间 + 状态(生效绿 / 已撤回灰)+
 * 「撤回」按钮(is_active=true 才可点)。撤回走二次确认 Dialog(普通 Dialog,
 * 无 alert-dialog.tsx 组件 —— 镜像 document-list 的删除确认范式),确认后调
 * useRevokeDistribution;hook 成功失效 qk.documentDistributions(docId) 自动刷新。
 *
 * 门店名解析:KnowledgeDistributionRead 只带 target_tenant_id,无 name。用
 * useGroups(group.tenants[])+ useAllTenants(super 全量)拼 tenant→name 映射;
 * 查不到(如门店已删)fallback 显示 id 前 8 位,不报错阻断渲染。
 */
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ListState } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import {
  useAllTenants,
  useDistributions,
  useGroups,
  useRevokeDistribution,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import type { KnowledgeDistributionRead } from "@/api/types";

export interface DistributionListDialogProps {
  docId: string;
  docName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DistributionListDialog({
  docId,
  docName,
  open,
  onOpenChange,
}: DistributionListDialogProps) {
  const toast = useToast();
  const { data, isLoading, isError, error, refetch } = useDistributions(docId);
  const revokeMut = useRevokeDistribution(docId);
  const { data: groups } = useGroups();
  // useAllTenants 默认 enabled=true;对非 super 会发请求(group_admin 的后端按
  // /tenants/all 权限可能 403)。这里始终调用以拿门店名,后端若 403 则 data
  // undefined,fallback 到 useGroups 的 tenants[] —— 两条路径任一拿到名即可。
  const { data: allTenants } = useAllTenants();

  const list = data ?? [];

  // 撤回二次确认目标(选中的 dist 行)。
  const [revokeTarget, setRevokeTarget] =
    useState<KnowledgeDistributionRead | null>(null);

  // tenant→name 映射:优先 useAllTenants(super 全量,带 name),不足则补
  // useGroups 的 tenants[](group.tenants 是 TenantBrief,也有 name)。
  const tenantNameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of allTenants ?? []) m.set(t.id, t.name);
    for (const g of groups ?? []) {
      for (const t of g.tenants) {
        if (!m.has(t.id)) m.set(t.id, t.name ?? t.id);
      }
    }
    return m;
  }, [allTenants, groups]);

  const tenantLabel = (id: string) => {
    const name = tenantNameMap.get(id);
    return name ?? id.slice(0, 8);
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    try {
      await revokeMut.mutateAsync(revokeTarget.id);
      toast.success("已撤回下发", tenantLabel(revokeTarget.target_tenant_id));
      setRevokeTarget(null);
    } catch (err) {
      toast.error("撤回失败", apiErrorMessage(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>管理下发{docName ? `「${docName}」` : ""}</DialogTitle>
          <DialogDescription>
            查看本文档已下发到的门店,撤回可停止门店侧的可见性(撤回后灰显)。
          </DialogDescription>
        </DialogHeader>

        <ListState
          isLoading={isLoading}
          isEmpty={list.length === 0}
          isError={isError}
          error={error}
          onRetry={() => refetch()}
          loadingVariant="skeleton"
          skeletonRows={3}
          emptyContent={
            <p className="py-8 text-center text-sm text-muted-foreground">
              该文档暂无下发关系
            </p>
          }
        >
          <div className="max-h-80 space-y-2 overflow-auto">
            {list.map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">
                    {tenantLabel(d.target_tenant_id)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    下发于 {fmt(d.distributed_at)}
                  </div>
                </div>
                {d.is_active ? (
                  <Badge variant="success">生效</Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">已撤回</span>
                )}
                {d.is_active && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRevokeTarget(d)}
                  >
                    撤回
                  </Button>
                )}
              </div>
            ))}
          </div>
        </ListState>

        {/* 撤回二次确认 —— 普通 Dialog 范式(无 alert-dialog,镜像删除确认)。 */}
        <Dialog
          open={!!revokeTarget}
          onOpenChange={(o) => !o && setRevokeTarget(null)}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>确认撤回</DialogTitle>
              <DialogDescription>
                确定撤回对「
                {revokeTarget
                  ? tenantLabel(revokeTarget.target_tenant_id)
                  : ""}
                」的下发?撤回后该门店将无法再检索到本文档。可重新下发恢复。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRevokeTarget(null)}>
                取消
              </Button>
              <Button
                variant="destructive"
                onClick={handleRevoke}
                disabled={revokeMut.isPending}
              >
                {revokeMut.isPending ? "撤回中…" : "确认撤回"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </DialogContent>
    </Dialog>
  );
}
