import * as React from "react";
import { RATE_LIMITED_EVENT } from "@/api/client";
import { useToast } from "./toast";

/**
 * Rate-limited toast bridge (rate-limit-login-lockout slice 03).
 *
 * The axios interceptor (api/client.ts) dispatches `aap:rate-limited` on 429;
 * this listener turns it into a friendly error toast. It MUST be mounted
 * inside ToastProvider (App.tsx does) — useToast only works there, and the
 * interceptor itself lives outside the React tree (that's the whole reason
 * the event bridge exists, mirroring AUTH_EXPIRED_EVENT / auth-context).
 *
 * No dedup/throttle on purpose: a burst of 429s stacking a few toasts is
 * acceptable; each auto-dismisses after 4s.
 */
export function RateLimitedToast() {
  const t = useToast();

  React.useEffect(() => {
    const handler = () => t.error("请求过于频繁,请稍后再试");
    window.addEventListener(RATE_LIMITED_EVENT, handler);
    return () => window.removeEventListener(RATE_LIMITED_EVENT, handler);
  }, [t]);

  return null;
}
