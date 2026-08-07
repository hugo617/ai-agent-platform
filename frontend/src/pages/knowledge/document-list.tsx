/**
 * knowledge/ document-list — 中栏文档列表卡片 + CRUD(reader-ui slice 01 + 03)。
 *
 * 镜像 devices/store-view.tsx 的「子组件自调 hook + 按钮守卫」范式(G1):
 *   - 本组件自调 ``useDocuments(filter?)``,父 index.tsx 不调 hook —— 只把选中的
 *     scope/categoryId 作为 props 下传,本组件透传给 hook 作 query 参数。
 *   - 写操作(录入/删除)按钮守卫 ``hasPermission(me, "knowledge", act)``
 *     (member 只持有 knowledge:read,写按钮隐藏 —— 与旧 legacy-page 一致,零回归)。
 *
 * 切片 01 范围(只读卡片视图):文档卡片(标题 + ScopeBadge + statusBadge + 时间 +
 * chunk 数)+ 空态 + filter 透传 + 选中态。
 *
 * 切片 03 范围(本片迁移):从旧 legacy-page.tsx 迁入录入 Dialog(name/sourceType/
 * textContent/upload 字段 + handleFilePick + handleCreate)+ 删除确认 Dialog +
 * DropdownMenu 删除项 + 按钮守卫。逻辑零变化(plan G2 + AC5:CRUD 行为零回归)。
 *
 * 选中态:本组件接收 ``selectedId`` + ``onSelectDoc`` 回调,点击卡片高亮选中并通知
 * 父层(切片 02 的 MarkdownReader 联动基础)。
 */
import { useState } from "react";
import { FileText, MoreHorizontal, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ListState } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission } from "@/lib/permission";
import {
  useCreateDocument,
  useDeleteDocument,
  useDocuments,
} from "@/hooks/queries";
import type { DocumentRead } from "@/api/types";
import { cn } from "@/lib/utils";
import { formatDateTime as fmt } from "@/lib/format";
import { ScopeBadge } from "./scope-badge";
import { statusBadge } from "./shared";

// List filter props —— 父 index.tsx 把 CategoryTree 选中的 scope/categoryId 下传
// 到这里,本组件透传给 useDocuments(切片 02 联动基础)。
export interface DocumentListProps {
  scope?: DocumentRead["scope"];
  categoryId?: string;
  // 选中态(切片 02 MarkdownReader 联动)。
  selectedId?: string | null;
  onSelectDoc?: (doc: DocumentRead) => void;
}

export function DocumentList({
  scope,
  categoryId,
  selectedId,
  onSelectDoc,
}: DocumentListProps) {
  const { me } = useAuth();
  const toast = useToast();
  const { data: docs, isLoading, isError, error, refetch } = useDocuments({
    scope,
    category_id: categoryId,
  });
  const createMut = useCreateDocument();
  const deleteMut = useDeleteDocument();

  // Button-level guards. super_admin bypasses (hasPermission returns true);
  // members only hold knowledge:read so the write actions stay hidden
  // (与旧 legacy-page 一致,零回归)。
  const canCreate = hasPermission(me, "knowledge", "create");
  const canDelete = hasPermission(me, "knowledge", "delete");

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentRead | null>(null);

  // ----- create-dialog form state (从 legacy-page 迁入,逻辑零变化) -----
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<"text" | "upload">("text");
  const [textContent, setTextContent] = useState("");
  // For upload mode, we read the .txt file content into this string (the
  // backend stores raw text, not the uploaded URL — ingest splits it).
  const [uploadContent, setUploadContent] = useState("");
  const [uploadFileName, setUploadFileName] = useState("");

  const resetForm = () => {
    setName("");
    setSourceType("text");
    setTextContent("");
    setUploadContent("");
    setUploadFileName("");
  };

  const openCreate = () => {
    resetForm();
    setCreateOpen(true);
  };

  // Read a .txt file into a string for the upload source type. We don't POST
  // the file to /uploads — the knowledge base only needs the text content,
  // which the backend splits + embeds. Reading client-side keeps it simple.
  const handleFilePick = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".txt") && file.type !== "text/plain") {
      toast.error("仅支持纯文本文件(.txt)");
      return;
    }
    const text = await file.text();
    setUploadContent(text);
    setUploadFileName(file.name);
    // Pre-fill the name if empty.
    setName((n) => n || file.name.replace(/\.txt$/i, ""));
  };

  const handleCreate = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("请填写文档名称");
      return;
    }
    const content = sourceType === "text" ? textContent : uploadContent;
    if (!content.trim()) {
      toast.error(sourceType === "text" ? "请输入文档内容" : "请选择 .txt 文件");
      return;
    }
    try {
      await createMut.mutateAsync({
        name: trimmedName,
        content,
        source_type: sourceType,
      });
      toast.success("已创建文档", trimmedName);
      setCreateOpen(false);
      resetForm();
    } catch (err) {
      toast.error("创建失败", apiErrorMessage(err));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMut.mutateAsync(deleteTarget.id);
      toast.success("已删除文档", deleteTarget.name);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  const list = docs ?? [];

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle>文档列表</CardTitle>
            <CardDescription>
              共 {list.length} 篇文档。点击查看详情。
            </CardDescription>
          </div>
          {canCreate && (
            <Button size="sm" onClick={openCreate}>
              <Plus className="mr-2 h-4 w-4" /> 录入文档
            </Button>
          )}
        </div>
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
              <p className="text-sm text-muted-foreground">
                暂无文档{canCreate ? ",点击「录入文档」添加" : ""}
              </p>
            </div>
          }
        >
          <ul className="space-y-2">
            {list.map((d) => {
              const selected = selectedId != null && d.id === selectedId;
              return (
                <li key={d.id}>
                  <div
                    className={cn(
                      "w-full rounded-md border bg-card p-3 transition-colors",
                      selected
                        ? "border-primary ring-1 ring-primary"
                        : "border-border",
                    )}
                    aria-current={selected ? "true" : undefined}
                  >
                    <div className="flex items-start gap-2">
                      <button
                        type="button"
                        onClick={() => onSelectDoc?.(d)}
                        className="flex-1 text-left"
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
                      {canDelete && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="shrink-0"
                              aria-label="操作"
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => setDeleteTarget(d)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </ListState>
      </CardContent>

      {/* create dialog —— 从 legacy-page 迁入,逻辑零变化 */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>录入知识文档</DialogTitle>
            <DialogDescription>
              文档创建后会自动分块并生成向量索引。失败时状态显示为「索引失败」(
              通常是 Embedding 配置缺失或 Key 无效,请在设置页配置)。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>文档名称</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="如 颈椎理疗服务话术"
              />
            </div>

            <div className="space-y-2">
              <Label>录入方式</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={sourceType === "text" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSourceType("text")}
                >
                  手动录入
                </Button>
                <Button
                  type="button"
                  variant={sourceType === "upload" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSourceType("upload")}
                >
                  上传 .txt 文件
                </Button>
              </div>
            </div>

            {sourceType === "text" ? (
              <div className="space-y-2">
                <Label>文档内容</Label>
                <textarea
                  className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  placeholder="粘贴或输入知识库文本(产品说明、FAQ、话术等)..."
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label>选择文本文件</Label>
                <input
                  type="file"
                  accept=".txt,text/plain"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFilePick(f);
                  }}
                  className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:bg-primary/90"
                />
                {uploadFileName && (
                  <p className="text-xs text-muted-foreground">
                    已读取:{uploadFileName}({uploadContent.length} 字符)
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  仅支持纯文本 .txt 文件。文件内容会在客户端读取后提交。
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button onClick={handleCreate} disabled={createMut.isPending}>
              {createMut.isPending ? "创建中…" : "创建并索引"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* delete confirm —— 从 legacy-page 迁入,逻辑零变化 */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定删除「{deleteTarget?.name}」?删除后其向量分块将一并清除,
              智能体将无法检索到该文档的内容。此操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" /> 删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
