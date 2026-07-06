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

// Surface API errors with a readable message.
export function apiErrorMessage(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data) {
    const data = err.response.data as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return "validation error";
  }
  if (err instanceof Error) return err.message;
  return "unknown error";
}

export function isAuthError(err: unknown): boolean {
  return err instanceof AxiosError && (err.response?.status === 401 || err.response?.status === 403);
}
