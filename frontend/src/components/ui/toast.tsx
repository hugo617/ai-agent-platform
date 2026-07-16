import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Lightweight toast — no external dependency.
 *
 * Usage: ``const t = useToast(); t.success("saved")``.
 *
 * Two ergonomics on top of the original Context+hook pattern:
 *  - **Enter animation** — each toast slides up + fades in via the
 *    ``slide-in-up`` keyframe (defined in tailwind.config.js, phase 0). No
 *    motion library needed; this is one of the "everything else is CSS"
 *    cases (plan §6).
 *  - **``promise`` helper** — ``t.promise(fn, { loading, success, error })``
 *    shows a loading toast, then swaps to success/error when the promise
 *    settles. This covers the main reason the plan considered sonner (async
 *    exports / long tasks) without migrating the 17-file / 163-call surface.
 *
 * Decision (plan §2.4 / §9 #5): keep this self-rolled toast; do NOT swap to
 * sonner. The migration cost (17 files, 163 call sites) far exceeds the value
 * of sonner's promise/stack features, which we replicate narrowly here.
 */

type ToastVariant = "default" | "success" | "destructive" | "loading";

interface ToastItem {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface PromiseMessages {
  loading: string;
  success: string;
  error: string;
}

interface ToastContextValue {
  push: (t: Omit<ToastItem, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  /**
   * Track a promise: show a loading toast, then resolve to a success or error
   * toast based on the outcome. Returns the promise so callers can chain.
   *
   *   const t = useToast();
   *   t.promise(api.exportCsv(), {
   *     loading: "导出中…",
   *     success: "导出完成",
   *     error: "导出失败",
   *   });
   */
  promise: <T>(
    fn: () => Promise<T>,
    messages: PromiseMessages,
  ) => Promise<T>;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const idRef = React.useRef(0);

  const remove = React.useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = React.useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = ++idRef.current;
      setItems((prev) => [...prev, { ...t, id }]);
      // Loading toasts persist until swapped/cleared; others auto-dismiss.
      if (t.variant !== "loading") {
        setTimeout(() => remove(id), 4000);
      }
      return id;
    },
    [remove],
  );

  /** Replace the title/description/variant of an existing toast in place. */
  const update = React.useCallback(
    (id: number, patch: Partial<Omit<ToastItem, "id">>) => {
      setItems((prev) =>
        prev.map((t) => (t.id === id ? { ...t, ...patch } : t)),
      );
    },
    [],
  );

  const value = React.useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, description) =>
        push({ title, description, variant: "success" }),
      error: (title, description) =>
        push({ title, description, variant: "destructive" }),
      promise: async (fn, messages) => {
        const id = push({ title: messages.loading, variant: "loading" });
        try {
          const result = await fn();
          update(id, { title: messages.success, variant: "success" });
          // Auto-dismiss the swapped-in success toast (it was loading, which
          // doesn't auto-dismiss, so schedule removal now).
          setTimeout(() => remove(id), 4000);
          return result;
        } catch (e) {
          update(id, { title: messages.error, variant: "destructive" });
          setTimeout(() => remove(id), 4000);
          throw e;
        }
      },
    }),
    [push, update, remove],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              // slide-in-up enter animation (CSS keyframe, no motion lib).
              "pointer-events-auto animate-slide-in-up rounded-md border p-4 shadow-lg",
              t.variant === "success" &&
                "border-emerald-200 bg-emerald-50 text-emerald-900",
              t.variant === "destructive" &&
                "border-red-200 bg-red-50 text-red-900",
              t.variant === "loading" && "border-border bg-background",
              t.variant === "default" && "border-border bg-background",
            )}
          >
            <div className="flex items-center gap-2">
              {t.variant === "loading" && (
                <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
              )}
              <div className="text-sm font-semibold">{t.title}</div>
            </div>
            {t.description && (
              <div className="mt-1 text-xs opacity-80">{t.description}</div>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
