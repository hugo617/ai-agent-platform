// KeySpecRows 序列化逻辑单测(device-models-admin-ui 切片 02)。
//
// 这是本 feature 唯一的单测，覆盖 plan §5 点名的核心逻辑：
//   ① 空 key 过滤 —— 序列化时空 key 的行被丢弃
//   ② 重复 key 后者覆盖 —— dict 字面量赋值语义（后者覆盖前者），不报错
//   ③ 三类型序列化 —— string 原样 / number → Number(v) / boolean → v === "true"
//   ④ 反序列化 round-trip —— typeof 推断 type + value 文本化
//
// 单测只断言纯函数 serializeSpecs / deserializeSpecs（plan AC 列为可测边界），
// 组件渲染层（Input/Select/按钮交互）不测 —— 对齐 devices-page 现状（无组件
// 集成测），且 UI 行为靠手测 + build 兜底。
import { describe, expect, it } from "vitest";

import {
  deserializeSpecs,
  serializeSpecs,
  type SpecRow,
} from "./key-spec-rows";

describe("serializeSpecs", () => {
  it("① 空 key 过滤：key 为空字符串的行被丢弃", () => {
    const rows: SpecRow[] = [
      { key: "", value: "ignored", type: "string" },
      { key: "form_factor", value: "ring", type: "string" },
      { key: "   ", value: "blank-key", type: "string" }, // 仅空白也视作空
    ];
    expect(serializeSpecs(rows)).toEqual({ form_factor: "ring" });
  });

  it("② 重复 key 后者覆盖前者（dict 赋值语义，不报错）", () => {
    const rows: SpecRow[] = [
      { key: "threshold", value: "60", type: "number" },
      { key: "threshold", value: "80", type: "number" },
    ];
    expect(serializeSpecs(rows)).toEqual({ threshold: 80 });
  });

  it("③ 三类型序列化：string 原样 / number → Number(v) / boolean → v === 'true'", () => {
    const rows: SpecRow[] = [
      { key: "form_factor", value: "ring", type: "string" },
      { key: "threshold", value: "80", type: "number" },
      { key: "enabled", value: "true", type: "boolean" },
      { key: "deprecated", value: "false", type: "boolean" },
      { key: "count", value: "0", type: "number" }, // 边界：0 不是 falsy 漏网
    ];
    expect(serializeSpecs(rows)).toEqual({
      form_factor: "ring",
      threshold: 80,
      enabled: true,
      deprecated: false,
      count: 0,
    });
  });

  it("空行数组 → 空对象", () => {
    expect(serializeSpecs([])).toEqual({});
  });
});

describe("deserializeSpecs", () => {
  it("④ 反序列化：typeof 推断 type + boolean value 文本化为 'true'/'false'", () => {
    const specs = {
      form_factor: "ring", // string
      threshold: 80, // number
      enabled: true, // boolean
      deprecated: false, // boolean
    };
    expect(deserializeSpecs(specs)).toEqual<SpecRow[]>([
      { key: "form_factor", value: "ring", type: "string" },
      { key: "threshold", value: "80", type: "number" },
      { key: "enabled", value: "true", type: "boolean" },
      { key: "deprecated", value: "false", type: "boolean" },
    ]);
  });

  it("空对象 → 空行数组", () => {
    expect(deserializeSpecs({})).toEqual([]);
  });

  it("round-trip：serialize ∘ deserialize 不丢类型（三类型混合）", () => {
    const original: SpecRow[] = [
      { key: "form_factor", value: "patch", type: "string" },
      { key: "threshold", value: "120", type: "number" },
      { key: "enabled", value: "true", type: "boolean" },
    ];
    const serialized = serializeSpecs(original);
    const roundTripped = deserializeSpecs(serialized);
    // round-trip 后类型推断与原始一致（顺序按 Object.keys 稳定）
    expect(roundTripped).toEqual(original);
  });
});
