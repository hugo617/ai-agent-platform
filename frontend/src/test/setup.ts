// Vitest 全局 setup(device-poweron 切片 02)。
//
// 1. ``@testing-library/jest-dom`` —— 给 expect 注入 ``toBeInTheDocument``
//    等 DOM matchers;配合 tsconfig.app.json 的 types 声明,tsc 也认。
// 2. ``afterEach(cleanup)`` —— 每个用例间卸载上一轮 render 的 DOM,避免
//    跨用例查询串扰(如 ``getByText`` 撞到上一个用例残留的节点)。
// 3. jsdom polyfills for Radix UI (platform-cross-tenant-write 切片 04) ——
//    Radix Select 内部用 ``hasPointerCapture`` / ``scrollIntoView`` /
//    ``releasePointerCapture`` 等 Pointer Events API,jsdom 没实现;在
//    hq-view.test.tsx 选目标门店下拉时撞 ``TypeError: target.hasPointerCapture
//    is not a function`` + ``candidate?.scrollIntoView is not a function``。
//    Polyfill 这几个方法到 HTMLElement.prototype,让 Radix Select 在 jsdom 下
//    跑通(标准做法,React Testing Library + Radix 社区惯例)。
import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

if (typeof HTMLElement !== "undefined") {
  // No-op stubs — Radix uses these for pointer capture + viewport-scroll
  // coordination in real browsers; in jsdom there's no viewport to scroll
  // or pointer to capture, so the stubs just satisfy the API surface.
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => {};
  }
  if (!HTMLElement.prototype.scrollIntoView) {
    HTMLElement.prototype.scrollIntoView = () => {};
  }
}

afterEach(() => {
  cleanup();
});
