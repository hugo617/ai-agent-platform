import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bot, Pencil, Plus, Trash2, X } from "lucide-react";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
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
  useAttachSpecialist,
  useCreateAgent,
  useDeleteAgent,
  useDetachSpecialist,
  useEffectiveModels,
  useOrchestratorSpecialists,
  useUpdateAgent,
} from "@/hooks/queries";
import { apiErrorMessage } from "@/api/client";
import type { Agent } from "@/api/types";
import { formatDateTime } from "@/lib/format";

// max_tokens / top_p are kept as strings in the form (empty = "not set") and
// normalized to number|null on submit. temperature always has a numeric value
// (slider), so it uses z.number() + valueAsNumber.
// is_orchestrator/specialty drive the Supervisor multi-agent orchestration
// (feature 58): an orchestrator routes incoming messages to its specialists.
// specialist_ids are managed outside react-hook-form (checkbox list on create,
// dedicated attach/detach panel on edit — same pattern as groups-page tenants).
const agentSchema = z.object({
  name: z.string().min(1, "名称不能为空").max(128),
  system_prompt: z.string().default(""),
  model: z.string().default("deepseek-chat"),
  description: z.string().default(""),
  temperature: z.number().min(0).max(2).default(0.7),
  max_tokens: z.string().default(""),
  top_p: z.string().default(""),
  is_orchestrator: z.boolean().default(false),
  specialty: z.string().default(""),
});

type AgentFormValues = z.input<typeof agentSchema>;

export function AgentsPage() {
  const { data: agents, isLoading } = useAgents();
  const { data: effectiveModels } = useEffectiveModels();
  const createMut = useCreateAgent();
  const updateMut = useUpdateAgent();
  const deleteMut = useDeleteAgent();
  const attachMut = useAttachSpecialist();
  const detachMut = useDetachSpecialist();
  const toast = useToast();

  // Client-side filter seeded from ?search= so the global-search-box "查看全部"
  // deep link carries the term onto this page (the agents endpoint has no
  // server-side search). Matches against name + description, case-insensitive.
  const [searchParams] = useSearchParams();
  const search = (searchParams.get("search") ?? "").trim().toLowerCase();
  const visibleAgents = search
    ? (agents ?? []).filter(
        (a) =>
          a.name.toLowerCase().includes(search) ||
          (a.description ?? "").toLowerCase().includes(search),
      )
    : (agents ?? []);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Agent | null>(null);
  // specialist_ids chosen at creation time (Checkbox list). Unused in edit
  // mode, where attachment is done via the dedicated attach/detach panel.
  const [selectedSpecialistIds, setSelectedSpecialistIds] = useState<string[]>(
    [],
  );
  // which specialist is pending attach in the edit dialog's dropdown
  const [attachPick, setAttachPick] = useState("");

  // Available models come from the backend (GET /settings/models), not a
  // hardcoded list — so the agent dropdown always matches the configured
  // provider. Default to deepseek-chat until the list resolves.
  const models = effectiveModels ?? [];
  const defaultModel = models[0] ?? "deepseek-chat";

  // Fetch specialists of the editing orchestrator (enabled only when an
  // orchestrator is being edited).
  const { data: editingSpecialists } = useOrchestratorSpecialists(
    editing?.is_orchestrator ? editing.id : undefined,
  );

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
      is_orchestrator: false,
      specialty: "",
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
      is_orchestrator: false,
      specialty: "",
    });
    setSelectedSpecialistIds([]);
    setAttachPick("");
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
      is_orchestrator: agent.is_orchestrator,
      specialty: agent.specialty ?? "",
    });
    setAttachPick("");
    setDialogOpen(true);
  };

  // Specialists that may be picked as members of an orchestrator: every other
  // non-orchestrator agent in this tenant. Orchestrators cannot be attached as
  // specialists (prevents cycles, enforced both client and server side).
  const candidateSpecialists = useMemo(
    () => (agents ?? []).filter((a) => !a.is_orchestrator),
    [agents],
  );

  const toggleCreateSpecialist = (id: string) => {
    setSelectedSpecialistIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  // specialists not yet attached to the editing orchestrator (drives the
  // attach dropdown). Excludes the orchestrator itself and already-attached.
  const attachableSpecialists = useMemo(() => {
    if (!editing) return [];
    const attached = new Set(editingSpecialists?.map((s) => s.id) ?? []);
    return candidateSpecialists.filter(
      (a) => a.id !== editing.id && !attached.has(a.id),
    );
  }, [editing, editingSpecialists, candidateSpecialists]);

  const handleAttach = async () => {
    if (!editing || !attachPick) return;
    try {
      await attachMut.mutateAsync({
        orchestratorId: editing.id,
        specialistId: attachPick,
      });
      toast.success("已挂载 specialist");
      setAttachPick("");
    } catch (err) {
      toast.error("挂载失败", apiErrorMessage(err));
    }
  };

  const handleDetach = async (
    specialistId: string,
    specialistName?: string | null,
  ) => {
    if (!editing) return;
    try {
      await detachMut.mutateAsync({
        orchestratorId: editing.id,
        specialistId,
      });
      toast.success("已卸载 specialist", specialistName ?? specialistId);
    } catch (err) {
      toast.error("卸载失败", apiErrorMessage(err));
    }
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
      // specialty only meaningful for specialists (is_orchestrator=false).
      // Orchestrator itself has no specialty — clear it to avoid confusion.
      specialty:
        !values.is_orchestrator && (values.specialty ?? "").trim()
          ? (values.specialty ?? "").trim()
          : null,
    };
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新", `智能体「${values.name}」`);
      } else {
        // Backend has no specialist_ids on AgentCreate — orchestrator is
        // created first, then specialists attached via the dedicated endpoint
        // (same lifecycle as Group-tenant attachment).
        const created = await createMut.mutateAsync(payload);
        if (values.is_orchestrator && selectedSpecialistIds.length > 0) {
          await Promise.all(
            selectedSpecialistIds.map((specialistId) =>
              attachMut.mutateAsync({
                orchestratorId: created.id,
                specialistId,
              }),
            ),
          );
        }
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
            {agents
              ? search
                ? `匹配 ${visibleAgents.length} / 共 ${agents.length} 个`
                : `共 ${agents.length} 个`
              : "加载中…"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              加载中…
            </div>
          ) : !visibleAgents.length ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <Bot className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {search ? "没有匹配的智能体" : "还没有智能体，点击右上角创建第一个"}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleAgents.map((agent) => (
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
                      {agent.is_orchestrator ? (
                        <Badge>编排器</Badge>
                      ) : agent.specialty ? (
                        <Badge variant="secondary">specialist</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">普通</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{agent.model}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(agent.created_at)}
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
            {/* ---- orchestration: supervisor / specialist ---- */}
            <div className="space-y-3 rounded-md border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="is_orchestrator">编排器（Supervisor）</Label>
                  <p className="text-xs text-muted-foreground">
                    开启后该智能体作为路由编排器，会根据问题自动转发给挂载的 specialist。
                  </p>
                </div>
                <Switch
                  id="is_orchestrator"
                  checked={form.watch("is_orchestrator")}
                  onCheckedChange={(v) =>
                    form.setValue("is_orchestrator", v, {
                      shouldDirty: true,
                    })
                  }
                />
              </div>
              {!form.watch("is_orchestrator") && (
                <div className="space-y-2">
                  <Label htmlFor="specialty">职责描述（specialty）</Label>
                  <Input
                    id="specialty"
                    placeholder="如「预约/排班」「理疗/针灸」，供编排器路由参考"
                    {...form.register("specialty")}
                  />
                  <p className="text-xs text-muted-foreground">
                    当作为 specialist 被编排器调用时，此描述帮助 supervisor 判断是否路由给你。
                  </p>
                </div>
              )}
              {form.watch("is_orchestrator") &&
                (!editing ? (
                  <div className="space-y-2">
                    <Label>挂载 specialist（创建时挂载，可后续增删）</Label>
                    {candidateSpecialists.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        暂无可选 specialist（其他智能体要么是编排器，要么不存在）
                      </p>
                    ) : (
                      <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
                        {candidateSpecialists.map((s) => (
                          <label
                            key={s.id}
                            className="flex cursor-pointer items-center gap-2 text-sm"
                          >
                            <input
                              type="checkbox"
                              checked={selectedSpecialistIds.includes(s.id)}
                              onChange={() => toggleCreateSpecialist(s.id)}
                              className="h-4 w-4"
                            />
                            <span>{s.name}</span>
                            {s.specialty && (
                              <span className="text-xs text-muted-foreground">
                                ({s.specialty})
                              </span>
                            )}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label>
                      {`挂载 specialist（${editingSpecialists?.length ?? 0} 个）`}
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      {(editingSpecialists ?? []).length === 0 ? (
                        <span className="text-sm text-muted-foreground">
                          暂未挂载 specialist
                        </span>
                      ) : (
                        (editingSpecialists ?? []).map((s) => (
                          <Badge
                            key={s.id}
                            variant="secondary"
                            className="gap-1 pr-1"
                          >
                            {s.name}
                            <button
                              type="button"
                              onClick={() => handleDetach(s.id, s.name)}
                              disabled={detachMut.isPending}
                              className="ml-0.5 rounded-full hover:bg-muted"
                              aria-label={`卸载 ${s.name}`}
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </Badge>
                        ))
                      )}
                    </div>
                    {attachableSpecialists.length > 0 && (
                      <div className="mt-2 flex items-center gap-2">
                        <Select
                          value={attachPick}
                          onValueChange={setAttachPick}
                        >
                          <SelectTrigger className="flex-1">
                            <SelectValue placeholder="+ 添加 specialist" />
                          </SelectTrigger>
                          <SelectContent>
                            {attachableSpecialists.map((s) => (
                              <SelectItem key={s.id} value={s.id}>
                                {s.name}
                                {s.specialty ? `（${s.specialty}）` : ""}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleAttach}
                          disabled={!attachPick || attachMut.isPending}
                        >
                          挂载
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
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
