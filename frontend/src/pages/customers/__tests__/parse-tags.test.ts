// parseTagsJson 纯函数测(customers-page-split 切片 02,plan §5 AC2.3)。
//
// D4 决策:把 StoreView.buildPayload 的 tags-JSON 解析抽成纯函数,解锁不可测
// 纯逻辑(像 chat/build-working-list)。3 边界:合法 / 非法 / 空。
// 错误文案逐字锁定「标签 JSON 格式错误」(原 buildPayload 的 catch 文案)。
import { describe, expect, it } from "vitest";
import { parseTagsJson } from "../shared";

describe("customers/parseTagsJson (D4 pure function)", () => {
  it("parses valid JSON object → {tags: parsed}", () => {
    expect(parseTagsJson('{"level":"vip"}')).toEqual({ tags: { level: "vip" } });
  });

  it("parses valid JSON with whitespace padding → trimmed then parsed", () => {
    expect(parseTagsJson('   {"source":"walk-in"}   ')).toEqual({
      tags: { source: "walk-in" },
    });
  });

  it("returns error for invalid JSON → {tags: undefined, error: '标签 JSON 格式错误'}", () => {
    expect(parseTagsJson("{broken")).toEqual({
      tags: undefined,
      error: "标签 JSON 格式错误",
    });
  });

  it("empty string → {tags: undefined} (no error, no-op on profile)", () => {
    expect(parseTagsJson("")).toEqual({ tags: undefined });
    expect(parseTagsJson("").error).toBeUndefined();
  });

  it("whitespace-only string → {tags: undefined} (treated as empty)", () => {
    expect(parseTagsJson("   \n\t  ")).toEqual({ tags: undefined });
  });

  it("undefined input → {tags: undefined}", () => {
    expect(parseTagsJson(undefined)).toEqual({ tags: undefined });
  });
});
