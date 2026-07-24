// 组件测试的 render 入口(device-poweron 切片 02)。
//
// 为什么必须包 providers:
//   - ``useMyBookings`` / ``useStartBooking`` 调 ``useQueryClient`` → 需
//     ``QueryClientProvider``。
//   - 组件里的 ``toast.success/error`` 调 ``useToast`` → 需
//     ``ToastProvider``(否则抛 "useToast must be used within ToastProvider")。
//
// 为什么每测新建 QueryClient:
//   全局共享的 QueryClient 会把上个案的缓存数据带进下个案,断言串扰。
//   且设 ``retry:false``(mutation/query 失败立即 reject,不重试拖慢/误判)
//   + ``staleTime:Infinity``(防止后台 refetch 在断言窗口内改变 DOM)。
//
// 复用模式:测试用 ``renderWithProviders(<Component/>)`` 替代裸 render。
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { ToastProvider } from "@/components/ui/toast";

export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}
