// msw (Mock Service Worker) 集成测试基建(knowledge-tiered reader-ui slice 01)。
//
// 这是项目首个 msw seam:既有的前端测试(devices/bookings/chat/customers)全
// 部用 mock-hook 范式(stub useXxx hook),不触达 axios 层。本 feature 引入 msw
// 补一层「前端类型层 ↔ 后端 API 契约」的集成测试 —— 在 node 测试环境里用
// ``setupServer`` 拦截 axios 发出的真实 HTTP 请求,断言请求构造(query string /
// body)+ 响应解析(类型层契约对齐),不依赖后端起没起。
//
// 用法(测试文件):
//   import { server } from "@/test/msw-server";
//   beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
//   afterEach(() => server.resetHandlers());   // 隔离:每个用例的 handler 用完即清
//   afterAll(() => server.close());
//   server.use(http.get("/api/v1/knowledge/documents", () =>
//     HttpResponse.json([...])));
//
// 为什么放 ``src/test/`` 而非 ``__tests__/``:这是跨 feature 复用的共享基建
// (后续 feature 可沿用),与 ``test-utils.tsx`` / ``setup.ts`` 同层。每个 feature
// 的具体测试文件放自己的 ``__tests__/`` 目录。
//
// ⚠️ 偏离范式声明:本 seam 是经确认的显式决策(plan §4.6)—— 补 mock-hook 范式
// 不覆盖的契约层。后续 feature 自行选择 mock-hook 或 msw,不强推。
import { setupServer } from "msw/node";
import { type HttpHandler } from "msw";

/**
 * 共享的 msw server 单例。测试文件 import 这个 ``server``,用 ``server.use``
 * 注册本用例专属的 handler,在 ``afterEach`` 调 ``resetHandlers`` 清理。
 *
 * ``onUnhandledRequest: "error"`` 让任何未匹配的请求直接报错 —— 强制每个测试
 * 显式声明它依赖的 endpoint,避免「假装通过」(请求漏 mock,axios 抛网络错,
 * 测试却没断言到)。
 */
export const server = setupServer();

// 类型再导出,测试文件 import ``http`` / ``HttpResponse`` 时统一从 ``@/test/msw-server``
// 进(减少跨文件 import 路径分歧)。msw 的 ``http`` / ``HttpResponse`` 是命名导出,
// 这里透传。
export { http, HttpResponse } from "msw";
export type { HttpHandler };
