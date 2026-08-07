/**
 * knowledge/ index — 三栏可视化阅读页编排(reader-ui slice 01)。
 *
 * 镜像 devices/index.tsx 的「barrel 编排 + 子组件自调 hook」范式,但与 devices 的
 * 「按角色二叉路由(super/hq vs store)」不同:knowledge 是「三栏布局」对所有角色
 * 同结构(差异在 backend list 返回数据,前端只渲染)。
 *
 * 切片 01 范围(三栏空壳 + 中栏 DocumentList 卡片):
 *   - 左栏:占位「待实现」(切片 02 落地 CategoryTree)
 *   - 中栏:DocumentList 只读卡片视图(本切片已实现)
 *   - 右栏:占位「待实现」(切片 02 落地 MarkdownReader)
 *   - 底部:<LegacyKnowledgePage/> —— 旧 page 全部行为(列表 Table + 录入/删除
 *     Dialog + 检索调试卡)整体保留,plan G2 + AC5 行为零回归。切片 03 拆掉。
 *
 * 选中态(为切片 02 铺管线,切片 01 暂不联动):
 *   - selectedScope / selectedCategoryId:CategoryTree 点击后设置 → 下传 DocumentList
 *   - selectedDoc:DocumentList 点击卡片后设置 → 下传 MarkdownReader
 *   切片 01 不接 CategoryTree / MarkdownReader,故 selectedDoc 仅 state 持有,
 *   无右栏消费(占位)。
 *
 * 切片 01 父层不持有 useQuery/useMutation —— data fetching 在子组件(DocumentList
 * 自调 useDocuments,plan G1)。index 只管选中态 + 三栏编排。
 */
import { useState } from "react";
import { PanelsTopLeft } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { DocumentRead } from "@/api/types";
import { DocumentList } from "./document-list";
import { LegacyKnowledgePage } from "./legacy-page";

export function KnowledgePage() {
  // selectedDoc —— 切片 02 MarkdownReader 联动基础。切片 01 持有选中态供右栏占位
  // 提示渲染,右栏阅读器在切片 02 落地后消费。
  //
  // ⚠️ selectedScope / selectedCategoryId 是切片 02 CategoryTree 点击驱动的状态
  // (filter DocumentList),**不是** doc 点击驱动的 —— 故不在 onSelectDoc 里设这两个
  // (那样会把列表按所选 doc 的 scope 误过滤)。切片 02 接 CategoryTree 时再引入。
  const [selectedDoc, setSelectedDoc] = useState<DocumentRead | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="知识库"
        subtitle="三栏浏览:分类目录 / 文档列表 / 在线阅读。左栏分类树与右栏阅读器将在后续切片上线。"
      />

      {/* 三栏布局 —— 切片 01 空壳:左/右栏占位「待实现」,中栏 DocumentList 已落地 */}
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,1fr)]">
        {/* 左栏:CategoryTree 占位(切片 02 落地) */}
        <Card className="hidden lg:flex lg:flex-col">
          <CardHeader>
            <CardTitle className="text-sm">分类目录</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 py-8 text-xs text-muted-foreground">
              <PanelsTopLeft className="h-4 w-4" />
              <span>左栏目录树(待实现)</span>
            </div>
          </CardContent>
        </Card>

        {/* 中栏:文档列表卡片(已落地)。切片 01 不传 filter/selectedId(纯展示)。
            切片 02 接 CategoryTree 的 scope/categoryId + 选中 doc 联动右栏。 */}
        <DocumentList onSelectDoc={setSelectedDoc} />

        {/* 右栏:MarkdownReader 占位(切片 02 落地)。切片 01 selectedDoc 已持有,
            但右栏未实现,占位提示。 */}
        <Card className="hidden lg:flex lg:flex-col">
          <CardHeader>
            <CardTitle className="text-sm">阅读器</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="py-8 text-xs text-muted-foreground">
              {selectedDoc ? (
                <span>已选中:{selectedDoc.name}(阅读器待实现)</span>
              ) : (
                <span>右栏 Markdown 阅读器(待实现)</span>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 旧 page 全部行为 —— 切片 01 过渡期保留,plan G2 + AC5 行为零回归。
          切片 03 把这里的 CRUD 迁进 document-list.tsx、RetrievalDebugCard 独立,
          然后删除 LegacyKnowledgePage。 */}
      <LegacyKnowledgePage />
    </div>
  );
}
