import { useState } from "react";
import {
  BookOpen,
  FileText,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "lucide-react";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ListState } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { retrieveKnowledge } from "@/api/endpoints";
import { useAuth } from "@/components/auth/auth-context";
import { hasPermission } from "@/lib/permission";
import type { DocumentRead, RetrieveResult } from "@/api/types";
import {
  useCreateDocument,
  useDeleteDocument,
  useDocuments,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";

/** Badge for the embedding-pipeline status shown in the list. */
function statusBadge(status: string) {
  if (status === "indexed") return <Badge variant="success">已索引</Badge>;
  if (status === "failed")
    return <Badge variant="destructive">索引失败</Badge>;
  return <Badge variant="secondary">待处理</Badge>;
}

export function KnowledgePage() {
  const { me } = useAuth();
  const toast = useToast();
  const { data: docs, isLoading, isError, error, refetch } = useDocuments();
  const createMut = useCreateDocument();
  const deleteMut = useDeleteDocument();

  const canCreate = hasPermission(me, "knowledge", "create");
  const canDelete = hasPermission(me, "knowledge", "delete");

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentRead | null>(null);

  // ----- create-dialog form state -----
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
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">知识库</h1>
          <p className="text-muted-foreground">
            管理本租户的知识文档(产品手册 / FAQ / 话术库)。文档经分块与向量化后,
            智能体对话时可检索相关知识作答。
          </p>
        </div>
        {canCreate && (
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> 录入文档
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" /> 文档列表
          </CardTitle>
          <CardDescription>
            仅显示本租户的文档。状态反映向量索引流水线。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ListState
            isLoading={isLoading}
            isEmpty={list.length === 0}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            emptyContent={
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <FileText className="h-10 w-10 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  暂无文档{canCreate ? ",点击「录入文档」添加" : ""}
                </p>
              </div>
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>分块数</TableHead>
                  <TableHead>创建时间</TableHead>
                  {canDelete && (
                    <TableHead className="text-right">操作</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-medium">{d.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {d.source_type === "upload" ? "文件上传" : "手动录入"}
                    </TableCell>
                    <TableCell>{statusBadge(d.status)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {d.chunk_count}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(d.created_at)}
                    </TableCell>
                    {canDelete && (
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
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
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      <RetrievalDebugCard />

      {/* create dialog */}
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
            <Button
              onClick={handleCreate}
              disabled={createMut.isPending}
            >
              {createMut.isPending ? "创建中…" : "创建并索引"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* delete confirm */}
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
    </div>
  );
}

/** Retrieval-debug panel: enter a query, see the matched chunks + similarity
 * scores. Verifies the RAG pipeline finds the right context before relying on
 * it in agent conversations. */
function RetrievalDebugCard() {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RetrieveResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    try {
      const res = await retrieveKnowledge(q, 4);
      setResult(res);
    } catch (err) {
      toast.error("检索失败", apiErrorMessage(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Search className="h-5 w-5" /> 检索调试
        </CardTitle>
        <CardDescription>
          输入问题,查看向量检索召回的知识片段与相似度。用于验证检索效果。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSearch();
            }}
            placeholder="输入要检索的问题..."
          />
          <Button onClick={handleSearch} disabled={loading || !query.trim()}>
            {loading ? "检索中…" : "检索"}
          </Button>
        </div>

        {result && (
          <div className="space-y-3">
            {result.hits.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                未找到相关知识片段
              </p>
            ) : (
              result.hits.map((hit, i) => (
                <div
                  key={i}
                  className="rounded-md border bg-muted/30 p-3 text-sm"
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-xs text-muted-foreground">
                      来自:{hit.document_name}
                    </span>
                    <Badge variant="secondary">
                      相似度 {(hit.score * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <p className="whitespace-pre-wrap break-words">{hit.content}</p>
                </div>
              ))
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
