// DeviceModelsAdminPage —— 设备型号目录管理页(device-models-admin-ui 切片 02)。
//
// 平台级(super_admin only)资源,与 groups-page 同范式:
//   - 路由 /device-models 挂 RequireSuperAdmin(见 App.tsx),非 super_admin
//     重定向到 /;后端 POST/PUT/DELETE 已 require_super_admin() 双保险。
//   - 列表(名称 / 品牌 / 规格摘要 / 单位成本 / 更新时间 / 操作)+ 顶部搜索框
//     (client-side filter)+ 新增 Dialog + 编辑 Dialog + 软删确认 Dialog。
//
// 与 groups-page 的差异(device-models-admin-ui 特有):
//   - specs 是自由 JSON → 用 KeySpecRows 结构化行编辑器(string/number/boolean)
//   - unit_cost 是 Numeric(12,2) 货币 → 列表内联 ``¥${Number(...).toFixed(2)}``
//     (不复用 formatCurrency,它 toFixed(4) 是 token cost 设计)
//   - brand datalist 联想(原生 <datalist>,options 从已拉列表 unique brands)
//   - 整页只 super_admin 能进,无 canManage 只读分支(groups 允许 owner 只读)
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Cpu, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";

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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { FormField as Field } from "@/components/ui/form-field";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ListState } from "@/components/ui/list-state";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/api/client";
import type { DeviceModelRead } from "@/api/types";
import {
  useCreateDeviceModel,
  useDeleteDeviceModel,
  useDeviceModels,
  useUpdateDeviceModel,
} from "@/hooks/queries";
import { formatDateTime as fmt } from "@/lib/format";
import {
  KeySpecRows,
  deserializeSpecs,
  serializeSpecs,
  type SpecRow,
} from "@/components/ui/key-spec-rows";

// ---------- create/edit form schema ----------
// specs 不进 zod schema —— 它是动态行数组,由 Controller 包 KeySpecRows 管理,
// 提交时手动 serializeSpecs(rows) 拼进 payload。unit_cost 是字符串形态的
// Decimal(后端 Numeric(12,2) 经 JSON 序列化为 "299.00"),refine 校验 0-2 位小数。
const formSchema = z.object({
  name: z.string().min(1, "名称不能为空").max(200),
  brand: z.string().max(200).optional(),
  supplier: z.string().max(200).optional(),
  unit_cost: z
    .string()
    .min(1, "单位成本不能为空")
    .refine((v) => /^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0, {
      message: "请输入合法金额(最多两位小数,非负)",
    }),
});
type FormValues = z.input<typeof formSchema>;

interface FormState extends FormValues {
  specs: SpecRow[];
}

const EMPTY_FORM: FormState = {
  name: "",
  brand: "",
  supplier: "",
  unit_cost: "",
  specs: [],
};

// 规格摘要:取 specs.form_factor(后端惯例 key,驱动门店下拉分组);无则
// JSON.stringify 截断 40 字符 + "…" 兜底。空 specs 显示 "-"。
function specSummary(specs: Record<string, unknown>): string {
  if (Object.keys(specs).length === 0) return "-";
  const ff = specs.form_factor;
  if (typeof ff === "string" && ff) return ff;
  const json = JSON.stringify(specs);
  return json.length > 40 ? `${json.slice(0, 40)}…` : json;
}

export function DeviceModelsAdminPage() {
  const toast = useToast();

  // 整页在 RequireSuperAdmin 守卫内,useDeviceModels 返回的 union 在此视角
  // 必然是 DeviceModelRead[](后端按 platform_role 分叉,super_admin 拿全字段)。
  // narrow 用类型断言而非运行时判断 —— 守卫已是真相源,运行时校验是冗余。
  // 不把 narrow 结果赋给中间变量:react-query 的 data 引用在不变时是稳定的,
  // 中间 `?? []` 每次 render 生成新数组引用会让下游 useMemo(exhaustive-deps)
  // 每次重算。改在每个 useMemo 内部 narrow,依赖稳定引用 rawModels。
  const { data: rawModels, isLoading } = useDeviceModels();

  const createMut = useCreateDeviceModel();
  const updateMut = useUpdateDeviceModel();
  const deleteMut = useDeleteDeviceModel();

  // ---- dialogs ----
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<DeviceModelRead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeviceModelRead | null>(null);

  // KeySpecRows 的行 state(specs 不进 react-hook-form,独立 state + Controller
  // 风格手动管理)。表单 reset 时同步重置。
  const [specRows, setSpecRows] = useState<SpecRow[]>([]);

  // 顶部搜索框
  const [query, setQuery] = useState("");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  });

  // brand datalist options:从已拉型号列表 unique 非空 brands 派生。
  // useMemo 避免每次 render 重算。super_admin 视角下 brands 跨全平台。
  const brandOptions = useMemo(() => {
    const set = new Set<string>();
    for (const m of (rawModels ?? []) as DeviceModelRead[]) {
      if (m.brand && m.brand.trim()) set.add(m.brand.trim());
    }
    return Array.from(set).sort();
  }, [rawModels]);

  const openCreate = () => {
    setEditing(null);
    form.reset({
      name: "",
      brand: "",
      supplier: "",
      unit_cost: "",
    });
    setSpecRows([]);
    setFormOpen(true);
  };

  const openEdit = (m: DeviceModelRead) => {
    setEditing(m);
    form.reset({
      name: m.name,
      brand: m.brand ?? "",
      supplier: m.supplier ?? "",
      unit_cost: m.unit_cost,
    });
    // 反序列化当前 specs → 行(让用户改完 round-trip 不丢类型)
    setSpecRows(deserializeSpecs(m.specs));
    setFormOpen(true);
  };

  const handleSubmit = async (values: FormValues) => {
    const payload = {
      name: values.name.trim(),
      brand: values.brand?.trim() || null,
      supplier: values.supplier?.trim() || null,
      unit_cost: values.unit_cost,
      specs: serializeSpecs(specRows),
    };
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, payload });
        toast.success("已更新设备型号", editing.name);
      } else {
        await createMut.mutateAsync(payload);
        toast.success("已创建设备型号", values.name);
      }
      setFormOpen(false);
    } catch (err) {
      toast.error(editing ? "更新失败" : "创建失败", apiErrorMessage(err));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMut.mutateAsync(deleteTarget.id);
      toast.success("已删除设备型号", deleteTarget.name);
      setDeleteTarget(null);
    } catch (err) {
      toast.error("删除失败", apiErrorMessage(err));
    }
  };

  // client-side filter:按 name / brand / supplier 模糊匹配(大小写不敏感)。
  // device_models 预期表小,不分页不服务端搜索(对齐 groups-ui 范式)。
  const filtered = useMemo(() => {
    const all = (rawModels ?? []) as DeviceModelRead[];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter((m) =>
      [m.name, m.brand, m.supplier].some((x) => x?.toLowerCase().includes(q)),
    );
  }, [rawModels, query]);

  // 列表计数 + 空态判断用 rawModels(未经搜索过滤),与 groups-page 范式一致。
  const totalCount = (rawModels ?? []).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="设备型号"
        subtitle="维护平台级设备型号目录,供门店设备入库时选择。"
        actions={
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> 新建型号
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>型号列表</CardTitle>
          <CardDescription>共 {totalCount} 个型号</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="按名称 / 品牌 / 供应商搜索"
              className="max-w-sm"
              aria-label="搜索型号"
            />
          </div>

          <ListState
            isLoading={isLoading}
            isEmpty={filtered.length === 0}
            loadingVariant="skeleton"
            skeletonRows={4}
            emptyContent={
              <EmptyState
                icon={Cpu}
                title={totalCount === 0 ? "暂无型号" : "无匹配结果"}
                description={
                  totalCount === 0
                    ? "点击右上角「新建型号」开始建立目录"
                    : "尝试调整搜索关键词"
                }
              />
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>品牌</TableHead>
                  <TableHead>规格摘要</TableHead>
                  <TableHead>单位成本</TableHead>
                  <TableHead>更新时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">{m.name}</TableCell>
                    <TableCell>{m.brand ?? "-"}</TableCell>
                    <TableCell className="max-w-[240px] truncate text-muted-foreground">
                      {specSummary(m.specs)}
                    </TableCell>
                    <TableCell>
                      {/* 内联 toFixed(2):unit_cost 是 Numeric(12,2) 货币,
                          formatCurrency 用 toFixed(4) 是 token cost 设计,
                          复用会渲染 ¥299.5000。见 plan §4.5 / §4.6。 */}
                      {`¥${Number(m.unit_cost).toFixed(2)}`}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmt(m.updated_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openEdit(m)}>
                            <Pencil className="mr-2 h-4 w-4" /> 编辑
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => setDeleteTarget(m)}
                          >
                            <Trash2 className="mr-2 h-4 w-4" /> 删除
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ListState>
        </CardContent>
      </Card>

      {/* brand datalist —— 原生联想,无新组件,不影响后端契约(brand 仍 str|null) */}
      <datalist id="device-model-brands">
        {brandOptions.map((b) => (
          <option key={b} value={b} />
        ))}
      </datalist>

      {/* create / edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑型号" : "新建型号"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "修改型号基础信息与规格。"
                : "新增一个平台级设备型号,供门店入库时选择。"}
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            <Field label="名称 *">
              <Input
                {...form.register("name")}
                placeholder="如:智能戒指 R2"
              />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.name.message}
                </p>
              )}
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field label="品牌(可选)">
                <Input
                  {...form.register("brand")}
                  placeholder="如:Acme"
                  list="device-model-brands"
                />
              </Field>
              <Field label="供应商(可选)">
                <Input {...form.register("supplier")} placeholder="如:深圳 XX" />
              </Field>
            </div>

            <Field label="单位成本 *">
              <Input
                {...form.register("unit_cost")}
                placeholder="如:299.00"
                inputMode="decimal"
              />
              {form.formState.errors.unit_cost && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.unit_cost.message}
                </p>
              )}
            </Field>

            <Field label="规格(可选)">
              <KeySpecRows value={specRows} onChange={setSpecRows} />
            </Field>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setFormOpen(false)}
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

      {/* delete confirm dialog —— 话术准确传达软删语义 */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定删除型号「{deleteTarget?.name}」?该操作为软删除,已被设备引用的
              型号不会被硬删(仅从目录中隐藏),名称可被新型号复用。
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
