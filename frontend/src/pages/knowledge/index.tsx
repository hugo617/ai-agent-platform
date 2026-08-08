/**
 * knowledge/ index — 知识库页编排(reader-ui 三栏 + admin-ui 管理 tab)。
 *
 * admin-ui slice 02(F1 同页 Tabs):顶部 button-list 切「阅读」/「管理」两个 tab
 * (镜像 settings-page 范式,不引入 shadcn Tabs primitive —— 项目惯例;
 * @radix-ui/react-tabs 在 package.json 声明但 node_modules 未装、src 零引用)。
 *   - 默认「阅读」tab = reader-ui 三栏(CategoryTree + DocumentList + MarkdownReader
 *     + RetrievalDebugCard),对所有角色同结构,逻辑零变化。
 *   - 「管理」tab = <AdminPanel/>(admin-ui 切片02+),可见性
 *     hasPermission(me, "knowledge", "create")(owner/admin 可见,member 隐藏,F7)。
 *   - 选中态(selectedScope/selectedCategoryId/selectedDoc)只在「阅读」tab 用;
 *     「管理」tab 内部自管状态(AdminPanel 自调 useDocuments 不依赖阅读 tab 选中态)。
 *
 * reader-ui 范围(切片 01-03,三栏完整 + 迁移收尾,逻辑保留):
 *   - 左栏:CategoryTree(自调 useKnowledgeCategories,点击 category 筛选中栏)
 *   - 中栏:DocumentList(自调 useDocuments({scope, category_id}) + 录入/删除 Dialog
 *     + member 只读守卫,点击卡片选中下传)
 *   - 右栏:MarkdownReader(纯渲染 selectedDoc,目录大纲 G7 + 搜索高亮 G5)
 *   - 底部:<RetrievalDebugCard/> —— 从旧 legacy-page 迁入,逻辑零变化。
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
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission } from "@/lib/permission";
import type { DocumentRead, KnowledgeScope } from "@/api/types";
import { CategoryTree } from "./category-tree";
import { DocumentList } from "./document-list";
import { MarkdownReader } from "./markdown-reader";
import { RetrievalDebugCard } from "./retrieval-debug-card";
import { AdminPanel } from "./admin-panel";

type TopTab = "read" | "admin";

export function KnowledgePage() {
  const { me } = useAuth();
  // 管理 tab 可见性(F7):owner/admin 可见(member 隐藏整个管理 tab)。
  const canAdmin = hasPermission(me, "knowledge", "create");
  const [topTab, setTopTab] = useState<TopTab>("read");

  // selectedScope / selectedCategoryId —— CategoryTree 点击驱动(过滤 DocumentList)。
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

  // 顶层 tab 列表(管理 tab 按 canAdmin 条件加入,member 只看到阅读)。
  const topTabs: { id: TopTab; label: string }[] = [
    { id: "read", label: "阅读" },
    ...(canAdmin ? [{ id: "admin" as const, label: "管理" }] : []),
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="知识库"
        subtitle="三栏浏览:分类目录 / 文档列表 / 在线阅读。点击左栏分类筛选,点击中栏文档在右栏阅读。"
      />

      {/* 顶层 tab —— button-list 范式(镜像 settings-page,无 shadcn Tabs primitive)。
          member 只看到「阅读」(canAdmin=false),owner/admin 多一个「管理」(F7)。 */}
      <div className="flex gap-1 border-b">
        {topTabs.map((t) => {
          const isActive = t.id === topTab;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTopTab(t.id)}
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

      {topTab === "read" ? (
        <>
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

          {/* 检索调试 —— 切片 03 从旧 legacy-page 迁入,逻辑零变化。
              放三栏底部(三栏是阅读主体,调试卡是辅助工具,不抢主视觉)。 */}
          <RetrievalDebugCard />
        </>
      ) : (
        <AdminPanel />
      )}
    </div>
  );
}
