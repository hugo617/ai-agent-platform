/**
 * knowledge/ document-list — 中栏文档列表卡片(reader-ui slice 01)。
 *
 * 镜像 devices/store-view.tsx 的「子组件自调 hook」范式(G1):本组件自调
 * ``useDocuments(filter?)``,父 index.tsx 不调 hook —— 只把选中的
 * scope/categoryId 作为 props 下传,本组件透传给 hook 作 query 参数。
 *
 * 切片 01 范围(只读卡片视图):
 *   - 渲染文档卡片(标题 + ScopeBadge 来源徽章 + statusBadge 状态徽章 +
 *     更新时间 + chunk 数)
 *   - 空态 + 加载态(ListState 范式)
 *   - 接收 ``filter`` props 透传给 useDocuments(为切片 02 category-tree 点击
 *     筛选铺好管线;切片 01 不传 filter = 全量)
 *
 * 切片 03 范围(本片不做):录入/删除 Dialog + DropdownMenu 操作项 + 按钮守卫
 * (member 只读)。本片是纯只读列表,无写操作。
 *
 * 选中态:本组件接收 ``selectedId`` + ``onSelectDoc`` 回调,点击卡片高亮选中
 * 并通知父层(切片 02 的 MarkdownReader 联动基础)。切片 01 父层暂不传 → 无
 * 选中态,纯展示。
 */
import { FileText } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ListState } from "@/components/ui/list-state";
import { useDocuments } from "@/hooks/queries";
import type { DocumentRead } from "@/api/types";
import { cn } from "@/lib/utils";
import { formatDateTime as fmt } from "@/lib/format";
import { ScopeBadge } from "./scope-badge";
import { statusBadge } from "./shared";

// List filter props —— 父 index.tsx 把 CategoryTree 选中的 scope/categoryId 下传
// 到这里,本组件透传给 useDocuments(切片 02 联动基础)。切片 01 父层不传 = 全量。
export interface DocumentListProps {
  scope?: DocumentRead["scope"];
  categoryId?: string;
  // 选中态(切片 02 MarkdownReader 联动)。切片 01 父层不传 → 无高亮。
  selectedId?: string | null;
  onSelectDoc?: (doc: DocumentRead) => void;
}

export function DocumentList({
  scope,
  categoryId,
  selectedId,
  onSelectDoc,
}: DocumentListProps) {
  const { data: docs, isLoading, isError, error, refetch } = useDocuments({
    scope,
    category_id: categoryId,
  });
  const list = docs ?? [];

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle>文档列表</CardTitle>
        <CardDescription>
          共 {list.length} 篇文档。点击查看详情。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto">
        <ListState
          isLoading={isLoading}
          isEmpty={list.length === 0}
          isError={isError}
          error={error}
          onRetry={() => refetch()}
          loadingVariant="skeleton"
          skeletonRows={4}
          emptyContent={
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <FileText className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无文档</p>
            </div>
          }
        >
          <ul className="space-y-2">
            {list.map((d) => {
              const selected = selectedId != null && d.id === selectedId;
              return (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => onSelectDoc?.(d)}
                    className={cn(
                      "w-full rounded-md border bg-card p-3 text-left transition-colors",
                      "hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      selected
                        ? "border-primary ring-1 ring-primary"
                        : "border-border",
                    )}
                    aria-current={selected ? "true" : undefined}
                  >
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <span className="line-clamp-1 font-medium">{d.name}</span>
                      <ScopeBadge scope={d.scope} />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      {statusBadge(d.status)}
                      <span>{d.chunk_count} 块</span>
                      <span>{fmt(d.updated_at)}</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </ListState>
      </CardContent>
    </Card>
  );
}
