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
  useUpdateAgent,
} from "@/hooks/queries";
import { apiErrorMessage } from "@/api/client";
import type { Agent } from "@/api/types";

const MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "claude-3-5-sonnet"];

const agentSchema = z.object({
  name: z.string().min(1, "名称不能为空").max(128),
  system_prompt: z.string().default(""),
  model: z.string().default("gpt-4o-mini"),
});

type AgentFormValues = z.input<typeof agentSchema>;

export function AgentsPage() {
  const { data: agents, isLoading } = useAgents();
  const createMut = useCreateAgent();
  const updateMut = useUpdateAgent();
  const deleteMut = useDeleteAgent();
  const toast = useToast();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Agent | null>(null);

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentSchema),
    defaultValues: { name: "", system_prompt: "", model: "gpt-4o-mini" },
  });

  const openCreate = () => {
    setEditing(null);
    form.reset({ name: "", system_prompt: "", model: "gpt-4o-mini" });
    setDialogOpen(true);
  };

  const openEdit = (agent: Agent) => {
    setEditing(agent);
    form.reset({
      name: agent.name,
      system_prompt: agent.system_prompt,
      model: agent.model,
    });
    setDialogOpen(true);
  };

  const onSubmit = async (values: AgentFormValues) => {
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, payload: values });
        toast.success("已更新", `智能体「${values.name}」`);
      } else {
        await createMut.mutateAsync(values);
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
        <Button onClick={openCreate}>
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
                    <TableCell className="font-medium">{agent.name}</TableCell>
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
              <Input id="name" {...form.register("name")} />
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
                {MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="system_prompt">系统提示词</Label>
              <textarea
                className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="你是一个有用的助手…"
                {...form.register("system_prompt")}
              />
            </div>
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
