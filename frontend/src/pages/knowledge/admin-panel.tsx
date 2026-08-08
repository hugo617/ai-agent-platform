/**
 * knowledge/ admin-panel — 管理 tab 主体(admin-ui slice 02 F2)。
 *
 * 管理 tab 的两个子 tab(本切片用 button-list 范式,镜像 settings-page,不引入
 * shadcn Tabs primitive —— 项目惯例;@radix-ui/react-tabs 在 package.json 声明但
 * node_modules 未装、src 零引用):
 *   - 「文档与发放」(本切片):文档表格(useDocuments)+ 顶部「创建文档」按钮
 *     (仅 isGroupAdmin(me)||isSuperAdmin(me) 可见,F7 职责切割 —— 门店 owner 的
 *     本店创建走 reader-ui,不在此重复)。行操作「下发」「管理下发」在切片03 加。
 *   - 「分类管理」(切片04):Category CRUD UI(category-manager.tsx),按 scope
 *     分组渲染 platform/group/store 三区块,新建/编辑/删除 Dialog。
 *
 * 与 reader-ui 三栏阅读页的关系(职责正交):
 *   - reader-ui = 所有角色的「阅读 + 门店 CRUD」(owner/admin/member 同结构,差异在
 *     backend list 返回数据)。
 *   - admin-panel = owner/admin 的「管控 + 上级创建 + 下发管理」(member 隐藏整个
 *     管理 tab,见 index.tsx 的 hasPermission 守卫)。
 *   - 门店 owner 进管理 tab:看本店文档表格(只读,创建走 reader-ui)+ 分类管理
 *     (本店 store Category)+ 本店被下发情况(只读,切片03 的 distribution-list)。
 */
import { useState } from "react";
import { MoreHorizontal, Plus, Send, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ListState } from "@/components/ui/list-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/components/auth/auth-context";
import { isGroupAdmin, isSuperAdmin } from "@/lib/permission";
import { useDocuments } from "@/hooks/queries";
import type { DocumentRead } from "@/api/types";
import { ScopeBadge } from "./scope-badge";
import { statusBadge } from "./shared";
import { DocumentForm } from "./document-form";
import { DistributeDialog } from "./distribute-dialog";
import { DistributionListDialog } from "./distribution-list-dialog";
import { CategoryManager } from "./category-manager";
import { formatDateTime as fmt } from "@/lib/format";

type SubTab = "docs" | "categories";

export function AdminPanel() {
  const { me } = useAuth();
  const [subTab, setSubTab] = useState<SubTab>("docs");

  // 「创建文档」按钮仅 group_admin + super 可见(F7 职责切割)。门店 owner 的本店
  // 创建走 reader-ui,管理 tab 不重复入口。
  const canCreateUpper = isGroupAdmin(me) || isSuperAdmin(me);

  // 子 tab 列表(docs 始终在;categories 始终在 —— 两子 tab 对所有进管理 tab 的人可见)。
  const tabs: { id: SubTab; label: string }[] = [
    { id: "docs", label: "文档与发放" },
    { id: "categories", label: "分类管理" },
  ];

  return (
    <div className="space-y-4">
      {/* 子 tab —— button-list 范式(镜像 settings-page,无 shadcn Tabs primitive)。 */}
      <div className="flex gap-1 border-b">
        {tabs.map((t) => {
          const isActive = t.id === subTab;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setSubTab(t.id)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {subTab === "docs" ? (
        <DocsSubTab canCreateUpper={canCreateUpper} />
      ) : (
        <CategoryManager />
      )}
    </div>
  );
}

/** 文档与发放子 tab:文档表格 + 创建文档按钮(仅上级)+ 行操作「下发/管理下发」。 */
function DocsSubTab({ canCreateUpper }: { canCreateUpper: boolean }) {
  const [createOpen, setCreateOpen] = useState(false);
  // 下发/管理下发 两入口的行级目标(F5:DropdownMenu → 开对应 Dialog)。
  const [distributeTarget, setDistributeTarget] = useState<DocumentRead | null>(
    null,
  );
  const [listTarget, setListTarget] = useState<DocumentRead | null>(null);
  const { data: docs, isLoading, isError, error, refetch } = useDocuments();
  const list = docs ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle>文档与发放</CardTitle>
            <CardDescription>
              共 {list.length} 篇文档。上级可创建 platform/group 层级文档并发放到门店。
            </CardDescription>
          </div>
          {canCreateUpper && (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> 创建文档
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <ListState
          isLoading={isLoading}
          isEmpty={list.length === 0}
          isError={isError}
          error={error}
          onRetry={() => refetch()}
          loadingVariant="skeleton"
          skeletonRows={4}
          emptyContent={
            <p className="py-8 text-center text-sm text-muted-foreground">
              暂无文档
            </p>
          }
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>层级</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>更新时间</TableHead>
                {/* 操作列仅上级可见(F7:owner 进管理 tab 只看本店文档,无下发权)。 */}
                {canCreateUpper && <TableHead className="w-12">操作</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="font-medium">{d.name}</TableCell>
                  <TableCell>
                    <ScopeBadge scope={d.scope} />
                  </TableCell>
                  <TableCell>{statusBadge(d.status)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {fmt(d.updated_at)}
                  </TableCell>
                  {canCreateUpper && (
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label="文档操作">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => setDistributeTarget(d)}
                          >
                            <Send className="mr-2 h-4 w-4" /> 下发
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setListTarget(d)}>
                            <ListChecks className="mr-2 h-4 w-4" /> 管理下发
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ListState>
      </CardContent>

      <DocumentForm open={createOpen} onOpenChange={setCreateOpen} />

      {/* 下发 / 管理下发 Dialog —— 目标为空时卸载(条件挂载),避免 docId=""
          触发空请求;每次打开重新挂载拉最新数据(数据时效 > 关闭动画)。 */}
      {distributeTarget && (
        <DistributeDialog
          docId={distributeTarget.id}
          docName={distributeTarget.name}
          open
          onOpenChange={(o) => !o && setDistributeTarget(null)}
        />
      )}
      {listTarget && (
        <DistributionListDialog
          docId={listTarget.id}
          docName={listTarget.name}
          open
          onOpenChange={(o) => !o && setListTarget(null)}
        />
      )}
    </Card>
  );
}
