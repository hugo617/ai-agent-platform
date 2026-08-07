/**
 * knowledge/ category-tree — 左栏分类目录树(reader-ui slice 02)。
 *
 * 镜像 devices/store-view.tsx 的「子组件自调 hook」范式(plan G1):本组件自调
 * ``useKnowledgeCategories()``,父 index.tsx 不调 hook —— 只接收点击回调。
 *
 * 渲染结构(承接 plan §4.5 G7 + 切片 02 AC1):
 *   - 按 scope 分三区(platform 平台🔴 / group 集团🟡 / store 本店🟢),每区头部
 *     带 ScopeBadge 标识来源 + 该区 category 计数。
 *   - 每区下按 ``sort_order`` 列出该 scope 的 category;点击 category →
 *     ``onSelect({scope, categoryId})`` 通知父层 filter DocumentList。
 *   - 每个 scope 分区可折叠/展开(本地 state,默认全展开)。空 scope(无 category)
 *     仍显示分区头(让用户知道「这一层存在但暂无内容」),但无列表项。
 *
 * 选中态:接收 ``selectedScope`` / ``selectedCategoryId`` props(父层持有),命中
 * 的 category 高亮显示 —— 与 DocumentList 卡片选中范式一致(``ring-primary``)。
 * 点击同一 category 再次点击不 toggle 取消(plan 未要求取消语义,且 DocumentList
 * 的 scope/category 过滤一旦设为空会回到全量,与「在树里选了一个分类」的直觉
 * 冲突);用户选别的分类或刷新即切换。
 */
import { useState } from "react";
import { ChevronDown, ChevronRight, FolderTree } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ListState } from "@/components/ui/list-state";
import { useKnowledgeCategories } from "@/hooks/queries";
import type { KnowledgeCategoryRead, KnowledgeScope } from "@/api/types";
import { cn } from "@/lib/utils";
import { ScopeBadge } from "./scope-badge";

// scope 分区显示顺序:平台 → 集团 → 本店(从高到低,符合「上级下发在前」直觉)。
// 后端返回的 categories 可能任意顺序,前端按此固定顺序分组渲染。
const SCOPE_ORDER: KnowledgeScope[] = ["platform", "group", "store"];

// scope → 中文分区标题(分区头大字,与 ScopeBadge 的短标签「平台/集团/本店」区分)。
const SCOPE_SECTION_TITLE: Record<KnowledgeScope, string> = {
  platform: "平台下发",
  group: "集团下发",
  store: "本店自建",
};

export interface CategoryTreeSelection {
  scope: KnowledgeScope;
  categoryId: string;
}

export interface CategoryTreeProps {
  selectedScope?: KnowledgeScope;
  selectedCategoryId?: string;
  onSelect: (selection: CategoryTreeSelection) => void;
}

export function CategoryTree({
  selectedScope,
  selectedCategoryId,
  onSelect,
}: CategoryTreeProps) {
  const {
    data: categories,
    isLoading,
    isError,
    error,
    refetch,
  } = useKnowledgeCategories();
  const list = categories ?? [];

  // 按 scope 分组(用 Map 保持插入顺序,但渲染时按 SCOPE_ORDER 固定顺序输出)。
  const grouped = groupByScope(list);

  // 折叠的 scope 集合(本地 state)。默认全展开;点击分区头 toggle 进出集合。
  const [collapsed, setCollapsed] = useState<Set<KnowledgeScope>>(new Set());
  const toggleScope = (scope: KnowledgeScope) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle className="text-sm">分类目录</CardTitle>
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
              <FolderTree className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无分类</p>
            </div>
          }
        >
          <div className="space-y-4">
            {SCOPE_ORDER.filter((s) => grouped.has(s)).map((scope) => {
              const items = grouped.get(scope)!;
              const isCollapsed = collapsed.has(scope);
              return (
                <ScopeSection
                  key={scope}
                  scope={scope}
                  categories={items}
                  collapsed={isCollapsed}
                  onToggle={() => toggleScope(scope)}
                  selectedScope={selectedScope}
                  selectedCategoryId={selectedCategoryId}
                  onSelect={onSelect}
                />
              );
            })}
          </div>
        </ListState>
      </CardContent>
    </Card>
  );
}

/** 按 scope 分组(过滤掉 is_deleted 的 category —— 后端理论上不返回,前端兜底)。 */
function groupByScope(
  categories: KnowledgeCategoryRead[],
): Map<KnowledgeScope, KnowledgeCategoryRead[]> {
  const map = new Map<KnowledgeScope, KnowledgeCategoryRead[]>();
  for (const c of categories) {
    if (c.is_deleted) continue;
    const bucket = map.get(c.scope) ?? [];
    bucket.push(c);
    map.set(c.scope, bucket);
  }
  // 每个 scope 内按 sort_order 升序(sort_order 小的在前)。
  for (const bucket of map.values()) {
    bucket.sort((a, b) => a.sort_order - b.sort_order);
  }
  return map;
}

/** 单个 scope 分区:头部(折叠箭头 + ScopeBadge + 标题 + 计数)+ category 列表。 */
function ScopeSection({
  scope,
  categories,
  collapsed,
  onToggle,
  selectedScope,
  selectedCategoryId,
  onSelect,
}: {
  scope: KnowledgeScope;
  categories: KnowledgeCategoryRead[];
  collapsed: boolean;
  onToggle: () => void;
  selectedScope?: KnowledgeScope;
  selectedCategoryId?: string;
  onSelect: (selection: CategoryTreeSelection) => void;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        className="mb-1.5 flex w-full items-center gap-2 rounded-md px-1 py-1 text-left transition-colors hover:bg-accent"
      >
        {collapsed ? (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
        <ScopeBadge scope={scope} />
        <span className="text-sm font-medium">
          {SCOPE_SECTION_TITLE[scope]}
        </span>
        <span className="text-xs text-muted-foreground">({categories.length})</span>
      </button>

      {!collapsed && (
        <ul className="ml-2 space-y-0.5 border-l border-border pl-2">
          {categories.map((c) => {
            const selected =
              selectedScope === scope && selectedCategoryId === c.id;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onSelect({ scope, categoryId: c.id })}
                  aria-current={selected ? "true" : undefined}
                  className={cn(
                    "block w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                    "hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected
                      ? "bg-accent font-medium text-accent-foreground ring-1 ring-primary"
                      : "text-foreground",
                  )}
                >
                  {c.name}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
