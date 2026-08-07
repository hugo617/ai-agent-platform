/**
 * knowledge/ index — 三栏可视化阅读页编排(reader-ui slice 01 + slice 02)。
 *
 * 镜像 devices/index.tsx 的「barrel 编排 + 子组件自调 hook」范式,但与 devices 的
 * 「按角色二叉路由(super/hq vs store)」不同:knowledge 是「三栏布局」对所有角色
 * 同结构(差异在 backend list 返回数据,前端只渲染)。
 *
 * 切片 02 范围(三栏完整 + 响应式):
 *   - 左栏:CategoryTree(自调 useKnowledgeCategories,点击 category 筛选中栏)
 *   - 中栏:DocumentList(自调 useDocuments({scope, category_id}),点击卡片选中下传)
 *   - 右栏:MarkdownReader(纯渲染 selectedDoc,目录大纲 G7 + 搜索高亮 G5)
 *   - 底部:<LegacyKnowledgePage/> —— 旧 page 全部行为(列表 Table + 录入/删除
 *     Dialog + 检索调试卡)整体保留,plan G2 + AC5 行为零回归。切片 03 拆掉。
 *
 * 选中态(切片 02 三栏联动):
 *   - selectedScope / selectedCategoryId:CategoryTree 点击后设置 → 下传 DocumentList
 *     作 useDocuments 参数(中栏列表按选中的 scope+category 过滤)
 *   - selectedDoc:DocumentList 点击卡片后设置 → 下传 MarkdownReader(右栏渲染)
 *   - index 不持有 useQuery/useMutation —— data fetching 在子组件(plan G1)
 *
 * 响应式(G4):
 *   - lg+(≥1024px):三栏并排 grid(左栏固定 260px + 中右各 minmax)
 *   - lg-(<1024px):左栏 CategoryTree 收进 Sheet 抽屉(默认关,顶部汉堡按钮展开);
 *     中右栏纵向堆叠(列表上 + 阅读器下)
 *   - Sheet 内渲染同一 <CategoryTree/>(逻辑零变化,只是容器从 grid 列变 Sheet)
 */
import { useState } from "react";
import { Menu } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { DocumentRead, KnowledgeScope } from "@/api/types";
import { CategoryTree } from "./category-tree";
import { DocumentList } from "./document-list";
import { MarkdownReader } from "./markdown-reader";
import { LegacyKnowledgePage } from "./legacy-page";

export function KnowledgePage() {
  // selectedScope / selectedCategoryId —— CategoryTree 点击驱动(过滤 DocumentList)。
  // 切片 01 注释的「不要在 onSelectDoc 里设这两个」(会把列表按所选 doc 的 scope
  // 误过滤)在切片 02 解决:这两个状态由 CategoryTree 的 onSelect 独立设置。
  const [selectedScope, setSelectedScope] = useState<KnowledgeScope | undefined>();
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | undefined>();

  // selectedDoc —— DocumentList 点击驱动(渲染 MarkdownReader)。
  const [selectedDoc, setSelectedDoc] = useState<DocumentRead | null>(null);

  // 响应式 Sheet 开合态(lg- 左栏抽屉)。默认关,汉堡按钮展开。
  const [treeSheetOpen, setTreeSheetOpen] = useState(false);

  // CategoryTree 点击 → 设置 scope+categoryId 过滤 + 关 Sheet(窄屏选完即收)。
  const handleCategorySelect = (selection: {
    scope: KnowledgeScope;
    categoryId: string;
  }) => {
    setSelectedScope(selection.scope);
    setSelectedCategoryId(selection.categoryId);
    setTreeSheetOpen(false);
  };

  // 三栏共用同一 <CategoryTree/> 实例 props(lg+ 直接渲染 / lg- 渲染进 Sheet)。
  const tree = (
    <CategoryTree
      selectedScope={selectedScope}
      selectedCategoryId={selectedCategoryId}
      onSelect={handleCategorySelect}
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="知识库"
        subtitle="三栏浏览:分类目录 / 文档列表 / 在线阅读。点击左栏分类筛选,点击中栏文档在右栏阅读。"
      />

      {/* 三栏布局(G4 响应式):
          - lg+:grid 三栏并排(左 260px 固定 + 中右 minmax)
          - lg-:左栏收进 Sheet(汉堡按钮触发)+ 中右 grid 两栏(列表上阅读器下) */}
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,1fr)]">
        {/* 左栏:CategoryTree。
            - lg+:直接渲染(grid 第一列)。
            - lg-:收进 Sheet(<lg:hidden 隐藏这列,下方 Sheet Trigger 显示)。 */}
        <div className="hidden lg:block">
          {tree}
        </div>

        {/* 中栏:文档列表卡片(自调 useDocuments + filter 联动 + 选中态)。 */}
        <DocumentList
          scope={selectedScope}
          categoryId={selectedCategoryId}
          selectedId={selectedDoc?.id}
          onSelectDoc={setSelectedDoc}
        />

        {/* 右栏:Markdown 阅读器(纯渲染 selectedDoc + 目录大纲 + 搜索高亮)。 */}
        <MarkdownReader doc={selectedDoc} />
      </div>

      {/* 响应式:lg- 左栏 Sheet 抽屉(lg+ 隐藏 Trigger)。汉堡按钮顶部固定。 */}
      <div className="lg:hidden">
        <Sheet open={treeSheetOpen} onOpenChange={setTreeSheetOpen}>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm">
              <Menu className="mr-2 h-4 w-4" />
              分类目录
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[280px] p-4">
            <SheetHeader>
              <SheetTitle>分类目录</SheetTitle>
            </SheetHeader>
            <div className="mt-4 h-[calc(100%-3rem)]">{tree}</div>
          </SheetContent>
        </Sheet>
      </div>

      {/* 旧 page 全部行为 —— 切片 02 过渡期保留,plan G2 + AC5 行为零回归。
          切片 03 把这里的 CRUD 迁进 document-list.tsx、RetrievalDebugCard 独立,
          然后删除 LegacyKnowledgePage。 */}
      <LegacyKnowledgePage />
    </div>
  );
}
