// design-system-token-foundation 切片 02 —— ui/ 组件库语义色映射渲染测试。
//
// 覆盖 plan 切片 02 AC 第 5 条「Badge/Toast/Avatar 含新 className 的 fixture
// 渲染通过」。目的不是测交互逻辑,而是**锁住语义色映射不回退**:断言新
// className(`bg-success` / `bg-warning` / `bg-danger` / `bg-success/10` 等)
// 真的出现在渲染 DOM 里 —— 切片 02 把硬编码原色(emerald/amber/red)映射到
// semantic token 后,这些 className 必须落地。哪天有人把 `bg-success` 改回
// `bg-emerald-500`,这组测试会变红。
//
// 范式沿用 key-spec-rows.test.tsx(同目录 ui/ 单测,中文注释 + describe/it)。
// Badge/Avatar 是无状态纯 DOM 组件,直接 render;Toast 走 ToastProvider +
// useToast 的真实路径(不 mock,验证渲染层 className 真落地)。
import { describe, expect, it } from "vitest";
import { act, useEffect } from "react";
import { render, screen } from "@testing-library/react";

import { Avatar } from "./avatar";
import { Badge } from "./badge";
import { ToastProvider, useToast } from "./toast";

// 取渲染后的 class 字符串做子串断言(比 toHaveClass 的精确匹配更宽松 ——
// 允许 cva / cn 拼接顺序变化,只验「目标 token className 在不在里面」)。
function classesOf(el: HTMLElement): string {
  return el.className;
}

// Toast 的 title 文本在内层 <div class="text-sm font-semibold">,变体 className
// 在外层容器。从 title 节点向上找到那个外层容器 —— 用 parentElement 两层
// (title div → flex 行 div → toast 容器),而非耦合到 Tailwind 工具类
// (pointer-events-auto 等),避免样式重构时测试因非语义原因脆裂。
function toastContainerOf(titleEl: HTMLElement): HTMLElement {
  // title div → "flex items-center gap-2" 行 → toast 外层容器
  return titleEl.parentElement?.parentElement as HTMLElement;
}

// ---- Badge:语义 dot 色 + success variant 映射到 token ----
describe("Badge — semantic token mapping (slice 02)", () => {
  it("dot-success 映射到 bg-success(green dot,was emerald-500)", () => {
    render(<Badge variant="dot-success">运行中</Badge>);
    const badge = screen.getByText("运行中");
    // ::before 的 bg 由 [&::before]:bg-success 注入,出现在 badge className 里
    expect(classesOf(badge)).toContain("[&::before]:bg-success");
    // 反向断言:旧硬编码 emerald-500 不应再出现(锁回退)
    expect(classesOf(badge)).not.toContain("emerald");
  });

  it("dot-warning 映射到 bg-warning(amber dot,was amber-500)", () => {
    render(<Badge variant="dot-warning">待处理</Badge>);
    const badge = screen.getByText("待处理");
    expect(classesOf(badge)).toContain("[&::before]:bg-warning");
    expect(classesOf(badge)).not.toContain("amber-500");
  });

  it("dot-destructive 映射到 bg-danger(red dot,was red-500)", () => {
    render(<Badge variant="dot-destructive">失败</Badge>);
    const badge = screen.getByText("失败");
    expect(classesOf(badge)).toContain("[&::before]:bg-danger");
    expect(classesOf(badge)).not.toContain("red-500");
  });

  it("success variant 映射到 bg-success + success-foreground(was emerald-500 + white)", () => {
    render(<Badge variant="success">已保存</Badge>);
    const badge = screen.getByText("已保存");
    expect(classesOf(badge)).toContain("bg-success");
    expect(classesOf(badge)).toContain("text-success-foreground");
    expect(classesOf(badge)).not.toContain("emerald");
    expect(classesOf(badge)).not.toContain("text-white");
  });

  // knowledge-tiered reader-ui slice 01 — group scope 徽章依赖 warning 实心
  // variant(platform→destructive / group→warning / store→success 三色,plan §4.5
  // G3)。锁住 warning 实心映射到 semantic token,不回退到 amber-500。
  it("warning variant 映射到 bg-warning + warning-foreground(reader-ui slice 01)", () => {
    render(<Badge variant="warning">集团</Badge>);
    const badge = screen.getByText("集团");
    expect(classesOf(badge)).toContain("bg-warning");
    expect(classesOf(badge)).toContain("text-warning-foreground");
    expect(classesOf(badge)).not.toContain("amber");
  });

  it("中性 dot / dot-muted 不受映射影响(仍 bg-current,无语义色)", () => {
    render(<Badge variant="dot-muted">已确认</Badge>);
    const badge = screen.getByText("已确认");
    expect(classesOf(badge)).toContain("[&::before]:bg-current");
    // 中性 dot 不该冒出任何语义 token(它是 grey,不是 success/warning/danger)
    expect(classesOf(badge)).not.toMatch(/bg-(success|warning|danger)/);
  });
});

// ---- Toast:success / destructive 变体映射到 alpha 约定 token ----
describe("Toast — semantic token mapping (slice 02)", () => {
  // 把 useToast 暴露给测试:在 ToastProvider 内 render 一个 probe 组件,
  // mount 后通过 useEffect 把 toast API 传出去(不 mock Toast 内部)。
  function ToastProbe({
    onReady,
  }: {
    onReady: (t: ReturnType<typeof useToast>) => void;
  }) {
    const t = useToast();
    useEffect(() => {
      onReady(t);
    }, [onReady, t]);
    return null;
  }

  // Toast 是强语义提示(成功/错误反馈),用实心 bg-success + 深色前景(对齐
  // badge success / button destructive 范式),而非 Feature B 业务页的浅底 tint
  // (bg-X/10 + text-X DEFAULT 在亮色仅 2.96 / 暗色 ~1.2,不达 WCAG AA 4.5;
  //  实心 bg-success 亮 5.42 / 暗 8.31 全过 —— 见 plan §4.5① v2 对比度表)。
  function renderToast() {
    const toastApi = { current: null as ReturnType<typeof useToast> | null };
    render(
      <ToastProvider>
        <ToastProbe onReady={(t) => (toastApi.current = t)} />
      </ToastProvider>
    );
    return toastApi;
  }

  it("success toast 映射到实心 bg-success + text-success-foreground(was emerald-*)", async () => {
    const toastApi = renderToast();
    await act(async () => {
      toastApi.current!.success("已保存");
    });
    const title = await screen.findByText("已保存");
    const toast = toastContainerOf(title);
    expect(classesOf(toast)).toContain("bg-success");
    expect(classesOf(toast)).toContain("text-success-foreground");
    // 锁回退:旧 emerald 系不应再出现
    expect(classesOf(toast)).not.toContain("emerald");
  });

  it("destructive(error)toast 映射到实心 bg-danger + text-danger-foreground(was red-*)", async () => {
    const toastApi = renderToast();
    await act(async () => {
      toastApi.current!.error("保存失败");
    });
    const title = await screen.findByText("保存失败");
    const toast = toastContainerOf(title);
    expect(classesOf(toast)).toContain("bg-danger");
    expect(classesOf(toast)).toContain("text-danger-foreground");
    expect(classesOf(toast)).not.toContain("red-");
  });

  it("loading toast 不含语义色(走 border-border + bg-background 中性样式)", async () => {
    const toastApi = renderToast();
    await act(async () => {
      toastApi.current!.push({ title: "加载中…", variant: "loading" });
    });
    const title = await screen.findByText("加载中…");
    const toast = toastContainerOf(title);
    expect(classesOf(toast)).toContain("border-border");
    expect(classesOf(toast)).toContain("bg-background");
    expect(classesOf(toast)).not.toMatch(/(bg|border|text)-(success|danger)/);
  });
});

// ---- Avatar:8 色环保留不动(设计性多色边界,AC 第 3 条)----
describe("Avatar — 8-color palette preserved (slice 02 boundary)", () => {
  it("COLOR_PALETTE 8 色全保留:渲染按 name hash 命中其中一个", () => {
    // 取若干 name,断言渲染出的 avatar 命中 8 色环之一(而非被 token 化)
    const palette = [
      "bg-blue-500",
      "bg-emerald-500",
      "bg-amber-500",
      "bg-rose-500",
      "bg-violet-500",
      "bg-cyan-500",
      "bg-orange-500",
      "bg-pink-500",
    ];
    const names = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi"];
    for (const name of names) {
      const { container } = render(<Avatar name={name} />);
      const div = container.firstChild as HTMLElement;
      const cls = classesOf(div);
      // 必须命中 palette 之一(8 色环按 hash 分配,每个 name 落到某色)
      const hit = palette.some((p) => cls.includes(p));
      expect(hit, `${name} 应命中 8 色环之一,实际 class: ${cls}`).toBe(true);
    }
  });

  it("无图片 fallback 走 initials + palette 色环(不被 semantic token 替代)", () => {
    const { container } = render(<Avatar name="Alice Wonderland" />);
    const div = container.firstChild as HTMLElement;
    expect(div.textContent).toContain("AW"); // initials = AW
    // 8 色环保留:不应出现 semantic token(那是 Feature A 的语义边界,avatar 是设计性多色)
    expect(classesOf(div)).not.toMatch(/bg-(success|warning|danger|info)/);
  });
});
