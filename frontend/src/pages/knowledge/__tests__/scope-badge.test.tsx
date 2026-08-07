// scope-badge 组件测试(reader-ui slice 01 G3)。
//
// 锁住 scope → 实心 Badge variant 的三色映射(platform→destructive 红 /
// group→warning 琉 / store→success 绿)+ 中文标签。这是「分级知识库落到门店
// 眼睛里」的核心视觉契约 —— 哪天有人把映射改错(比如 group 误用 success),
// 这组测试变红。
//
// 范式沿用 badge-toast-avatar.test.tsx:断言渲染 DOM 的 className 含目标
// semantic token(bg-destructive / bg-warning / bg-success),而非耦合到 cva
// 拼接顺序。Badge 是无状态纯组件,直接 render 不需要 providers。
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScopeBadge } from "../scope-badge";

function classesOf(el: HTMLElement): string {
  return el.className;
}

describe("ScopeBadge — scope→实心 variant 三色映射(reader-ui slice 01 G3)", () => {
  it("platform → destructive 实心(平台下发,红)", () => {
    render(<ScopeBadge scope="platform" />);
    const badge = screen.getByText("平台");
    expect(classesOf(badge)).toContain("bg-destructive");
    expect(classesOf(badge)).toContain("text-destructive-foreground");
  });

  it("group → warning 实心(集团下发,琉)", () => {
    render(<ScopeBadge scope="group" />);
    const badge = screen.getByText("集团");
    expect(classesOf(badge)).toContain("bg-warning");
    expect(classesOf(badge)).toContain("text-warning-foreground");
  });

  it("store → success 实心(本店自建,绿)", () => {
    render(<ScopeBadge scope="store" />);
    const badge = screen.getByText("本店");
    expect(classesOf(badge)).toContain("bg-success");
    expect(classesOf(badge)).toContain("text-success-foreground");
  });

  it("三态都用实心 variant,不用 dot variant(与状态徽章语义分层)", () => {
    // dot variant 用 bg-muted + [&::before]:bg-XXX;实心 variant 用 bg-XXX。
    // 这条锁住「scope 用实心,不混进 dot」—— dot 是状态徽章(statusBadge)的专属。
    for (const scope of ["platform", "group", "store"] as const) {
      const { unmount } = render(<ScopeBadge scope={scope} />);
      const badge = screen.getByText(/平台|集团|本店/);
      expect(classesOf(badge)).not.toContain("bg-muted");
      expect(classesOf(badge)).not.toContain("[&::before]");
      unmount();
    }
  });
});
