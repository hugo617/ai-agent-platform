import axios, { AxiosError } from "axios";

/**
 * Pre-configured axios instance for the FastAPI backend.
 *
 * Requests go through the Vite dev-server proxy (see vite.config.ts), so the
 * browser calls `/api/v1/...` and they are forwarded to `http://localhost:8000`.
 *
 * Auth: a token is read from localStorage and attached as `Authorization: Bearer`.
 * In production this token comes from Logto; in development you can paste a
 * token in the Settings page (useful for hitting the real backend).
 */
const TOKEN_KEY = "aap.access_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export const api = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
});

// Attach bearer token on every request.
api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * Global 401 handler. When the backend rejects a request with 401 the local
 * token is stale/revoked (expired, user removed, account locked, …). We clear
 * the stored token and dispatch an event the AuthProvider listens for so the
 * app redirects to /login — without it, every query would just keep failing
 * with generic toasts while the UI shows stale data.
 *
 * 403 is intentionally NOT treated as "session expired": it means the caller is
 * authenticated but lacks permission, which should surface as a normal error.
 */
export const AUTH_EXPIRED_EVENT = "aap:auth-expired";

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      setStoredToken(null);
      // Only meaningful inside a browser; harmless under Vitest/jsdom otherwise.
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
      }
    }
    return Promise.reject(error);
  }
);

// Surface API errors with a readable message.
export function apiErrorMessage(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data) {
    const data = err.response.data as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    // FastAPI 422 shape: { detail: [{ loc, msg, type }, ...] }
    if (Array.isArray(data.detail) && data.detail.length > 0) {
      const first = data.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
      return "请求参数校验失败";
    }
  }
  if (err instanceof Error) return err.message;
  return "未知错误";
}
