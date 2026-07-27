// booking-config 系列 hooks 的单元测试。
//
// 为什么单独建文件:hooks 行为 bug(如 enabled 门控缺失)在 HqView 的全 mock
// 集成测试里无法被捕捉 —— vi.mock("@/hooks/queries") 把 hook 整个替换成 stub,
// 删掉 hook 里的 ``enabled`` 字段集成测试照样全绿,但生产会 403(原 bug 就是这么
// 漏网的)。这里用真实 hook + 真实 QueryClient + spy 拦截 fetch 函数,直接断言
// ``enabled`` 语义,删掉修复代码就会变红。
//
// 复用 test-utils 的 QueryClient 配置(retry:false,staleTime:Infinity),只是
// 入口换成 renderHook —— renderWithProviders 返回 render 结果,这里要 hook 句柄。
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import * as endpoints from "@/api/endpoints";
import { useBookingConfigEffective } from "@/hooks/queries";

// renderHook 的 wrapper 是「组件函数」,不是工厂。每个 case 独立 QueryClient,
// 防止缓存串扰(同 test-utils.tsx 的设计理由)。
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useBookingConfigEffective — enabled 门控(回归 bugfix:403 on /effective)", () => {
  // 回归 bugfix:useBookingConfigEffective 缺 ``enabled: !!tenantId`` 门控时,
  // HQ 视图首次渲染(targetTenantId 还是 "")会以 undefined 调用本 hook → 立即
  // 发起 GET /bookings/config/effective(不带 tenant_id)→ 后端按防伪造契约对
  // 平台角色返回 403(见 app/api/v1/booking_config.py:166-179,
  // test_x_super_admin_effective_without_tenant_id_forbidden 锁定)。
  //
  // 历史背景:HqView:208-214 注释声称本 hook "和 useTenantBookingsByDate 一样
  // 容忍 undefined",但门控行一直没加。集成测试全 mock 无法捕捉,故在此直接
  // 断言 hook 的 enabled 语义。删掉 queries.ts 里的 ``enabled: !!tenantId``
  // 此用例变红(fetch 被 spy 调用)。
  it("tenantId 为 undefined 时不发起 fetch(防 HQ 首次渲染 403)", async () => {
    const spy = vi
      .spyOn(endpoints, "fetchEffectiveBookingConfig")
      .mockResolvedValue({
        default_duration_minutes: 45,
        window_start: "08:00",
        window_end: "22:00",
        source: "default",
      });

    const { result } = renderHook(() => useBookingConfigEffective(undefined), {
      wrapper: createWrapper(),
    });

    // enabled=false → query 不执行,data 保持 undefined,fetch 不被调用
    expect(result.current.data).toBeUndefined();
    // 给一点窗口确认 react-query 不会异步触发(它不会,但显式等待让断言更稳)
    await waitFor(() => {
      expect(spy).not.toHaveBeenCalled();
    });
  });

  it("tenantId 有值时发起 fetch 并返回 data", async () => {
    const spy = vi
      .spyOn(endpoints, "fetchEffectiveBookingConfig")
      .mockResolvedValue({
        default_duration_minutes: 60,
        window_start: "09:00",
        window_end: "21:00",
        source: "tenant",
      });

    const { result } = renderHook(
      () => useBookingConfigEffective("tnt-1"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.data?.source).toBe("tenant");
    });
    expect(spy).toHaveBeenCalledWith("tnt-1");
  });
});
