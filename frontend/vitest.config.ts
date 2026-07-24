/// <reference types="vitest/config" />
import { mergeConfig } from "vite";
import viteConfig from "./vite.config";

// Vitest config — 本项目首个前端单测基建(device-poweron 切片 02)。
//
// 用 ``mergeConfig`` 从 ``vite.config.ts`` 引入(而非抄一份),这样
// ``@vitejs/plugin-react`` + ``@`` alias 任何调整都自动同步,不会在
// build 与 test 之间漂移。只在此追加 ``test:`` 字段:
//   - environment: jsdom  —— RTL 需要 DOM
//   - setupFiles   —— 注入 jest-dom matchers + afterEach(cleanup)
//   - globals: true —— ``describe``/``it``/``expect``/``vi`` 全局可见,
//     配合 tsconfig.app.json 的 ``vitest/globals`` types 让 tsc 也认。
export default mergeConfig(viteConfig, {
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    // 只扫 src 下的单测;e2e/*.spec.ts 是 Playwright 文件(由 @playwright/test
    // 独立跑),不归 vitest 管 —— 不排除会被误抓成 vitest 用例并报「test()
    // called here」错。
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
