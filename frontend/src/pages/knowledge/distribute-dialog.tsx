/**
 * knowledge/ distribute-dialog — 下发文档到门店/集团(admin-ui slice 03 F4)。
 *
 * 两种下发目标二选一(XOR,对齐后端 DistributeRequest):
 *   - 「按门店」:Checkbox 多选,构造 `{target_tenant_ids: [...]}`。
 *   - 「按集团」:Select 单选,构造 `{target_group_id: "..."}`。
 *
 * 角色派生目标范围(F7 职责切割;入口仅 isGroupAdmin||isSuperAdmin 可见):
 *   - group_admin:按门店 → 锁本集团(me.group_id)分店;按集团 → 锁 me.group_id
 *     不可改。本入口下 group_admin 永远只能下发到本集团。
 *   - super_admin:按门店 → useAllTenants 全平台门店;按集团 → useGroups 全部集团任选。
 *
 * 实现偏离(plan §F4 写「RadioGroup」):项目无 radio-group.tsx 组件
 * (@radix-ui/react-radio-group 在 package.json 声明但未装,同 Tabs 先例),故模式
 * 切换走 button-list 范式(镜像 admin-panel 子 tab / settings-page),功能等价。
 *
 * 空选校验在前端兜底(后端 BizError→400 是第二道闸):按门店未选任何门店 / 按集团
 * 未选集团 → toast.error 拦截,不发请求。
 *
 * 成功提示「已下发 N 条」:后端 POST 返回 KnowledgeDistributionRead[](本次新建 +
 * 重激活的下发关系),用数组长度作为 N。
 */
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { isGroupAdmin, isSuperAdmin } from "@/lib/permission";
import {
  useAllTenants,
  useDistributeDocument,
  useGroups,
} from "@/hooks/queries";
import type { DistributeRequest, TenantBrief } from "@/api/types";

type Mode = "tenants" | "group";

export interface DistributeDialogProps {
  docId: string;
  docName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DistributeDialog({
  docId,
  docName,
  open,
  onOpenChange,
}: DistributeDialogProps) {
  const { me } = useAuth();
  const toast = useToast();
  const distMut = useDistributeDocument(docId);
  const { data: groups } = useGroups();
  const { data: allTenants } = useAllTenants(isSuperAdmin(me));

  const [mode, setMode] = useState<Mode>("tenants");
  const [selectedTenants, setSelectedTenants] = useState<string[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>("");

  // 打开时按角色播种默认 mode/选择;关闭时重置。
  useEffect(() => {
    if (open) {
      setMode("tenants");
      setSelectedTenants([]);
      // group_admin 按集团锁定本集团;super 留空待选。
      setSelectedGroup(isGroupAdmin(me) && me?.group_id ? me.group_id : "");
    }
  }, [open, me]);

  // 按门店模式的可选门店清单:
  //   - group_admin → 本集团(me.group_id)的 tenants[] 展开(锁定本集团分店)。
  //   - super_admin → useAllTenants 全平台门店。
  // 找不到本集团 group 时 fallback 空(防御性,正常不会发生)。
  const tenantOptions = useMemo<TenantBrief[]>(() => {
    if (isSuperAdmin(me)) {
      // allTenants 是完整 TenantRead(带 id/name);映射成 TenantBrief 形态。
      return (allTenants ?? []).map((t) => ({
        id: t.id,
        name: t.name,
      }));
    }
    const myGroup = (groups ?? []).find((g) => g.id === me?.group_id);
    return myGroup?.tenants ?? [];
  }, [me, allTenants, groups]);

  // 按集团模式的可选集团清单:
  //   - group_admin → 仅本集团(useGroups 返回的本集团项,锁 me.group_id)。
  //   - super_admin → useGroups 全部集团任选。
  const groupOptions = useMemo(() => {
    if (isGroupAdmin(me)) {
      return (groups ?? []).filter((g) => g.id === me?.group_id);
    }
    return groups ?? [];
  }, [me, groups]);
  const groupLocked = isGroupAdmin(me) && !!me?.group_id;

  const toggleTenant = (id: string) => {
    setSelectedTenants((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    setMode(next);
    // XOR:切走某模式时清空该模式的残留选择,避免提交时误带另一模式字段。
    if (next === "group") setSelectedTenants([]);
    else setSelectedGroup(isGroupAdmin(me) && me?.group_id ? me.group_id : "");
  };

  const handleSubmit = async () => {
    // 前端空选校验(后端 BizError→400 是第二道闸)。
    if (mode === "tenants" && selectedTenants.length === 0) {
      toast.error("请至少选择一个门店");
      return;
    }
    if (mode === "group" && !selectedGroup) {
      toast.error("请选择目标集团");
      return;
    }

    // 按 mode 构造 XOR 载荷(只带一边字段,对齐 DistributeRequest)。
    const payload: DistributeRequest =
      mode === "tenants"
        ? { target_tenant_ids: selectedTenants }
        : { target_group_id: selectedGroup };

    try {
      const created = await distMut.mutateAsync(payload);
      const n = created.length;
      toast.success(`已下发 ${n} 条`, docName);
      onOpenChange(false);
    } catch (err) {
      toast.error("下发失败", apiErrorMessage(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>下发文档{docName ? `「${docName}」` : ""}</DialogTitle>
          <DialogDescription>
            选择下发目标:按门店多选下发到指定分店,或按集团一次性下发到整个集团旗下门店。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 模式切换 —— button-list 范式(无 radio-group.tsx,镜像子 tab 范式)。 */}
          <div className="flex gap-2">
            <Button
              type="button"
              variant={mode === "tenants" ? "default" : "outline"}
              size="sm"
              onClick={() => switchMode("tenants")}
            >
              按门店
            </Button>
            <Button
              type="button"
              variant={mode === "group" ? "default" : "outline"}
              size="sm"
              onClick={() => switchMode("group")}
            >
              按集团
            </Button>
          </div>

          {/* 按门店多选(XOR:选集团时整区 disabled)。 */}
          {mode === "tenants" ? (
            <div className="space-y-2">
              <Label>
                选择门店
                <span className="ml-2 text-xs text-muted-foreground">
                  已选 {selectedTenants.length}/{tenantOptions.length}
                </span>
              </Label>
              {tenantOptions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  暂无可选门店
                </p>
              ) : (
                <div className="max-h-56 space-y-2 overflow-auto rounded-md border p-3">
                  {tenantOptions.map((t) => {
                    const checked = selectedTenants.includes(t.id);
                    return (
                      <label
                        key={t.id}
                        className="flex cursor-pointer items-center gap-2 text-sm"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => toggleTenant(t.id)}
                        />
                        {t.name ?? t.id}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            /* 按集团单选(group_admin 锁 me.group_id;super 任选)。 */
            <div className="space-y-2">
              <Label>选择集团</Label>
              {groupLocked ? (
                <Select value={selectedGroup} disabled>
                  <SelectTrigger>
                    <SelectValue placeholder="本集团" />
                  </SelectTrigger>
                  <SelectContent>
                    {groupOptions.map((g) => (
                      <SelectItem key={g.id} value={g.id}>
                        {g.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Select value={selectedGroup} onValueChange={setSelectedGroup}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择集团" />
                  </SelectTrigger>
                  <SelectContent>
                    {groupOptions.map((g) => (
                      <SelectItem key={g.id} value={g.id}>
                        {g.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <p className="text-xs text-muted-foreground">
                按集团下发将覆盖该集团旗下所有门店。
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={distMut.isPending}>
            {distMut.isPending ? "下发中…" : "确认下发"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
