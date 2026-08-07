/**
 * knowledge/ retrieval-debug-card — 检索调试面板(reader-ui slice 03)。
 *
 * 从旧 legacy-page.tsx 的 ``RetrievalDebugCard`` 整体迁入,**逻辑零变化**(plan
 * §6 切片 03 AC2 + §9 风险表「旧 RetrievalDebugCard 迁移引入行为回归」缓解 = 整体
 * 迁移逻辑零变化 + 保留检索调试测试断言)。纯 locality move:query state +
 * handleSearch + retrieveKnowledge 调用 + hits 渲染全部照搬。
 *
 * 用途:输入问题,查看向量检索召回的知识片段与相似度。用于验证 RAG 检索效果
 * (智能体对话前先在这里试检索,确认召回对了再上线)。
 *
 * 在 index.tsx 三栏布局底部渲染(三栏是阅读主体,调试卡是辅助工具,放底部不抢主视觉)。
 */
import { useState } from "react";
import { Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import { retrieveKnowledge } from "@/api/endpoints";
import type { RetrieveResult } from "@/api/types";

export function RetrievalDebugCard() {
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
