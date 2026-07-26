/**
 * config-dialog tests (booking-schedule-grid 切片 03).
 *
 * Seam: the Dialog is tested as a pure presentational component — it receives
 * the loaded configs + role flag as props and calls ``onSubmit`` with the
 * gathered payload. We do NOT mock @/hooks/queries: the Dialog deliberately
 * takes pre-loaded data as props (mirrors shared-dialog.tsx's "Dialog is a
 * pure body, parent owns mutation + toast" convention), so the test drives it
 * by passing props + spying on ``onSubmit``. This is the agreed seam; no test
 * reaches into internals.
 *
 * 5 用例覆盖 plan AC7:
 *  - 渲染(标题可见)
 *  - super_admin → 两栏(平台默认 + 当前 target 店覆盖)
 *  - owner → 一栏(当前店覆盖)
 *  - duration 切换:点 90 预设按钮 → 自定义数字输入同步为 90
 *  - 提交调 mock:点保存 → onSubmit 被以 3 字段 payload 调用
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "@/test/test-utils";
import { BookingConfigDialog } from "../config-dialog";
import type { BookingConfig } from "@/api/types";

// ---- fixtures ---------------------------------------------------------------
// Backend-accurate shape: window_* are "HH:MM" 5-char strings, tenant_id null
// = platform default row. Two rows stand in for the two tiers the Dialog shows
// in super_admin mode.
const PLATFORM_CONFIG: BookingConfig = {
  id: "cfg_platform_1",
  tenant_id: null,
  default_duration_minutes: 45,
  window_start: "08:00",
  window_end: "22:00",
  created_at: "2026-07-20T00:00:00",
  updated_at: "2026-07-20T00:00:00",
};

const TENANT_CONFIG: BookingConfig = {
  id: "cfg_tenant_1",
  tenant_id: "tn_target",
  default_duration_minutes: 60,
  window_start: "09:00",
  window_end: "21:00",
  created_at: "2026-07-21T00:00:00",
  updated_at: "2026-07-21T00:00:00",
};

afterEach(() => vi.clearAllMocks());

describe("BookingConfigDialog", () => {
  it("渲染:Dialog 打开时标题与表单字段可见", () => {
    renderWithProviders(
      <BookingConfigDialog
        open
        isSuperAdmin={false}
        targetTenantName="测试店"
        platformConfig={null}
        tenantConfig={TENANT_CONFIG}
        isPending={false}
        onClose={() => {}}
        onSubmit={async () => {}}
      />,
    );

    expect(screen.getByText(/预约配置/)).toBeInTheDocument();
    // duration 预设按钮可见(45/60/90)
    expect(screen.getByRole("button", { name: "45 分钟" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "60 分钟" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "90 分钟" })).toBeInTheDocument();
    // 保存按钮可见
    expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument();
  });

  it("super_admin:渲染两栏(平台默认 + 当前 target 店覆盖)", () => {
    renderWithProviders(
      <BookingConfigDialog
        open
        isSuperAdmin
        targetTenantName="测试店"
        platformConfig={PLATFORM_CONFIG}
        tenantConfig={TENANT_CONFIG}
        isPending={false}
        onClose={() => {}}
        onSubmit={async () => {}}
      />,
    );

    // 两栏各有一个 <h4> 栏标题(level=4)。用 heading role 精确定位,
    // 避开 DialogDescription 文案里同样含「平台默认」的干扰。
    const columnTitles = screen.getAllByRole("heading", { level: 4 });
    expect(columnTitles.length).toBe(2);
    expect(columnTitles[0].textContent).toBe("平台默认");
    expect(columnTitles[1].textContent).toBe("当前门店:测试店");
  });

  it("owner:仅渲染一栏(当前店覆盖),无平台默认栏", () => {
    renderWithProviders(
      <BookingConfigDialog
        open
        isSuperAdmin={false}
        targetTenantName="测试店"
        platformConfig={null}
        tenantConfig={TENANT_CONFIG}
        isPending={false}
        onClose={() => {}}
        onSubmit={async () => {}}
      />,
    );

    // 仅一个 <h4> 栏标题(当前门店),无「平台默认」栏。
    const columnTitles = screen.getAllByRole("heading", { level: 4 });
    expect(columnTitles.length).toBe(1);
    expect(columnTitles[0].textContent).toBe("当前门店:测试店");
  });

  it("duration:点 90 预设 → 自定义数字输入同步为 90,45/60 按钮变为非选中态", () => {
    renderWithProviders(
      <BookingConfigDialog
        open
        isSuperAdmin={false}
        targetTenantName="测试店"
        platformConfig={null}
        tenantConfig={TENANT_CONFIG} // 初始 duration=60
        isPending={false}
        onClose={() => {}}
        onSubmit={async () => {}}
      />,
    );

    // 初始:60 预设按钮带 aria-pressed=true(选中态),数字输入=60
    const preset60 = screen.getByRole("button", { name: "60 分钟" });
    const preset90 = screen.getByRole("button", { name: "90 分钟" });
    expect(preset60).toHaveAttribute("aria-pressed", "true");
    expect(preset90).toHaveAttribute("aria-pressed", "false");

    // 数字输入 — 用 role=spinbox 找到
    const numInput = screen.getByRole("spinbutton") as HTMLInputElement;
    expect(numInput.value).toBe("60");

    // 点 90 → 数字输入同步为 90,90 按钮变选中,60 变非选中
    fireEvent.click(preset90);
    expect(numInput.value).toBe("90");
    expect(preset90).toHaveAttribute("aria-pressed", "true");
    expect(preset60).toHaveAttribute("aria-pressed", "false");
  });

  it("提交:点保存 → onSubmit 被以当前店 3 字段 payload 调用(scope=tenant)", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <BookingConfigDialog
        open
        isSuperAdmin={false}
        targetTenantName="测试店"
        platformConfig={null}
        tenantConfig={TENANT_CONFIG} // duration=60, window 09:00-21:00
        isPending={false}
        onClose={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    // owner 一栏 → scope=tenant,payload 来自 TENANT_CONFIG
    expect(onSubmit).toHaveBeenCalledWith("tenant", {
      default_duration_minutes: 60,
      window_start: "09:00",
      window_end: "21:00",
    });
  });
});
