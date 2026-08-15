// rate-limit-login-lockout 切片 03 —— 前端 429 事件桥测试。
//
// 覆盖 plan 切片 03 AC:「client.ts 拦 429 → dispatchEvent(aap:rate-limited)
// → ToastProvider 子树内 listener → t.error toast;不清 token、不跳登录、
// 不自动重试」+「401 既有行为不回归」。
//
// 测法:不走 mock 拦截器,而是给真实 ``api`` 实例塞 stub adapter(按指定
// status reject 一个带 response 的 AxiosError),让响应拦截器链**真跑**——
// 这样一条用例就覆盖 整链:adapter 429 → 拦截器 dispatch 事件 →
// RateLimitedToast listener → t.error → toast 渲染。
//
// Toast 走 ToastProvider + useToast 真实路径(不 mock,范式沿用
// badge-toast-avatar.test.tsx)。adapter 是共享实例上的全局 default,每个
// 用例后必须还原,否则污染同文件其余用例。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { render, screen } from "@testing-library/react";
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";

import { api, AUTH_EXPIRED_EVENT, getStoredToken, setStoredToken } from "@/api/client";
import { RateLimitedToast } from "./rate-limited-toast";
import { ToastProvider } from "./toast";

const RATE_LIMIT_MESSAGE = "请求过于频繁,请稍后再试";

// 让真实 axios 实例按指定 status 失败一次 —— 拦截器据此分流 401/429。
function stubAdapter(status: number) {
  return (config: InternalAxiosRequestConfig) => {
    const response = {
      data: { detail: "stubbed" },
      status,
      statusText: "",
      headers: {},
      config,
    } as AxiosResponse;
    return Promise.reject(
      new AxiosError("stubbed", AxiosError.ERR_BAD_REQUEST, config, undefined, response),
    );
  };
}

describe("RateLimitedToast — 429 事件桥(rate-limit-login-lockout slice 03)", () => {
  const originalAdapter = api.defaults.adapter;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
  });

  it("429 → aap:rate-limited 事件 → 错误 toast 渲染;token 不被清除", async () => {
    api.defaults.adapter = stubAdapter(429);
    setStoredToken("tok-keep");
    render(
      <ToastProvider>
        <RateLimitedToast />
      </ToastProvider>,
    );

    await act(async () => {
      await api.get("/anything").catch(() => {
        /* 拦截器 reject 后由调用方 catch,这里只驱动拦截器链 */
      });
    });

    // 事件桥终点:错误 toast 出现
    expect(screen.getByText(RATE_LIMIT_MESSAGE)).toBeTruthy();
    // 限流不是认证失败:token 保留(不清、不跳登录)
    expect(getStoredToken()).toBe("tok-keep");
  });

  it("429 不触发 AUTH_EXPIRED_EVENT(不踢登录)", async () => {
    api.defaults.adapter = stubAdapter(429);
    const expiredSpy = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expiredSpy);

    await act(async () => {
      await api.get("/anything").catch(() => {});
    });

    expect(expiredSpy).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_EXPIRED_EVENT, expiredSpy);
  });

  it("401 既有行为不回归:清 token + 发 AUTH_EXPIRED_EVENT;不出限流 toast", async () => {
    api.defaults.adapter = stubAdapter(401);
    const expiredSpy = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expiredSpy);
    setStoredToken("tok-stale");
    render(
      <ToastProvider>
        <RateLimitedToast />
      </ToastProvider>,
    );

    await act(async () => {
      await api.get("/anything").catch(() => {});
    });

    expect(getStoredToken()).toBeNull();
    expect(expiredSpy).toHaveBeenCalledTimes(1);
    // 401 不经限流 toast
    expect(screen.queryByText(RATE_LIMIT_MESSAGE)).toBeNull();
    window.removeEventListener(AUTH_EXPIRED_EVENT, expiredSpy);
  });
});
