// 设计系统 token 基建测试(design-system-token-foundation 切片 01)。
//
// 切片 01 只落「四 token 存在且可消费」的最小可验证路径:index.css 定义 +
// tailwind.config.js 暴露。本测试用 CSS / 配置文本断言锁住契约(jsdom 取不到
// 计算色,plan §9 风险已明确降级为文本断言)。
//
// 断言三层:
//   ① index.css :root 含 4 token + 4 foreground(HSL 逐字 = B3 定稿亮色)
//   ② index.css .dark 含 4 token + 4 foreground(HSL 逐字 = B3 定稿暗色变体)
//   ③ tailwind.config.js theme.extend.colors 暴露 success/warning/danger/info
//      各含 DEFAULT + foreground 双键(照 destructive 范式)
//
// 不测:计算色(留给 plan §4.6 手动 WCAG 验证)/ 组件映射(切片 02)/ 暗色切换
// 运行时(降级为文本存在性,与 plan §9 风险缓解一致)。
import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const indexCss = readFileSync(resolve(here, "../index.css"), "utf8");
const tailwindConfig = readFileSync(
  resolve(here, "../../tailwind.config.js"),
  "utf8",
);

// B3 定稿 token 值(来源:harness/docs/plan-frontend-design-system-overview.md
// 「目标架构」段 + plan-design-system-token-foundation.md §4.5①)。逐字钉死,
// 调色须同步改这里,防漂移。
//
// foreground v2 修订:从 v1 的纯白(0 0% 100%)改为深蓝灰 222.2 47.4% 11.2%(对齐
// 现有 --secondary-foreground / --primary-foreground 亮色范式)。原因:纯白前景对
// B3 彩色底 8 组对比度全部不达 WCAG AA 4.5:1(见 plan §4.5① 对比度表);深字前景
// 8 组全部达标(最低 4.72,最高 9.54)。B3 底色逐字不变。
const LIGHT_TOKENS = [
  // [tokenName, hslValue]
  ["--success", "152 76% 36%"],
  ["--success-foreground", "222.2 47.4% 11.2%"],
  ["--warning", "35 92% 50%"],
  ["--warning-foreground", "222.2 47.4% 11.2%"],
  ["--danger", "0 84% 60%"],
  ["--danger-foreground", "222.2 47.4% 11.2%"],
  ["--info", "189 90% 42%"],
  ["--info-foreground", "222.2 47.4% 11.2%"],
] as const;

const DARK_TOKENS = [
  ["--success", "152 64% 48%"],
  ["--success-foreground", "222.2 47.4% 11.2%"],
  ["--warning", "38 95% 58%"],
  ["--warning-foreground", "222.2 47.4% 11.2%"],
  ["--danger", "0 80% 64%"],
  ["--danger-foreground", "222.2 47.4% 11.2%"],
  ["--info", "189 80% 55%"],
  ["--info-foreground", "222.2 47.4% 11.2%"],
] as const;

describe("index.css :root — 亮色 token(B3 定稿逐字)", () => {
  // 抽 :root {...} 段(从 `:root {` 到匹配的 `}`),避免 .dark 段干扰。
  const rootBlock = indexCss.slice(0, indexCss.indexOf(".dark"));

  it.each(LIGHT_TOKENS)("%s: %s 存在于 :root 段", (name, value) => {
    expect(rootBlock).toContain(`${name}: ${value};`);
  });
});

describe("index.css .dark — 暗色 token(B3 定稿提亮变体逐字)", () => {
  // 抽 .dark {...} 段(从 `.dark {` 到文件末尾的 colors 块结束)。
  const darkBlock = indexCss.slice(indexCss.indexOf(".dark"));

  it.each(DARK_TOKENS)("%s: %s 存在于 .dark 段", (name, value) => {
    expect(darkBlock).toContain(`${name}: ${value};`);
  });
});

describe("tailwind.config.js — 暴露 success/warning/danger/info", () => {
  // 照 destructive 范式:DEFAULT + foreground 双键,值引用 CSS var。
  const SEMANTIC_COLORS = ["success", "warning", "danger", "info"] as const;

  it.each(SEMANTIC_COLORS)(
    "%s 含 DEFAULT + foreground 双键(照 destructive 范式)",
    (color) => {
      expect(tailwindConfig).toContain(
        `DEFAULT: "hsl(var(--${color}))"`,
      );
      expect(tailwindConfig).toContain(
        `foreground: "hsl(var(--${color}-foreground))"`,
      );
    },
  );

  it("destructive 既有命名保留不动(本 feature 不做 destructive → danger 迁移)", () => {
    expect(tailwindConfig).toMatch(
      /destructive:\s*\{\s*DEFAULT:\s*"hsl\(var\(--destructive\)\)"/,
    );
  });
});
