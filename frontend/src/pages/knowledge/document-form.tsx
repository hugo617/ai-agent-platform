/**
 * knowledge/ document-form — admin 创建文档表单(admin-ui slice 02 F3)。
 *
 * 与 reader-ui 的 document-list 录入 Dialog 区别(reader-ui = 门店 store 录入,
 * scope 固定 store,无 scope 下拉;本表单 = 上级创建 platform/group/store 文档,
 * scope 按 getAvailableScopes(me) 过滤):
 *   - scope Select:getAvailableScopes 派生(super→全 / group_admin→group+store /
 *     owner/admin→store)。门店 owner 的创建走 reader-ui,本表单的「创建文档」按钮
 *     仅 group_admin||super 可见(admin-panel F7 职责切割),故 getAvailableScopes
 *     在此入口至少返回 [store],不会是空。
 *   - scope 联动:platform → 隐藏 group/tenant(两者 undefined);group → 显示 group
 *     字段(group_admin 锁 me.group_id 不可改;super 可选 useGroups 任意);store →
 *     隐藏 group,显示 tenant(group_admin/owner 默认 me.tenant_id 锁定;super 可选
 *     useAllTenants 任意)。
 *   - category 下拉:按所选 scope 过滤 useKnowledgeCategories(同 scope 的可见分类)。
 *   - name/content/source_type:沿用 reader-ui 范式(纯文本 / .txt 上传)。
 *
 * 提交调 useCreateDocument 透传 scope/group_id/tenant_id/category_id(可选,未选则
 * undefined,后端 scope=None 推导本店零回归;此处 scope 必选故始终透传)。
 */
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
import {
  getAvailableScopes,
  isSuperAdmin,
} from "@/lib/permission";
import {
  useCreateDocument,
  useKnowledgeCategories,
} from "@/hooks/queries";
import { useGroups } from "@/hooks/queries";
import { useAllTenants } from "@/hooks/queries";
import type {
  DocumentCreate,
  KnowledgeCategoryRead,
  KnowledgeScope,
} from "@/api/types";

// scope → 中文标签(对齐 ScopeBadge 的展示语义)。
const SCOPE_LABEL: Record<KnowledgeScope, string> = {
  platform: "平台",
  group: "集团",
  store: "本店",
};

export interface DocumentFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentForm({ open, onOpenChange }: DocumentFormProps) {
  const { me } = useAuth();
  const toast = useToast();
  const createMut = useCreateDocument();
  const { data: categories } = useKnowledgeCategories();
  // group/tenant 下拉数据源(super_admin 选择目标用;group_admin/owner 锁定本集团/
  // 本店时只需 me.group_id/me.tenant_id,但 hooks 仍调 —— 简单一致,且 useGroups 对
  // tenant 用户返回本集团,useAllTenants 对非 super enabled=false 不发请求)。
  const { data: groups } = useGroups();
  const { data: allTenants } = useAllTenants(isSuperAdmin(me));

  const availableScopes = useMemo(() => getAvailableScopes(me), [me]);

  // ----- form state -----
  const [name, setName] = useState("");
  const [scope, setScope] = useState<KnowledgeScope | "">("");
  const [groupId, setGroupId] = useState<string>("");
  const [tenantId, setTenantId] = useState<string>("");
  const [categoryId, setCategoryId] = useState<string>("__none__");
  const [sourceType, setSourceType] = useState<"text" | "upload">("text");
  const [textContent, setTextContent] = useState("");
  const [uploadContent, setUploadContent] = useState("");
  const [uploadFileName, setUploadFileName] = useState("");

  // 打开时按角色播种默认 scope(第一个可用)+ 联动字段默认值。关闭时重置。
  useEffect(() => {
    if (open) {
      const first = availableScopes[0];
      setScope(first ?? "");
      // group_admin 的 group 默认本集团锁定;super 留空待选。
      if (first === "group" && me?.group_id) setGroupId(me.group_id);
      // store 默认本店(group_admin/owner);super 留空待选。
      if (first === "store" && me?.tenant_id) setTenantId(me.tenant_id);
    }
  }, [open, availableScopes, me]);

  const resetForm = () => {
    setName("");
    setScope("");
    setGroupId("");
    setTenantId("");
    setCategoryId("__none__");
    setSourceType("text");
    setTextContent("");
    setUploadContent("");
    setUploadFileName("");
  };

  // scope 切换时重置 group/tenant 并重播种默认值。
  const handleScopeChange = (next: KnowledgeScope) => {
    setScope(next);
    setGroupId(next === "group" && me?.group_id ? me.group_id : "");
    setTenantId(next === "store" && me?.tenant_id ? me.tenant_id : "");
    setCategoryId("__none__");
  };

  const handleFilePick = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".txt") && file.type !== "text/plain") {
      toast.error("仅支持纯文本文件(.txt)");
      return;
    }
    const text = await file.text();
    setUploadContent(text);
    setUploadFileName(file.name);
    setName((n) => n || file.name.replace(/\.txt$/i, ""));
  };

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("请填写文档名称");
      return;
    }
    if (!scope) {
      toast.error("请选择文档层级");
      return;
    }
    const content = sourceType === "text" ? textContent : uploadContent;
    if (!content.trim()) {
      toast.error(sourceType === "text" ? "请输入文档内容" : "请选择 .txt 文件");
      return;
    }
    // scope=group 必须有 group_id;scope=store 必须有 tenant_id(默认值或手选)。
    if (scope === "group" && !groupId) {
      toast.error("请选择目标集团");
      return;
    }
    if (scope === "store" && !tenantId) {
      toast.error("请选择目标门店");
      return;
    }

    const payload: DocumentCreate = {
      name: trimmedName,
      content,
      source_type: sourceType,
      scope,
    };
    if (scope === "group") payload.group_id = groupId;
    if (scope === "store") payload.tenant_id = tenantId;
    if (categoryId !== "__none__") payload.category_id = categoryId;

    try {
      await createMut.mutateAsync(payload);
      toast.success("已创建文档", trimmedName);
      onOpenChange(false);
      resetForm();
    } catch (err) {
      toast.error("创建失败", apiErrorMessage(err));
    }
  };

  // 按所选 scope 过滤 category(同 scope 可见分类;platform → 只 platform 分类,
  // group → group 分类,store → store 分类)。category 可选,默认 __none__。
  const scopeCategories = useMemo<KnowledgeCategoryRead[]>(() => {
    if (!scope || !categories) return [];
    return categories.filter((c) => c.scope === scope);
  }, [scope, categories]);

  // group/tenant 字段显隐 + 是否可选。
  const showGroup = scope === "group";
  const showTenant = scope === "store";
  const groupLocked = showGroup && !!me?.group_id && !isSuperAdmin(me);
  const tenantLocked = showTenant && !!me?.tenant_id && !isSuperAdmin(me);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>创建知识文档</DialogTitle>
          <DialogDescription>
            上级创建文档:选择层级(platform/group/store)后录入,文档会自动分块并生成向量索引。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>文档名称</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如 集团统一话术 / 平台标准手册"
            />
          </div>

          <div className="space-y-2">
            <Label>文档层级</Label>
            <Select
              value={scope}
              onValueChange={(v) => handleScopeChange(v as KnowledgeScope)}
            >
              <SelectTrigger>
                <SelectValue placeholder="选择层级(platform/group/store)" />
              </SelectTrigger>
              <SelectContent>
                {availableScopes.map((s) => (
                  <SelectItem key={s} value={s}>
                    {SCOPE_LABEL[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {showGroup && (
            <div className="space-y-2">
              <Label>目标集团</Label>
              {groupLocked ? (
                <Input value={groupId} disabled />
              ) : (
                <Select value={groupId} onValueChange={setGroupId}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择集团" />
                  </SelectTrigger>
                  <SelectContent>
                    {(groups ?? []).map((g) => (
                      <SelectItem key={g.id} value={g.id}>
                        {g.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          {showTenant && (
            <div className="space-y-2">
              <Label>目标门店</Label>
              {tenantLocked ? (
                <Input value={tenantId} disabled />
              ) : (
                <Select value={tenantId} onValueChange={setTenantId}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择门店" />
                  </SelectTrigger>
                  <SelectContent>
                    {(allTenants ?? []).map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          {scope && scopeCategories.length > 0 && (
            <div className="space-y-2">
              <Label>分类(可选)</Label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger>
                  <SelectValue placeholder="不选则不归类" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">不归类</SelectItem>
                  {scopeCategories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

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
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={createMut.isPending}>
            {createMut.isPending ? "创建中…" : "创建并索引"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
