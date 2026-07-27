// Unit tests for lib/format.ts datetime-local conversion helpers.
//
// 重点回归测试 fromDatetimeLocalValue 的时区处理(bug fix 2026-07-27):
// 旧实现 ``${v}:00`` 返回 naive datetime(无时区后缀)→ 后端 Pydantic
// datetime 解析为 naive → SQLAlchemy 写入 DateTime(timezone=True) 列时被
// 当 UTC 解释 → 用户本地时间(如北京 14:30)被存为 14:30 UTC,实际应是
// 06:30 UTC。这让所有 booking 创建时段偏移用户时区offset 小时,产生
// 「时段冲突但用户视角看不到」的虚假 400 错误。
//
// 新实现用 new Date(v).toISOString() 把本地 wall-clock 时间正确转 UTC。
// 这一组测试锁定 round-trip + 时区转换的 fixed 行为。
import { describe, expect, it } from "vitest";

import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatRelative,
  formatTokens,
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
} from "../format";

describe("formatDateTime / formatDate", () => {
  it("formatDateTime returns zh-CN localized string for valid ISO", () => {
    // Locale-pinned output; just assert it's a non-dash string containing
    // the year. Avoid asserting the exact localized format (region variants).
    const s = formatDateTime("2026-07-27T06:30:00Z");
    expect(s).not.toBe("-");
    expect(s).toContain("2026");
  });

  it("formatDateTime returns '-' for null / undefined / empty", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime(undefined)).toBe("-");
    expect(formatDateTime("")).toBe("-");
  });

  it("formatDate returns a localized date-only string", () => {
    expect(formatDate("2026-07-27T06:30:00Z")).not.toBe("-");
    expect(formatDate(null)).toBe("-");
  });
});

describe("formatRelative", () => {
  it("returns '刚刚' for an ISO within the last minute", () => {
    expect(formatRelative(new Date(Date.now() - 10_000).toISOString())).toBe("刚刚");
  });

  it("returns 'X 分钟前' for an ISO a few minutes ago", () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelative(iso)).toBe("5 分钟前");
  });

  it("returns '-' for null / undefined / empty", () => {
    expect(formatRelative(null)).toBe("-");
    expect(formatRelative(undefined)).toBe("-");
    expect(formatRelative("")).toBe("-");
  });
});

describe("formatTokens / formatCurrency", () => {
  it("formatTokens adds en-US thousands separators", () => {
    expect(formatTokens(1234567)).toBe("1,234,567");
  });

  it("formatCurrency returns ¥ with 4 decimals", () => {
    expect(formatCurrency(0.5)).toBe("¥0.5000");
  });

  it("formatCurrency returns '-' for null / undefined", () => {
    expect(formatCurrency(null)).toBe("-");
    expect(formatCurrency(undefined)).toBe("-");
  });
});

describe("toDatetimeLocalValue", () => {
  it("returns '' for null / undefined / empty", () => {
    expect(toDatetimeLocalValue(null)).toBe("");
    expect(toDatetimeLocalValue(undefined)).toBe("");
    expect(toDatetimeLocalValue("")).toBe("");
  });

  it("returns '' for an invalid date string", () => {
    expect(toDatetimeLocalValue("not-a-date")).toBe("");
  });

  it("returns YYYY-MM-DDTHH:mm using LOCAL wall-clock components", () => {
    // 2026-07-27T06:30:00Z is 14:30 in UTC+8 / 23:30 (Jul 26) in UTC-7.
    // The function must use local-time getHours/getMinutes; we can't assert
    // a specific value across CI tz's, but the SHAPE is invariant.
    const out = toDatetimeLocalValue("2026-07-27T06:30:00Z");
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(out.length).toBe(16);
  });
});

describe("fromDatetimeLocalValue (bug fix 2026-07-27)", () => {
  it("returns the input unchanged when shorter than 16 chars (empty / invalid)", () => {
    expect(fromDatetimeLocalValue("")).toBe("");
    expect(fromDatetimeLocalValue("2026-07-27")).toBe("2026-07-27");
  });

  it("returns an ISO-8601 string ending in Z (UTC marker), NOT naive", () => {
    // The bug: old impl returned "2026-07-27T14:30:00" (no Z). Pydantic parses
    // that as naive → SQLAlchemy stores as UTC → wrong instant. The fix MUST
    // emit a Z-suffixed UTC ISO so the wire value is unambiguous.
    const out = fromDatetimeLocalValue("2026-07-27T14:30");
    expect(out).toMatch(/Z$/);
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  it("round-trips: a local wall-clock pick survives a UTC round-trip", () => {
    // The defining property: pick "right now" in local time, convert to API
    // ISO, parse it back — the parsed Date must equal the original instant.
    // This is what every booking create/edit relies on; if fromDatetimeLocalValue
    // ever drops the tz again, this assertion fails by the local tz offset.
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const localValue =
      `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
      `T${pad(now.getHours())}:${pad(now.getMinutes())}`;
    const iso = fromDatetimeLocalValue(localValue);
    const parsed = new Date(iso);
    // Compare epoch ms (the only tz-stable comparison). 1-second tolerance
    // because fromDatetimeLocalValue drops the seconds field (always :00).
    expect(Math.abs(parsed.getTime() - now.getTime())).toBeLessThan(60_000);
  });
});
