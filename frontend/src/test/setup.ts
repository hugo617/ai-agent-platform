// Vitest 全局 setup(device-poweron 切片 02)。
//
// 1. ``@testing-library/jest-dom`` —— 给 expect 注入 ``toBeInTheDocument``
//    等 DOM matchers;配合 tsconfig.app.json 的 types 声明,tsc 也认。
// 2. ``afterEach(cleanup)`` —— 每个用例间卸载上一轮 render 的 DOM,避免
//    跨用例查询串扰(如 ``getByText`` 撞到上一个用例残留的节点)。
import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
