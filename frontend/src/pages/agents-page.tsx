import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bot, Pencil, Plus, Trash2 } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import {
  useAgents,
  useCreateAgent,
  useDeleteAgent,
  useEffectiveModels,
  useUpdateAgent,
} from "@/hooks/queries";
import { apiErrorMessage } from "@/api/client";
import type { Agent } from "@/api/types";

// max_tokens / top_p are kept as strings in the form (empty = "not set") and
// normalized to number|null on submit. temperature always has a numeric value
// (slider), so it uses z.number() + valueAsNumber.
const agentSchema = z.object({
  name: z.string().min(1, "名称不能为空").max(128),
  system_prompt: z.string().default(""),
  model: z.string().default("deepseek-chat"),
  description: z.string().default(""),
  temperature: z.number().min(0).max(2).default(0.7),
  max_tokens: z.string().default(""),
  top_p: z.string().default(""),
});

type AgentFormValues = z.input<typeof agentSchema>;

export function AgentsPage() {
  const { data: agents, isLoading } = useAgents();
  const { data: effectiveModels } = useEffectiveModels();
  const createMut = useCreateAgent();
  const updateMut = useUpdateAgent();
  const deleteMut = useDeleteAgent();
  const toast = useToast();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Agent | null>(null);

  // Available models come from the backend (GET /settings/models), not a
  // hardcoded list — so the agent dropdown always matches the configured
  // provider. Default to deepseek-chat until the list resolves.
  const models = effectiveModels ?? [];
  const defaultModel = models[0] ?? "deepseek-chat";

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentSchema),
    defaultValues: {
      name: "",
      system_prompt: "",
      model: defaultModel,
      description: "",
      temperature: 0.7,
      max_tokens: "",
      top_p: "",
    },
  });

  const openCreate = () => {
    setEditing(null);
    form.reset({
      name: "",
      system_prompt: "",
      model: defaultModel,
      description: "",
      temperature: 0.7,
      max_tokens: "",
      top_p: "",
    });
    setDialogOpen(true);
  };

  const openEdit = (agent: Agent) => {
    setEditing(agent);
    form.reset({
      name: agent.name,
      system_prompt: agent.system_prompt,
      model: agent.model,
      description: agent.description,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens != null ? String(agent.max_tokens) : "",
      top_p: agent.top_p != null ? String(agent.top_p) : "",
    });
    setDialogOpen(true);
  };

  const onSubmit = async (values: AgentFormValues) => {
    // Parse optional numeric fields: empty string → null (don't forward to the
    // LLM, use provider default). A non-empty string is parsed to a number.
    const parseNum = (s: string | undefined): number | null => {
      const trimmed = (s ?? "").trim();
      if (trimmed === "") return null;
      const n = Number(trimmed);
      return Number.isNaN(n) ? null : n;
    };
    const payload = {
      ...values,
      max_tokens: parseNum(values.max_tokens),
      top_p: parseNum(values.top_p),
    };
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新", `智能体「${values.name}」`);
      } else {
        await createMut.mutateAsync(payload);
        toast.success("已创建", `智能体「${values.name}」`);
      }
      setDialogOpen(false);
    } catch (err) {
      toast.error("操作失败", apiErrorMessage(err));
    }
  };

  const handleDelete = async (agent: Agent) => {
    if (!confirm(`确认删除智能体「${agent.name}」？此操作不可撤销。`)) return;
    try {
      await deleteMut.mutateAsync(agent.id);
      toast.success("已删除", `智能体「${agent.name}」`);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">智能体</h1>
          <p className="text-muted-foreground">管理你租户下的 AI 智能体</p>
        </div>
        <Button onClick={openCreate} data-testid="create-agent-btn">
          <Plus className="mr-2 h-4 w-4" /> 新建智能体
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>智能体列表</CardTitle>
          <CardDescription>
            {agents ? `共 ${agents.length} 个` : "加载中…"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !agents?.length ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Bot className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                还没有智能体，点击右上角创建第一个
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {agents.map((agent) => (
                  <TableRow key={agent.id}>
                    <TableCell className="font-medium">
                      {agent.name}
                      {agent.description && (
                        <p className="text-xs font-normal text-muted-foreground">
                          {agent.description}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{agent.model}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(agent.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(agent)}
                        title="编辑"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(agent)}
                        title="删除"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "编辑智能体" : "新建智能体"}</DialogTitle>
            <DialogDescription>
              配置智能体的名称、系统提示词和底层模型
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">名称</Label>
              <Input id="name" data-testid="agent-name-input" {...form.register("name")} />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.name.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="model">模型</Label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                {...form.register("model")}
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              {models.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  暂无可用模型，请在设置页配置 LLM。
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="system_prompt">系统提示词</Label>
              <textarea
                className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="你是一个有用的助手…"
                {...form.register("system_prompt")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">描述</Label>
              <Input
                id="description"
                placeholder="用于区分智能体用途，如「客服助手」「代码生成」"
                {...form.register("description")}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="temperature">温度（temperature）</Label>
                <span className="text-sm text-muted-foreground">
                  {form.watch("temperature")?.toFixed(1)}
                </span>
              </div>
              <input
                id="temperature"
                type="range"
                min={0}
                max={2}
                step={0.1}
                className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-input"
                {...form.register("temperature", { valueAsNumber: true })}
              />
              <p className="text-xs text-muted-foreground">
                0 = 确定性输出，2 = 高随机性。代码生成建议低温度，创意写作建议高温度。
              </p>
            </div>
            {/* Advanced parameters — collapsed by default so new users aren't
                overwhelmed. max_tokens/top_p are optional; leave blank to use
                the provider default. */}
            <details className="group rounded-md border p-3">
              <summary className="cursor-pointer select-none text-sm font-medium text-muted-foreground">
                高级设置（max_tokens / top_p）
              </summary>
              <div className="mt-3 space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="max_tokens">最大输出 token（max_tokens）</Label>
                  <Input
                    id="max_tokens"
                    type="number"
                    min={1}
                    max={32768}
                    placeholder="留空 = 不限制"
                    {...form.register("max_tokens")}
                  />
                  <p className="text-xs text-muted-foreground">
                    限制单次回复的最大 token 数。留空使用模型默认值。
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="top_p">top_p（核采样）</Label>
                  <Input
                    id="top_p"
                    type="number"
                    min={0}
                    max={1}
                    step={0.1}
                    placeholder="留空 = 不设置"
                    {...form.register("top_p")}
                  />
                  <p className="text-xs text-muted-foreground">
                    0-1 之间。与 temperature 二选一调节，留空使用模型默认值。
                  </p>
                </div>
              </div>
            </details>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                取消
              </Button>
              <Button
                type="submit"
                disabled={createMut.isPending || updateMut.isPending}
                data-testid="agent-submit"
              >
                {editing ? "保存" : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
