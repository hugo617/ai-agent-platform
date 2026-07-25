// KeySpecRows —— 结构化 key-value 规格行编辑器(device-models-admin-ui 切片 02)。
//
// 后端 ``specs: dict[str, Any]`` 是自由 JSON,堵住 string 单类型会与契约不一致:
// 用户可能要存数值阈值(number)、开关(boolean)。本组件让每行带一个 type 选项
// (string / number / boolean),提交时按 type 序列化,编辑时按 typeof 反推 type。
//
// 受控组件:props 是 ``{ value: SpecRow[]; onChange }``,不持有自身 state ——
// 由父表单(react-hook-form Controller)管理,这样表单提交/dirty/reset 都一致。
//
// 序列化 / 反序列化边界(plan §4.5):
//   - 空 key(含纯空白)过滤 —— 避免 ``{ "": "..." }`` 这种垃圾键
//   - 重复 key 后者覆盖前者 —— 与 dict 字面量赋值语义一致,可预测,不报错
//   - type 序列化:string 原样 / number → Number(v) / boolean → v === "true"
//   - 反序列化 typeof 推断 type,boolean value 文本化为 "true"/"false"
//     (Select 的 value 是字符串,Input value 也是字符串,故统一文本化存储)

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export type SpecValueType = "string" | "number" | "boolean";

export interface SpecRow {
  key: string;
  value: string;
  type: SpecValueType;
}

const TYPE_OPTIONS: SpecValueType[] = ["string", "number", "boolean"];

/**
 * 序列化行数组为后端 specs dict。
 *
 * - 空 key(含纯空白)的行被丢弃
 * - 重复 key 后者覆盖前者(dict 赋值语义)
 * - 按 type 转换 value:string 原样 / number → Number / boolean → `v === "true"`
 *
 * 导出供单测 + 父表单提交时调用。
 */
export function serializeSpecs(rows: SpecRow[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue; // 空 key 过滤
    out[key] = serializeValue(row.value, row.type);
  }
  return out;
}

function serializeValue(value: string, type: SpecValueType): unknown {
  switch (type) {
    case "number":
      return Number(value);
    case "boolean":
      return value === "true";
    case "string":
    default:
      return value;
  }
}

/**
 * 反序列化后端 specs dict 为行数组(编辑 Dialog 预填用)。
 *
 * typeof 推断 type:number → "number" / boolean → "boolean" / 其他 → "string"。
 * boolean value 文本化为 "true"/"false"(Select value 必须是字符串)。
 *
 * 顺序按 Object.keys 稳定(现代 JS 引擎 string key 按插入序迭代)。
 * 导出供单测 + 父表单 openEdit 时调用。
 */
export function deserializeSpecs(specs: Record<string, unknown>): SpecRow[] {
  return Object.entries(specs).map(([key, raw]) => {
    const { value, type } = inferRow(raw);
    return { key, value, type };
  });
}

function inferRow(raw: unknown): { value: string; type: SpecValueType } {
  if (typeof raw === "number") return { value: String(raw), type: "number" };
  if (typeof raw === "boolean")
    return { value: raw ? "true" : "false", type: "boolean" };
  // string / null / undefined / 对象 / 数组 —— 一律落到 string 渲染
  return { value: raw == null ? "" : String(raw), type: "string" };
}

const EMPTY_ROW: SpecRow = { key: "", value: "", type: "string" };

interface KeySpecRowsProps {
  value: SpecRow[];
  onChange: (rows: SpecRow[]) => void;
  /** 空行时的占位提示(可选)。 */
  emptyHint?: string;
}

/**
 * 行编辑器。每行 = key Input + value Input + type Select + 删除按钮,
 * 底部一个「+ 添加规格」按钮。受控,变更通过 onChange 上抛。
 */
export function KeySpecRows({
  value,
  onChange,
  emptyHint = "暂无规格字段",
}: KeySpecRowsProps) {
  const updateRow = (index: number, patch: Partial<SpecRow>) => {
    const next = value.map((row, i) => (i === index ? { ...row, ...patch } : row));
    onChange(next);
  };

  const removeRow = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  const addRow = () => {
    onChange([...value, { ...EMPTY_ROW }]);
  };

  if (value.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">{emptyHint}</p>
        <button
          type="button"
          onClick={addRow}
          className="text-sm text-primary hover:underline"
        >
          + 添加规格
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {value.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            value={row.key}
            onChange={(e) => updateRow(i, { key: e.target.value })}
            placeholder="字段名(如 form_factor)"
            className="flex-1"
            aria-label={`规格第 ${i + 1} 行字段名`}
          />
          <Input
            value={row.value}
            onChange={(e) => updateRow(i, { value: e.target.value })}
            placeholder="值"
            className="flex-1"
            aria-label={`规格第 ${i + 1} 行值`}
          />
          <Select
            value={row.type}
            onValueChange={(v) => updateRow(i, { type: v as SpecValueType })}
            aria-label={`规格第 ${i + 1} 行类型`}
          >
            <SelectTrigger className="w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((t) => (
                <SelectItem key={t} value={t}>
                  {t === "string"
                    ? "文本"
                    : t === "number"
                      ? "数字"
                      : "开关"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => removeRow(i)}
            aria-label={`删除规格第 ${i + 1} 行`}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <button
        type="button"
        onClick={addRow}
        className="text-sm text-primary hover:underline"
      >
        + 添加规格
      </button>
    </div>
  );
}
